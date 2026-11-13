from app.enums import SessionStatus
from app.models import QuizParticipant, QuizSession

ACTIVE_SESSION_STATUSES = (
    SessionStatus.WAITING,
    SessionStatus.IN_PROGRESS,
    SessionStatus.PAUSED,
)


def took_part(
    participant: QuizParticipant, quiz_session: QuizSession, answered_count: int
) -> bool:
    """Whether a participant took part in an exam, for every results view.

    Someone who left the waiting room and never answered took no part: the
    teacher's results do not list them, and their history does not show them
    the exam or its correction.
    """
    return not (
        participant.left_at is not None
        and (
            quiz_session.started_at is None
            or participant.left_at <= quiz_session.started_at
        )
        and answered_count == 0
    )
