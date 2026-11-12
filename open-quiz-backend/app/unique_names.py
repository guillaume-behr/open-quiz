"""Report a write that reuses one of a teacher's names as the matching error."""

from collections.abc import Callable

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ApiError, ErrorCode


def write_unique_name(
    session: Session,
    write: Callable[[], None],
    constraint: str,
    code: ErrorCode,
    message: str,
) -> None:
    """Run ``write``; a violation of ``constraint`` becomes a 409 ``code``.

    Any other integrity error propagates: it is not a name already taken.
    """
    try:
        write()
    except IntegrityError as error:
        session.rollback()
        diagnostic = getattr(error.orig, "diag", None)
        if getattr(diagnostic, "constraint_name", None) != constraint:
            raise
        raise ApiError(status.HTTP_409_CONFLICT, code, message) from None


QUESTION_BANK_NAME_CONSTRAINT = "uq_question_bank_owner_classification"
QUESTION_BANK_NAME_TAKEN_MESSAGE = "Une banque existe déjà pour ce niveau et ce titre"


def commit_unique_bank(session: Session) -> None:
    write_unique_name(
        session,
        session.commit,
        QUESTION_BANK_NAME_CONSTRAINT,
        ErrorCode.QUESTION_BANK_NAME_TAKEN,
        QUESTION_BANK_NAME_TAKEN_MESSAGE,
    )
