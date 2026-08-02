from argparse import ArgumentParser

from sqlalchemy import delete, select

from app.audit import audit_event
from app.config import Settings, get_settings
from app.database import build_session_factory
from app.models import (
    AuthenticationChallenge,
    RefreshSession,
    RefreshSessionFamily,
    TwoFactorCredential,
    User,
)


def reset(username: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    session_factory = build_session_factory(settings.database_url)
    with session_factory() as session:
        user = session.scalar(select(User).where(User.username == username))
        if user is None:
            return False
        refresh_session_ids = select(RefreshSession.id).where(
            RefreshSession.user_id == user.id
        )
        session.execute(
            delete(RefreshSessionFamily).where(
                RefreshSessionFamily.session_id.in_(refresh_session_ids)
            )
        )
        session.execute(delete(RefreshSession).where(RefreshSession.user_id == user.id))
        session.execute(
            delete(AuthenticationChallenge).where(
                AuthenticationChallenge.user_id == user.id
            )
        )
        session.execute(
            delete(TwoFactorCredential).where(TwoFactorCredential.user_id == user.id)
        )
        session.commit()
        audit_event("security.two_factor_reset_by_script", user_id=user.id)
        return True


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Reset a user's 2FA enrollment and revoke active sessions."
    )
    parser.add_argument("username")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt.",
    )
    arguments = parser.parse_args()
    if not arguments.yes:
        confirmation = input(
            f"Reset 2FA and revoke all sessions for '{arguments.username}'? [y/N] "
        )
        if confirmation.strip().lower() not in {"y", "yes"}:
            parser.exit(1, "Aborted.\n")
    if not reset(arguments.username):
        parser.error("user not found")
