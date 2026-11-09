import warnings
from io import BytesIO
from threading import BoundedSemaphore

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_DIMENSION = 8192
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
# The decoders an upload may reach. Pillow otherwise tries every format it
# knows, whatever type the upload declares: some forty parsers, most of them
# for formats no browser would ever send here.
ACCEPTED_IMAGE_FORMATS = ("JPEG", "PNG", "WEBP", "GIF")
# Decoding holds an image's pixels in memory several times over, up to a few
# hundred megabytes for the largest accepted. Without a bound, a burst of
# uploads multiplies that by the size of the request thread pool.
MAX_CONCURRENT_IMAGE_DECODES = 2
image_decoding = BoundedSemaphore(MAX_CONCURRENT_IMAGE_DECODES)

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class InvalidImageError(ValueError):
    pass


def image_pixel_count(data: bytes) -> int:
    """Pixels an image would decode to, read from its header alone.

    Zero for data that is not an accepted image: normalize_image() refuses it.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(
                BytesIO(data), formats=ACCEPTED_IMAGE_FORMATS
            ) as candidate:
                return candidate.width * candidate.height
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ):
        return 0


def normalize_image(data: bytes, declared_type: str) -> tuple[bytes, str]:
    """Decode and re-encode an image so stored bytes match a safe media type."""
    if declared_type not in ALLOWED_IMAGE_TYPES:
        raise InvalidImageError("Format d’image non pris en charge")
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise InvalidImageError("L’image est vide ou trop volumineuse")

    try:
        with image_decoding, warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(
                BytesIO(data), formats=ACCEPTED_IMAGE_FORMATS
            ) as candidate:
                candidate.verify()
            with Image.open(
                BytesIO(data), formats=ACCEPTED_IMAGE_FORMATS
            ) as candidate:
                candidate.load()
                if (
                    candidate.width > MAX_IMAGE_DIMENSION
                    or candidate.height > MAX_IMAGE_DIMENSION
                    or candidate.width * candidate.height > MAX_IMAGE_PIXELS
                ):
                    raise InvalidImageError(
                        "Les dimensions de l’image sont trop grandes"
                    )
                normalized = ImageOps.exif_transpose(candidate)
                output = BytesIO()
                if declared_type == "image/jpeg":
                    normalized.convert("RGB").save(
                        output,
                        format="JPEG",
                        quality=90,
                        optimize=True,
                    )
                    content_type = "image/jpeg"
                elif declared_type == "image/webp":
                    mode = "RGBA" if "A" in normalized.getbands() else "RGB"
                    normalized.convert(mode).save(
                        output,
                        format="WEBP",
                        lossless=True,
                        method=4,
                    )
                    content_type = "image/webp"
                else:
                    mode = "RGBA" if "A" in normalized.getbands() else "RGB"
                    normalized.convert(mode).save(
                        output,
                        format="PNG",
                        optimize=True,
                    )
                    content_type = "image/png"
    except InvalidImageError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as error:
        raise InvalidImageError(
            "Le fichier envoyé n’est pas une image valide"
        ) from error

    normalized_data = output.getvalue()
    if not normalized_data or len(normalized_data) > MAX_IMAGE_BYTES:
        raise InvalidImageError("L’image convertie est vide ou trop volumineuse")
    return normalized_data, content_type
