from pathlib import Path
from secrets import token_urlsafe
from time import time

from sqlalchemy import update

from app.config import get_settings, secure_private_file, write_private_file
from app.database import build_session_factory
from app.models import RefreshSession

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
ROTATED_KEYS = ("JWT_SECRET", "ADMIN_PASSWORD")


def rotate() -> None:
    secure_defaults = {
        "JWT_SECRET": token_urlsafe(48),
        "ADMIN_PASSWORD": token_urlsafe(24),
    }
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    updated: set[str] = set()
    output: list[str] = []

    for line in lines:
        name = line.split("=", 1)[0] if "=" in line else ""
        if name in secure_defaults:
            output.append(f"{name}={secure_defaults[name]}")
            updated.add(name)
        else:
            output.append(line)

    for name in ROTATED_KEYS:
        if name not in updated:
            output.append(f"{name}={secure_defaults[name]}")

    # ENV_FILE has no suffix (".env" is a bare stem), so with_suffix() would
    # produce ".env.env.<timestamp>.bak". Name the sibling file explicitly.
    backup = ENV_FILE.with_name(f"{ENV_FILE.name}.{int(time())}.bak")
    write_private_file(backup, ENV_FILE.read_text(encoding="utf-8"))

    ENV_FILE.write_text("\n".join(output) + "\n", encoding="utf-8")
    secure_private_file(ENV_FILE)
    settings = get_settings()
    session_factory = build_session_factory(settings.database_url)
    with session_factory() as session:
        session.execute(
            update(RefreshSession)
            .where(RefreshSession.revoked_at.is_(None))
            .values(revoked_at=int(time()))
        )
        session.commit()
    print(f"Backup written to {backup}")
    print("Secrets rotated. Restart the service to reload them.")


if __name__ == "__main__":
    rotate()
