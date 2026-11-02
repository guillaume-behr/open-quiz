"""Images of questions and choices, stored once per distinct content.

See models.StoredImage. Writing goes through store_image(), which needs no
read of the image table: identical bytes map to the same key, and a
concurrent insertion of the same image is simply skipped.
"""

from collections.abc import Iterable
from hashlib import sha256
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select, union
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Question, QuestionChoice, StoredImage


def store_image(
    session: Session, data: bytes | None, content_type: str | None
) -> str | None:
    """Store an image if it is new and return the key that references it."""
    if data is None or content_type is None:
        return None
    digest = sha256(data).hexdigest()
    session.execute(
        insert(StoredImage)
        .values(sha256=digest, content_type=content_type, data=data)
        .on_conflict_do_nothing(index_elements=[StoredImage.sha256])
    )
    return digest


def stored_image_sizes(session: Session, digests: Iterable[str]) -> dict[str, int]:
    """Byte sizes of stored images, measured without transferring them."""
    wanted = set(digests)
    if not wanted:
        return {}
    return dict(
        session.execute(
            select(StoredImage.sha256, func.octet_length(StoredImage.data)).where(
                StoredImage.sha256.in_(wanted)
            )
        ).all()
    )


def delete_unreferenced_images(session: Session) -> int:
    """Delete the images no question or choice uses any more."""
    referenced = union(
        select(Question.image_sha256).where(Question.image_sha256.is_not(None)),
        select(QuestionChoice.image_sha256).where(
            QuestionChoice.image_sha256.is_not(None)
        ),
    )
    result = cast(
        CursorResult[Any],
        session.execute(
            delete(StoredImage).where(StoredImage.sha256.not_in(referenced))
        ),
    )
    return result.rowcount
