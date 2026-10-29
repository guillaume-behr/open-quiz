"""Startup, authentication and administration paths outside the main flows."""

from dataclasses import replace
from pathlib import Path
from time import sleep, time

import pyotp
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError

import main
from app.database import build_session_factory
from app.models import (
    AuthenticationChallenge,
    GradeLevel,
    RefreshSession,
    RefreshSessionFamily,
    SecurityState,
    TwoFactorCredential,
    User,
)
from app.routers.auth import REFRESH_COOKIE, REFRESH_PROOF_HEADER
from app.security import (
    create_refresh_token,
    decrypt_totp_secret,
    hash_password,
    hash_refresh_token,
    refresh_request_proof,
)

from support import (
    ADMIN_PASSWORD,
    JWT_SECRET,
    TOTP_ENCRYPTION_KEY,
    complete_first_login,
    concurrent_writes,
    create_professor,
    login_admin,
    make_client,
    refresh_headers,
    settings_for,
)


def seed_refresh_session(
    session_factory, user_id: int, *, with_family: bool, revoked: bool = False
) -> str:
    raw_token = create_refresh_token()
    with session_factory() as session:
        stored = RefreshSession(
            token_hash=hash_refresh_token(raw_token),
            user_id=user_id,
            expires_at=int(time()) + 3600,
            revoked_at=int(time()) if revoked else None,
        )
        session.add(stored)
        session.flush()
        if with_family:
            session.add(
                RefreshSessionFamily(session_id=stored.id, family_id=f"f{stored.id}")
            )
        session.commit()
    return raw_token


def use_refresh_token(client, raw_token: str) -> dict[str, str]:
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, raw_token, path="/api/auth")
    return {REFRESH_PROOF_HEADER: refresh_request_proof(raw_token, JWT_SECRET)}


def add_user(session_factory, username: str, *, is_admin: bool) -> int:
    with session_factory() as session:
        user = User(
            username=username,
            display_name=username,
            password_hash=hash_password("an-unused-password-value"),
            is_admin=is_admin,
        )
        session.add(user)
        session.commit()
        return user.id


def test_first_startup_revokes_sessions_that_predate_session_families(
    tmp_path: Path,
) -> None:
    settings = settings_for(tmp_path / "legacy-sessions")
    session_factory = build_session_factory(settings.database_url)
    user_id = add_user(session_factory, "root-admin", is_admin=True)
    seed_refresh_session(session_factory, user_id, with_family=False)

    main.synchronize_security_state(session_factory, settings)

    with session_factory() as session:
        assert session.scalar(select(RefreshSession.revoked_at)) is not None


def test_a_rotated_jwt_secret_revokes_every_session(tmp_path: Path) -> None:
    settings = settings_for(tmp_path / "rotated-secret")
    session_factory = build_session_factory(settings.database_url)
    main.synchronize_security_state(session_factory, settings)
    with session_factory() as session:
        admin_id = session.scalar(select(User.id).where(User.is_admin.is_(True)))
    seed_refresh_session(session_factory, admin_id, with_family=True)

    rotated = settings_for(
        tmp_path / "rotated-secret",
        jwt_secret="another-secret-with-plenty-of-variety-2026",
    )
    main.synchronize_security_state(session_factory, rotated)

    with session_factory() as session:
        assert session.scalar(select(RefreshSession.revoked_at)) is not None


def test_a_single_unmanaged_administrator_takes_the_configured_name(
    tmp_path: Path,
) -> None:
    settings = settings_for(tmp_path / "unmanaged-admin")
    session_factory = build_session_factory(settings.database_url)
    admin_id = add_user(session_factory, "legacy-admin", is_admin=True)

    main.synchronize_security_state(session_factory, settings)

    with session_factory() as session:
        assert session.get(User, admin_id).username == "root-admin"


@pytest.mark.parametrize(
    ("managed_value", "message"),
    [
        ("not-a-number", "state is invalid"),
        ("999999", "account is missing"),
        ("other", "belongs to a different account"),
    ],
)
def test_startup_refuses_an_inconsistent_managed_administrator(
    tmp_path: Path, managed_value: str, message: str
) -> None:
    settings = settings_for(tmp_path / "managed-admin")
    session_factory = build_session_factory(settings.database_url)
    if managed_value == "other":
        managed_value = str(add_user(session_factory, "managed", is_admin=True))
        add_user(session_factory, "root-admin", is_admin=False)
    with session_factory() as session:
        session.add(SecurityState(key=main.MANAGED_ADMIN_KEY, value=managed_value))
        session.commit()

    with pytest.raises(RuntimeError, match=message):
        main.synchronize_security_state(session_factory, settings)


