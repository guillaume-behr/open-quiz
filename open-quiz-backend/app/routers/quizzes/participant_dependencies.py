"""Request dependencies on the quiz participant an X-Quiz-Token opens."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, Request

from app.core.dependencies import DbSession
from app.services.participants import ParticipantContext, rate_limited_participant


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
