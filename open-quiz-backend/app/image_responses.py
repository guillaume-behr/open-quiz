"""Stored images served so that a browser revalidates them instead of refetching.

Images are stored under the SHA-256 of their bytes, so that hash is a strong
ETag: an image never changes under it. A request that already holds it gets
304 without the image being read from the database.
"""

from fastapi import Request, Response, status
from sqlalchemy.orm import Session

from app.models import StoredImage

# Private: only the viewer's browser keeps an image. No-cache: it asks again
# before each use, so the route checks access every time (a student who left
# the question, a teacher who deleted it) while an unchanged image costs a 304
# instead of its bytes.
IMAGE_CACHE_CONTROL = "private, no-cache"


def holds_image(request: Request, etag: str) -> bool:
    header = request.headers.get("If-None-Match")
    if header is None:
        return False
    candidates = {
        candidate.strip().removeprefix("W/") for candidate in header.split(",")
    }
    return etag in candidates or "*" in candidates


def image_response(image_sha256: str, request: Request, session: Session) -> Response:
    """The stored image, or 304 when the browser already holds it."""
    etag = f'"{image_sha256}"'
    headers = {"ETag": etag, "Cache-Control": IMAGE_CACHE_CONTROL}
    if holds_image(request, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    image = session.get_one(StoredImage, image_sha256)
    return Response(content=image.data, media_type=image.content_type, headers=headers)