def test_complete_production_public_information_is_not_reported(
    tmp_path: Path,
) -> None:
    settings = settings_for(
        tmp_path / "public-information",
        **{attribute: "Filled" for _, attribute in main.PUBLIC_INFORMATION_VARIABLES},
    )
    production = replace(
        settings,
        environment="production",
        frontend_origin="https://quiz.example.org",
    )
    assert main.warn_missing_public_information(production) == []


def test_retention_maintenance_runs_periodically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs: list[int] = []
    enforce = main.enforce_data_retention

    def counting_enforce(session_factory, settings) -> None:
        runs.append(1)
        enforce(session_factory, settings)

    monkeypatch.setattr(main, "RETENTION_MAINTENANCE_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(main, "enforce_data_retention", counting_enforce)
    with make_client(settings_for(tmp_path / "maintenance")) as client:
        deadline = time() + 5
        while len(runs) < 3 and time() < deadline:
            sleep(0.01)
        assert client.get("/docs").headers.get("Cache-Control") != "no-store"
    assert len(runs) >= 3


def test_health_reports_an_unavailable_database(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "health-down")) as client:

        def broken_session():
            raise SQLAlchemyError("database is down")

        client.app.state.session_factory = broken_session
        response = client.get("/api/health")
        assert response.status_code == 503


def test_refresh_and_logout_edge_cases(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "refresh-edges")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        session_factory = client.app.state.session_factory
        with session_factory() as session:
            admin_id = session.scalar(select(User.id).where(User.is_admin.is_(True)))

        unknown = use_refresh_token(client, "unknown-token")
        assert client.post("/api/auth/refresh", headers=unknown).status_code == 401

        legacy = seed_refresh_session(session_factory, admin_id, with_family=False)
        refreshed = client.post(
            "/api/auth/refresh", headers=use_refresh_token(client, legacy)
        )
        assert refreshed.status_code == 200

        revoked = seed_refresh_session(
            session_factory, admin_id, with_family=False, revoked=True
        )
        replayed = client.post(
            "/api/auth/refresh", headers=use_refresh_token(client, revoked)
        )
        assert replayed.status_code == 401

        raced = seed_refresh_session(session_factory, admin_id, with_family=True)
        with concurrent_writes(
            client,
            (
                "UPDATE refresh_sessions SET revoked_at",
                lambda connection: connection.execute(
                    update(RefreshSession)
                    .where(RefreshSession.token_hash == hash_refresh_token(raced))
                    .values(revoked_at=int(time()))
                ),
            ),
        ) as fired:
            lost = client.post(
                "/api/auth/refresh", headers=use_refresh_token(client, raced)
            )
        assert fired
        assert lost.status_code == 401

        client.cookies.clear()
        assert client.post("/api/auth/logout").status_code == 204


def test_refresh_is_refused_once_the_account_is_disabled(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "refresh-disabled")) as client:
        admin_headers = login_admin(client)
        professor, _ = create_professor(client, admin_headers)
        teacher_refresh = refresh_headers(client)
        with client.app.state.session_factory() as session:
            session.execute(
                update(User).where(User.id == professor["id"]).values(is_active=False)
            )
            session.commit()
        response = client.post("/api/auth/refresh", headers=teacher_refresh)
        assert response.status_code == 401


def test_an_account_keeps_at_most_ten_active_sessions(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "session-cap")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        session_factory = client.app.state.session_factory
        with session_factory() as session:
            admin_id = session.scalar(select(User.id).where(User.is_admin.is_(True)))
        for _ in range(10):
            seed_refresh_session(session_factory, admin_id, with_family=True)
        client.cookies.clear()
        challenge = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        ).json()
        assert challenge["status"] == "verification_required"
        with session_factory() as session:
            secret_row = session.get(TwoFactorCredential, admin_id)
            session.execute(
                update(TwoFactorCredential)
                .where(TwoFactorCredential.user_id == admin_id)
                .values(last_counter=None)
            )
            session.commit()
        secret = decrypt_totp_secret(secret_row.encrypted_secret, TOTP_ENCRYPTION_KEY)
        verified = client.post(
            "/api/auth/2fa/verify",
            json={
                "challenge_token": challenge["challenge_token"],
                "code": pyotp.TOTP(secret).now(),
            },
        )
        assert verified.status_code == 200
        with session_factory() as session:
            active = session.scalars(
                select(RefreshSession.id).where(RefreshSession.revoked_at.is_(None))
            ).all()
        assert len(active) == 10


