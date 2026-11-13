"""Images of questions and choices, stored once per distinct content.

See models.StoredImage. Writing goes through store_image(), which needs no
read of the image table: identical bytes map to the same key, and an image
already stored is locked instead of written again.
"""

from collections.abc import Iterable
from hashlib import sha256

from sqlalchemy import delete, func, select, union
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import affected_rows
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
        # A no-op update rather than DO NOTHING: it locks an existing row
        # until the caller commits, so a concurrent purge cannot delete the
        # image between this call and the write that references it.
        .on_conflict_do_update(
            index_elements=[StoredImage.sha256],
            set_={"sha256": insert(StoredImage).excluded.sha256},
        )
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
    """Delete the images no question or choice uses any more.

    A teacher may save a question that reuses an unreferenced image while
    this runs: the foreign key then rejects the deletion. That attempt is
    rolled back to a savepoint, leaving the rest of the caller's transaction
    intact, and the next run collects what is still unused.
    """
    referenced = union(
        select(Question.image_sha256).where(Question.image_sha256.is_not(None)),
        select(QuestionChoice.image_sha256).where(
            QuestionChoice.image_sha256.is_not(None)
        ),
    )
    try:
        with session.begin_nested():
            return affected_rows(
                session.execute(
                    delete(StoredImage).where(StoredImage.sha256.not_in(referenced))
                )
            )
    except IntegrityError:
        return 0
