from argparse import ArgumentParser

from sqlalchemy import delete, select

from app.config import Settings, get_settings
from app.database import build_session_factory
from app.models import RefreshSession, TwoFactorCredential, User


def reset(username: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    session_factory = build_session_factory(settings.database_url)
    with session_factory() as session:
        user = session.scalar(select(User).where(User.username == username))
        if user is None:
            return False
        session.execute(delete(RefreshSession).where(RefreshSession.user_id == user.id))
        session.execute(
            delete(TwoFactorCredential).where(TwoFactorCredential.user_id == user.id)
        )
        session.commit()
        return True


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Reset a user's 2FA enrollment and revoke active sessions."
    )
    parser.add_argument("username")
    arguments = parser.parse_args()
    if not reset(arguments.username):
        parser.error("user not found")