def test_two_factor_setup_can_restart_and_survive_failures(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "two-factor-edges")) as client:
        credentials = {"username": "root-admin", "password": ADMIN_PASSWORD}
        first = client.post("/api/auth/login", json=credentials).json()
        restarted = client.post("/api/auth/login", json=credentials).json()
        assert restarted["status"] == "setup_required"
        assert restarted["secret"] != first["secret"]

        malformed = client.post(
            "/api/auth/2fa/verify",
            json={"challenge_token": "not-a-token", "code": "123456"},
        )
        assert malformed.status_code == 401
        assert malformed.json()["detail"]["code"] == "AUTH_2FA_CHALLENGE_INVALID"

        session_factory = client.app.state.session_factory
        with session_factory() as session:
            session.execute(
                update(TwoFactorCredential).values(encrypted_secret="corrupted")
            )
            session.commit()
        unreadable = client.post(
            "/api/auth/2fa/verify",
            json={"challenge_token": restarted["challenge_token"], "code": "123456"},
        )
        assert unreadable.status_code == 500
        assert unreadable.json()["detail"]["code"] == "AUTH_2FA_UNAVAILABLE"

        retry = client.post("/api/auth/login", json=credentials).json()
        with concurrent_writes(
            client,
            (
                "UPDATE authentication_challenges SET used_at",
                lambda connection: connection.execute(
                    update(AuthenticationChallenge).values(used_at=int(time()))
                ),
            ),
        ) as fired:
            raced = client.post(
                "/api/auth/2fa/verify",
                json={
                    "challenge_token": retry["challenge_token"],
                    "code": pyotp.TOTP(retry["secret"]).now(),
                },
            )
        assert fired
        assert raced.status_code == 401
        assert raced.json()["detail"]["code"] == "AUTH_2FA_CHALLENGE_INVALID"


def test_admin_account_management_edge_cases(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "admin-edges")) as client:
        admin_headers = login_admin(client)
        professor, _ = create_professor(client, admin_headers)

        unchanged = client.post(
            f"/api/admin/users/{professor['id']}/status",
            headers=admin_headers,
            json={"is_active": True},
        )
        assert unchanged.status_code == 200
        assert unchanged.json()["is_active"] is True

        reset = client.post(
            f"/api/admin/users/{professor['id']}/credentials",
            headers=admin_headers,
            json={"password": "another-secure-password", "reset_two_factor": False},
        )
        assert reset.status_code == 200
        with client.app.state.session_factory() as session:
            assert session.get(TwoFactorCredential, professor["id"]) is not None

        missing_report = client.delete(
            "/api/problem-reports/999999", headers=admin_headers
        )
        assert missing_report.status_code == 404


def test_student_login_is_rate_limited_per_identifier(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "student-limit", login_attempts=3)) as (
        client
    ):
        statuses = [
            client.post(
                "/api/student-auth/login",
                json={"identifier": "nobody", "password": "wrong-password"},
            ).status_code
            for _ in range(4)
        ]
        assert statuses == [401, 401, 401, 429]


def test_grade_levels_survive_concurrent_creation(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "grade-race")) as client:
        admin_headers = login_admin(client)
        professor, headers = create_professor(client, admin_headers)
        owner_id = professor["id"]
        with client.app.state.session_factory() as session:
            session.execute(text("DELETE FROM grade_levels"))
            session.commit()

        def insert_level(name: str):
            return lambda connection: connection.execute(
                GradeLevel.__table__.insert().values(owner_id=owner_id, name=name)
            )

        with concurrent_writes(
            client, ("INSERT INTO grade_levels", insert_level("2nd"))
        ) as fired:
            listed = client.get("/api/grade-levels", headers=headers)
        assert fired
        assert listed.status_code == 200
        assert [level["name"] for level in listed.json()] == ["2nd"]

        with concurrent_writes(
            client, ("INSERT INTO grade_levels", insert_level("CM2"))
        ) as fired:
            created = client.post(
                "/api/grade-levels", headers=headers, json={"name": "CM2"}
            )
        assert fired
        assert created.status_code == 201
        assert created.json()["name"] == "CM2"

        with (
            concurrent_writes(
                client,
                ("INSERT INTO grade_levels", insert_level("CM1")),
                (
                    "SELECT grade_levels",
                    lambda connection: connection.execute(
                        text("DELETE FROM grade_levels WHERE name = 'CM1'")
                    ),
                ),
            ) as fired,
            pytest.raises(Exception, match="uq_grade_level_owner_name"),
        ):
            client.post("/api/grade-levels", headers=headers, json={"name": "CM1"})
        assert len(fired) == 2


def test_a_two_factor_code_used_concurrently_is_refused(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "two-factor-counter")) as client:
        challenge = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        ).json()
        with concurrent_writes(
            client,
            (
                "UPDATE two_factor_credentials SET",
                lambda connection: connection.execute(
                    update(TwoFactorCredential).values(last_counter=2**31 - 1)
                ),
            ),
        ) as fired:
            response = client.post(
                "/api/auth/2fa/verify",
                json={
                    "challenge_token": challenge["challenge_token"],
                    "code": pyotp.TOTP(challenge["secret"]).now(),
                },
            )
        assert fired
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "AUTH_2FA_CODE_USED"
