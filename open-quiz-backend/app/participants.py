"""Quiz participants: join codes, participant tokens and public rate limits."""

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from random import SystemRandom
from string import ascii_uppercase, digits
from typing import Annotated, NoReturn

from fastapi import (
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from starlette.requests import HTTPConnection

from app.dependencies import DbSession
from app.errors import ApiError, ErrorCode
from app.models import (
    Quiz,
    QuizJoinCode,
    QuizParticipant,
    QuizSession,
    Student,
    StudentAccount,
)

randomizer = SystemRandom()


JOIN_CODE_ALPHABET = ascii_uppercase + digits


VIOLATION_DEDUPLICATION_SECONDS = 2
# Recorded by the server, never reported by a browser: a student took their
# participation back on a new token (student_join.resume_participation).
SESSION_RESUMED_VIOLATION = "session_resumed"


def enforce_public_rate_limit(
    request: HTTPConnection,
    limiter_name: str,
    subject: str,
) -> None:
    limiter = getattr(request.app.state, limiter_name)
    retry_after = limiter.reserve(subject)
    if retry_after:
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            ErrorCode.QUIZ_RATE_LIMITED,
            "Trop de tentatives pour rejoindre le quiz",
            headers={"Retry-After": str(retry_after)},
        )


def quiz_join_rejected() -> HTTPException:
    return ApiError(
        status.HTTP_403_FORBIDDEN,
        ErrorCode.QUIZ_JOIN_REJECTED,
        "Impossible de rejoindre ce quiz",
    )


def reject_quiz_join(request: Request, subject: str) -> NoReturn:
    enforce_public_rate_limit(
        request,
        "quiz_join_rate_limiter",
        subject,
    )
    raise quiz_join_rejected()


def participant_token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def public_session_subject(
    join_code: str,
    purpose: str,
    session: DbSession,
) -> str:
    normalized_join_code = join_code.strip().upper()
    session_id = session.scalar(
        select(QuizSession.id).where(QuizSession.join_code == normalized_join_code)
    )
    return (
        f"{purpose}:session:{session_id}"
        if session_id is not None
        else f"{purpose}:code:{normalized_join_code}"
    )


def authenticated_participant(
    join_code: str,
    token: str | None,
    request: HTTPConnection,
    session: DbSession,
) -> tuple[QuizSession, Quiz, QuizParticipant]:
    if not token:
        enforce_public_rate_limit(
            request,
            "quiz_join_rate_limiter",
            public_session_subject(join_code, "participant-auth", session),
        )
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.QUIZ_PARTICIPANT_TOKEN_MISSING,
            "Jeton de participation au quiz manquant",
        )
    row = session.execute(
        select(QuizSession, Quiz, QuizParticipant)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .join(
            QuizParticipant,
            QuizParticipant.session_id == QuizSession.id,
        )
        .where(
            QuizSession.join_code == join_code.strip().upper(),
            QuizParticipant.access_token_hash == participant_token_hash(token),
            QuizParticipant.left_at.is_(None),
        )
    ).first()
    if row is None:
        enforce_public_rate_limit(
            request,
            "quiz_join_rate_limiter",
            public_session_subject(join_code, "participant-auth", session),
        )
        replaced = session.scalar(
            select(QuizParticipant.id)
            .join(QuizSession, QuizSession.id == QuizParticipant.session_id)
            .where(
                QuizSession.join_code == join_code.strip().upper(),
                QuizParticipant.replaced_token_hash == participant_token_hash(token),
                QuizParticipant.left_at.is_(None),
            )
        )
        if replaced is not None:
            raise ApiError(
                status.HTTP_401_UNAUTHORIZED,
                ErrorCode.QUIZ_PARTICIPANT_SESSION_RESUMED,
                "Ce quiz a été repris dans une autre fenêtre",
            )
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.QUIZ_PARTICIPANT_TOKEN_INVALID,
            "Jeton de participation au quiz invalide",
        )
    participant = row[2]
    active_account = session.scalar(
        select(StudentAccount.is_active)
        .join(Student, Student.account_id == StudentAccount.id)
        .where(Student.id == participant.student_id)
    )
    if active_account is not True:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.QUIZ_PARTICIPANT_TOKEN_INVALID,
            "Jeton de participation au quiz invalide",
        )
    return row


@dataclass(frozen=True)
class ParticipantContext:
    """The participant a request's token opens, with its session and quiz."""

    participant: QuizParticipant
    session: QuizSession
    quiz: Quiz


def rate_limited_participant(
    join_code: str,
    quiz_token: str | None,
    request: Request,
    session: DbSession,
    limiter_name: str,
) -> ParticipantContext:
    """Authenticate the participant, then count the request against them."""
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(request, limiter_name, f"participant:{participant.id}")
    return ParticipantContext(participant, quiz_session, quiz)


def participant_context(
    limiter_name: str,
) -> Callable[[str, Request, DbSession, str | None], ParticipantContext]:
    """A dependency on the participant a request's X-Quiz-Token opens."""

    def dependency(
        join_code: str,
        request: Request,
        session: DbSession,
        quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
    ) -> ParticipantContext:
        return rate_limited_participant(
            join_code, quiz_token, request, session, limiter_name
        )

    return dependency


CurrentParticipant = Annotated[
    ParticipantContext,
    Depends(participant_context("quiz_participant_rate_limiter")),
]
# Anti-cheating reports count against a limiter of their own.
ReportingParticipant = Annotated[
    ParticipantContext,
    Depends(participant_context("quiz_violation_rate_limiter")),
]


def generate_join_code(session: DbSession) -> str:
    for _ in range(20):
        code = "".join(randomizer.choice(JOIN_CODE_ALPHABET) for _ in range(6))
        reserved_code = session.scalar(
            insert(QuizJoinCode)
            .values(code=code)
            .on_conflict_do_nothing(index_elements=[QuizJoinCode.code])
            .returning(QuizJoinCode.code)
        )
        if reserved_code is not None:
            return code
    raise ApiError(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        ErrorCode.QUIZ_CODE_GENERATION_FAILED,
        "Impossible de générer un code de quiz",
    )
