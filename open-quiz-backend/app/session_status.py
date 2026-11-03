from app.enums import SessionStatus

ACTIVE_SESSION_STATUSES = (
    SessionStatus.WAITING,
    SessionStatus.IN_PROGRESS,
    SessionStatus.PAUSED,
)
