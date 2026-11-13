"""Security state the application reconciles with its settings at startup.

Every worker runs synchronize_security_state() before serving: it revokes the
long sessions when JWT_SECRET changes and keeps the one administrator that
ADMIN_USERNAME and ADMIN_PASSWORD manage in line with them.
"""

from hashlib import sha256
from hmac import new as hmac_new
from time import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import audit_event
from app.config import Settings
from app.database import MAINTENANCE_LOCK_KEY
from app.models import RefreshSession, RefreshSessionFamily, SecurityState, User
from app.security import hash_password, verify_password
from app.services.credentials import revoke_refresh_sessions, revoke_user_sessions

JWT_FINGERPRINT_KEY = "jwt_secret_fingerprint"
MANAGED_ADMIN_KEY = "managed_admin_user_id"


def jwt_secret_fingerprint(settings: Settings) -> str:
    """A fingerprint of JWT_SECRET alone, so other keys can rotate freely."""
    return hmac_new(
        settings.jwt_secret.encode(), b"jwt-secret-fingerprint", sha256
    ).hexdigest()


def former_jwt_secret_fingerprint(settings: Settings) -> str:
    """The fingerprint earlier releases stored, keyed by TOTP_ENCRYPTION_KEY."""
    return hmac_new(
        settings.totp_encryption_key.encode(),
        settings.jwt_secret.encode(),
        sha256,
    ).hexdigest()


def revoke_sessions_on_jwt_rotation(
    session: Session, settings: Settings, now: int
) -> None:
    """Revoke every long session once JWT_SECRET has changed."""
    fingerprint = jwt_secret_fingerprint(settings)
    fingerprint_state = session.get(SecurityState, JWT_FINGERPRINT_KEY)
    if fingerprint_state is None:
        unmapped_session = session.scalar(
            select(RefreshSession.id)
            .outerjoin(
                RefreshSessionFamily,
                RefreshSessionFamily.session_id == RefreshSession.id,
            )
            .where(
                RefreshSession.revoked_at.is_(None),
                RefreshSessionFamily.session_id.is_(None),
            )
            .limit(1)
        )
        if unmapped_session is not None:
            revoke_refresh_sessions(session, now)
            audit_event("security.legacy_sessions_revoked")
        session.add(SecurityState(key=JWT_FINGERPRINT_KEY, value=fingerprint))
    elif fingerprint_state.value == former_jwt_secret_fingerprint(settings):
        # Stored by an earlier release for the same secrets: carry it over.
        fingerprint_state.value = fingerprint
    elif fingerprint_state.value != fingerprint:
        revoke_refresh_sessions(session, now)
        fingerprint_state.value = fingerprint
        audit_event("security.jwt_secret_rotated_sessions_revoked")


def managed_administrator(session: Session, settings: Settings, now: int) -> User:
    """The one administrator ADMIN_USERNAME and ADMIN_PASSWORD manage.

    At the first start it adopts or creates that account and disables any
    other administrator; afterwards it follows ADMIN_USERNAME renames.
    """
    managed_state = session.get(SecurityState, MANAGED_ADMIN_KEY)
    configured_user = session.scalar(
        select(User).where(User.username == settings.admin_username)
    )
    if managed_state is None:
        administrators = list(
            session.scalars(select(User).where(User.is_admin.is_(True)))
        )
        if configured_user is not None and not configured_user.is_admin:
            # Adopting it would overwrite a teacher's password and lock them
            # out of their quizzes and classes.
            raise RuntimeError(
                "ADMIN_USERNAME belongs to a teacher account; choose another "
                "username before starting the application"
            )
        if configured_user is not None:
            admin_user = configured_user
        elif len(administrators) == 1:
            admin_user = administrators[0]
            admin_user.username = settings.admin_username
        elif administrators:
            raise RuntimeError(
                "Multiple unmanaged administrators exist; resolve them "
                "before starting the application"
            )
        else:
            admin_user = User(
                username=settings.admin_username,
                display_name="Administrator",
                password_hash=hash_password(settings.admin_password),
                is_admin=True,
            )
            session.add(admin_user)
            session.flush()

        for stale_admin in administrators:
            if stale_admin.id != admin_user.id:
                stale_admin.is_admin = False
                stale_admin.is_active = False
                revoke_user_sessions(session, stale_admin.id, now)
                audit_event(
                    "security.stale_administrator_disabled",
                    user_id=stale_admin.id,
                )
        session.add(
            SecurityState(
                key=MANAGED_ADMIN_KEY,
                value=str(admin_user.id),
            )
        )
    else:
        try:
            managed_user_id = int(managed_state.value)
        except ValueError as error:
            raise RuntimeError("Managed administrator state is invalid") from error
        managed_user = session.get(User, managed_user_id)
        if managed_user is None:
            raise RuntimeError("The managed administrator account is missing")
        admin_user = managed_user
        if configured_user is not None and configured_user.id != admin_user.id:
            raise RuntimeError(
                "ADMIN_USERNAME belongs to a different account; choose a "
                "unique username before starting the application"
            )
        if admin_user.username != settings.admin_username:
            previous_username = admin_user.username
            admin_user.username = settings.admin_username
            audit_event(
                "security.managed_administrator_renamed",
                user_id=admin_user.id,
                previous_username=previous_username,
            )
    return admin_user


def apply_administrator_settings(
    admin_user: User, session: Session, settings: Settings, now: int
) -> None:
    """Keep the managed account active, and on ADMIN_PASSWORD."""
    admin_user.is_admin = True
    admin_user.is_active = True
    if not verify_password(settings.admin_password, admin_user.password_hash):
        admin_user.password_hash = hash_password(settings.admin_password)
        revoke_user_sessions(session, admin_user.id, now)
        audit_event(
            "security.administrator_password_rotated_sessions_revoked",
            user_id=admin_user.id,
        )


def synchronize_security_state(
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    now = int(time())
    with session_factory() as session:
        # Every worker runs this at startup: one at a time.
        session.execute(select(func.pg_advisory_xact_lock(MAINTENANCE_LOCK_KEY)))
        revoke_sessions_on_jwt_rotation(session, settings, now)
        admin_user = managed_administrator(session, settings, now)
        apply_administrator_settings(admin_user, session, settings, now)
        session.commit()
