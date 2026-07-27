from pathlib import Path
from secrets import token_urlsafe
from time import time

from sqlalchemy import update

from app.config import get_settings
from app.database import build_session_factory
from app.models import RefreshSession

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
SECURE_DEFAULTS = {
    "JWT_SECRET": token_urlsafe(48),
    "ADMIN_PASSWORD": token_urlsafe(24),
}


def rotate() -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    updated: set[str] = set()
    output: list[str] = []

    for line in lines:
        name = line.split("=", 1)[0] if "=" in line else ""
        if name in SECURE_DEFAULTS:
            output.append(f"{name}={SECURE_DEFAULTS[name]}")
            updated.add(name)
        else:
            output.append(line)

    for name, value in SECURE_DEFAULTS.items():
        if name not in updated:
            output.append(f"{name}={value}")

    ENV_FILE.write_text("\n".join(output) + "\n", encoding="utf-8")
    settings = get_settings()
    session_factory = build_session_factory(settings.database_url)
    with session_factory() as session:
        session.execute(
            update(RefreshSession)
            .where(RefreshSession.revoked_at.is_(None))
            .values(revoked_at=int(time()))
        )
        session.commit()


if __name__ == "__main__":
    rotate()
