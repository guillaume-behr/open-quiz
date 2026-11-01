"""Authentication, startup and administration: logins, two-factor, tokens and rate limits."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import new as hmac_new
from pathlib import Path
from threading import Barrier
from time import sleep, time

import jwt
import pyotp
import pytest
from fastapi import status
from fastapi.testclient import TestClient
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
from app.rate_limit import LoginRateLimiter
from app.routers.auth import REFRESH_COOKIE, REFRESH_PROOF_HEADER
from app.schemas import (
    LoginRequest,
    StudentLoginRequest,
)
from app.security import (
    DUMMY_PASSWORD_HASH,
    access_token_version,
    create_refresh_token,
    decode_access_token,
    decode_student_access_token,
    decode_two_factor_token,
    decrypt_totp_secret,
    hash_password,
    hash_refresh_token,
    refresh_request_proof,
)
from main import create_app
from scripts.reset_two_factor import reset

from support import (
    ADMIN_PASSWORD,
    JWT_SECRET,
    TEST_CLIENT_BACKEND_OPTIONS,
    TOTP_ENCRYPTION_KEY,
    complete_first_login,
    concurrent_writes,
    create_professor,
    database_connection,
    exam_environment,
    launch_and_join,
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
        assert response.json()["detail"]["code"] == "DATABASE_UNAVAILABLE"


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


@pytest.mark.parametrize(
    ("schema", "identity_field"),
    [
        (LoginRequest, "username"),
        (StudentLoginRequest, "identifier"),
    ],
)
def test_login_schemas_preserve_password_characters(
    schema, identity_field: str
) -> None:
    password = "  exact password value  "

    payload = schema.model_validate({identity_field: "account", "password": password})

    assert payload.password == password


@pytest.mark.parametrize(
    ("decoder", "payload"),
    [
        (
            decode_access_token,
            {"sub": "1", "type": "access", "ver": "version", "iat": 1},
        ),
        (
            decode_student_access_token,
            {
                "sub": "1",
                "type": "student_access",
                "ver": "version",
                "iat": 1,
            },
        ),
        (
            decode_two_factor_token,
            {
                "sub": "1",
                "type": "two_factor_verification",
                "jti": "token-id",
                "iat": 1,
            },
        ),
    ],
)
def test_signed_tokens_require_an_expiration_claim(decoder, payload) -> None:
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    with pytest.raises(jwt.MissingRequiredClaimError):
        decoder(token, JWT_SECRET)


def test_access_token_generation_permanently_invalidates_old_versions() -> None:
    password_hash = "stored-password-hash"
    assert access_token_version(password_hash, JWT_SECRET, 1) != (
        access_token_version(password_hash, JWT_SECRET, 0)
    )


def test_login_accepts_the_exact_configured_password_with_spaces(
    tmp_path: Path,
) -> None:
    exact_password = "  strong admin password 2026  "
    with make_client(
        settings_for(
            tmp_path / "password-characters.db",
            admin_password=exact_password,
        )
    ) as client:
        altered = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": exact_password.strip()},
        )
        accepted = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": exact_password},
        )

    assert altered.status_code == status.HTTP_401_UNAUTHORIZED
    assert accepted.status_code == status.HTTP_200_OK


def test_login_rate_limit_buckets_use_a_secret_key() -> None:
    subject = "password:identity:known-user"
    secret = "private-rate-limit-key"
    limiter = LoginRateLimiter(5, 900, secret)
    expected_digest = hmac_new(
        secret.encode(),
        subject.encode(),
        sha256,
    ).hexdigest()[: LoginRateLimiter.BUCKET_HEX_CHARACTERS]

    assert limiter._account_key(subject) == f"account:{expected_digest}"
    assert limiter._account_key(subject) != LoginRateLimiter(
        5,
        900,
        "different-private-key",
    )._account_key(subject)


def test_refresh_rotates_cookie_and_logout_revokes_it(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    with make_client(settings_for(database_path)) as client:
        _, secret = complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        first_refresh = client.cookies.get(REFRESH_COOKIE)
        assert first_refresh

        with database_connection(database_path) as database:
            created_at, first_expires_at = database.execute(
                "SELECT created_at, expires_at FROM refresh_sessions"
            ).fetchone()
        assert created_at is not None
        assert first_expires_at is not None

        refreshed = client.post(
            "/api/auth/refresh",
            headers=refresh_headers(client),
        )
        assert refreshed.status_code == 200
        second_refresh = client.cookies.get(REFRESH_COOKIE)
        assert second_refresh and second_refresh != first_refresh
        assert refreshed.json()["refresh_proof"] == refresh_request_proof(
            second_refresh,
            JWT_SECRET,
        )
        with database_connection(database_path) as database:
            second_expires_at = database.execute(
                "SELECT expires_at FROM refresh_sessions ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        assert second_expires_at == first_expires_at

        client.cookies.set(
            REFRESH_COOKIE,
            first_refresh,
            domain="testserver.local",
            path="/api/auth",
        )
        assert (
            client.post(
                "/api/auth/refresh",
                headers={
                    REFRESH_PROOF_HEADER: refresh_request_proof(
                        first_refresh,
                        JWT_SECRET,
                    )
                },
            ).status_code
            == 401
        )

        client.cookies.set(
            REFRESH_COOKIE,
            second_refresh,
            domain="testserver.local",
            path="/api/auth",
        )
        assert (
            client.post(
                "/api/auth/refresh",
                headers={
                    REFRESH_PROOF_HEADER: refresh_request_proof(
                        second_refresh,
                        JWT_SECRET,
                    )
                },
            ).status_code
            == 401
        )

        challenge = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        ).json()
        next_code = pyotp.TOTP(secret).at(time() + 30)
        assert (
            client.post(
                "/api/auth/2fa/verify",
                json={
                    "challenge_token": challenge["challenge_token"],
                    "code": next_code,
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/auth/logout",
                headers=refresh_headers(client),
            ).status_code
            == 204
        )
        assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_and_logout_require_the_session_proof(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "refresh-proof.db")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        assert client.post("/api/auth/refresh").status_code == 403
        assert (
            client.post(
                "/api/auth/refresh",
                headers={REFRESH_PROOF_HEADER: "invalid-proof"},
            ).status_code
            == 403
        )
        assert client.post("/api/auth/logout").status_code == 403

        refreshed = client.post(
            "/api/auth/refresh",
            headers=refresh_headers(client),
        )
        assert refreshed.status_code == 200


def test_later_login_requires_two_factor_code(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        _, secret = complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        assert (
            client.post(
                "/api/auth/logout",
                headers=refresh_headers(client),
            ).status_code
            == 204
        )

        login_response = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        challenge = login_response.json()
        assert challenge["status"] == "verification_required"
        assert challenge["secret"] is None
        assert challenge["provisioning_uri"] is None

        next_code = pyotp.TOTP(secret).at(time() + 30)
        verified = client.post(
            "/api/auth/2fa/verify",
            json={
                "challenge_token": challenge["challenge_token"],
                "code": next_code,
            },
        )
        assert verified.status_code == 200

        replayed = client.post(
            "/api/auth/2fa/verify",
            json={
                "challenge_token": challenge["challenge_token"],
                "code": next_code,
            },
        )
        assert replayed.status_code == 401


def test_new_device_requires_two_factor_while_known_device_is_restored(
    tmp_path: Path,
) -> None:
    app_settings = settings_for(tmp_path / "test.db")
    with make_client(app_settings) as known_device:
        complete_first_login(known_device, "root-admin", ADMIN_PASSWORD)
        assert (
            known_device.post(
                "/api/auth/refresh",
                headers=refresh_headers(known_device),
            ).status_code
            == 200
        )

    with make_client(app_settings) as new_device:
        login_response = new_device.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert login_response.status_code == 200
        assert login_response.json()["status"] == "verification_required"


def test_two_factor_recovery_requires_new_setup(tmp_path: Path) -> None:
    database = tmp_path / "test.db"
    app_settings = settings_for(database)
    with make_client(app_settings) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)

    assert reset("root-admin", app_settings)

    with make_client(app_settings) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert login_response.json()["status"] == "setup_required"


def test_login_rate_limit_and_origin_check(tmp_path: Path) -> None:
    app_settings = settings_for(tmp_path / "test.db", login_attempts=3)
    with make_client(app_settings) as client:
        for _ in range(3):
            response = client.post(
                "/api/auth/login",
                json={"username": "unknown", "password": "incorrect-password"},
            )
            assert response.status_code == 401

        limited = client.post(
            "/api/auth/login",
            json={"username": "unknown", "password": "incorrect-password"},
        )
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) > 0
        other_unknown = client.post(
            "/api/auth/login",
            json={"username": "another-unknown", "password": "incorrect-password"},
        )
        assert other_unknown.status_code == 401
        other_account = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert other_account.status_code == 200

        for _ in range(3):
            known_account_failure = client.post(
                "/api/auth/login",
                json={"username": "root-admin", "password": "incorrect-password"},
            )
            assert known_account_failure.status_code == 401
        correct_credentials = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert correct_credentials.status_code == 429

    with make_client(app_settings) as client:
        still_limited = client.post(
            "/api/auth/login",
            json={"username": "unknown", "password": "incorrect-password"},
        )
        assert still_limited.status_code == 429

    with TestClient(
        create_app(settings_for(tmp_path / "origin.db")),
        backend_options=TEST_CLIENT_BACKEND_OPTIONS,
    ) as client:
        missing = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert missing.status_code == 403
        rejected = client.post(
            "/api/auth/login",
            headers={"Origin": "https://attacker.example"},
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert rejected.status_code == 403


def test_development_accepts_local_vite_origin_on_another_port(
    tmp_path: Path,
) -> None:
    app_settings = settings_for(
        tmp_path / "development.db",
        environment="development",
    )
    with TestClient(
        create_app(app_settings),
        headers={"Origin": "http://localhost:5174"},
        backend_options=TEST_CLIENT_BACKEND_OPTIONS,
    ) as client:
        accepted = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert accepted.status_code == 200

    with TestClient(
        create_app(app_settings),
        headers={"Origin": "http://attacker.example"},
        backend_options=TEST_CLIENT_BACKEND_OPTIONS,
    ) as client:
        rejected = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert rejected.status_code == 403


def test_login_rate_limit_reserves_concurrent_attempts_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_settings = settings_for(tmp_path / "test.db", login_attempts=3)
    barrier = Barrier(8)

    def slow_invalid_password(_: str, __: str) -> bool:
        sleep(0.1)
        return False

    monkeypatch.setattr(
        "app.routers.auth.verify_password",
        slow_invalid_password,
    )

    with make_client(app_settings) as client:

        def attempt_login() -> int:
            barrier.wait()
            return client.post(
                "/api/auth/login",
                json={"username": "unknown", "password": "incorrect-password"},
            ).status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(attempt_login) for _ in range(8)]
            statuses = [future.result() for future in futures]

    assert statuses.count(401) <= 3
    assert statuses.count(429) >= 5


def test_global_auth_rate_limit_is_shared_across_login_flows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_settings = settings_for(
        tmp_path / "global-auth-limit.db",
        global_login_attempts=50,
    )
    monkeypatch.setattr("app.routers.auth.verify_password", lambda *_: False)
    monkeypatch.setattr("app.routers.student_auth.verify_password", lambda *_: False)

    with make_client(app_settings) as client:
        for attempt in range(49):
            response = client.post(
                "/api/auth/login",
                json={
                    "username": f"unknown-{attempt}",
                    "password": "incorrect-password",
                },
            )
            assert response.status_code == 401

        student_response = client.post(
            "/api/student-auth/login",
            json={"identifier": "unknown", "password": "incorrect-password"},
        )
        assert student_response.status_code == 401

        limited = client.post(
            "/api/auth/login",
            json={"username": "another-account", "password": "incorrect-password"},
        )

    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


def test_an_exhausted_global_budget_still_admits_a_known_teacher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An anonymous flood must not lock real teachers out of their instance."""
    app_settings = settings_for(
        tmp_path / "global-auth-floor.db",
        global_login_attempts=50,
    )
    with make_client(app_settings) as client:
        monkeypatch.setattr(
            "app.routers.auth.verify_password",
            lambda password, _: password == ADMIN_PASSWORD,
        )
        for attempt in range(50):
            client.post(
                "/api/auth/login",
                json={
                    "username": f"unknown-{attempt}",
                    "password": "incorrect-password",
                },
            )

        unknown = client.post(
            "/api/auth/login",
            json={"username": "still-unknown", "password": "incorrect-password"},
        )
        assert unknown.status_code == 429
        assert unknown.json()["detail"]["code"] == "AUTH_RATE_LIMITED"

        admitted = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert admitted.status_code == 200
        assert admitted.json()["status"] == "setup_required"

        # The floor admits the account, it does not excuse it from the password
        # check or from its own per-account budget.
        rejected = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": "incorrect-password"},
        )
        assert rejected.status_code == 401
        assert rejected.json()["detail"]["code"] == "AUTH_INVALID_CREDENTIALS"


def test_an_exhausted_global_budget_admits_only_active_students(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_settings = settings_for(
        tmp_path / "global-auth-floor-student.db",
        global_login_attempts=50,
    )
    with make_client(app_settings) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "floor.teacher",
                    "display_name": "Floor Teacher",
                    "password": "a-secure-teacher-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client,
            "floor.teacher",
            "a-secure-teacher-password",
        )
        account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={"first_name": "Floor", "last_name": "Student"},
        ).json()
        student_password = account["generated_password"]

        monkeypatch.setattr("app.routers.auth.verify_password", lambda *_: False)
        monkeypatch.setattr(
            "app.routers.student_auth.verify_password",
            lambda password, _: password == student_password,
        )
        for attempt in range(50):
            client.post(
                "/api/auth/login",
                json={
                    "username": f"unknown-{attempt}",
                    "password": "incorrect-password",
                },
            )

        unknown = client.post(
            "/api/student-auth/login",
            json={"identifier": "unknown.student", "password": "incorrect-password"},
        )
        assert unknown.status_code == 429

        admitted = client.post(
            "/api/student-auth/login",
            json={"identifier": account["identifier"], "password": student_password},
        )
        assert admitted.status_code == 200

        assert (
            client.post(
                f"/api/students/{account['id']}/update",
                headers=teacher_headers,
                json={
                    "identifier": account["identifier"],
                    "display_name": account["display_name"],
                    "is_active": False,
                },
            ).status_code
            == 200
        )
        # A disabled account is not a user the instance needs to keep serving,
        # so it falls back behind the budget like any unknown identifier.
        disabled = client.post(
            "/api/student-auth/login",
            json={"identifier": account["identifier"], "password": student_password},
        )
        assert disabled.status_code == 429


def test_correct_password_does_not_reset_two_factor_throttling(
    tmp_path: Path,
) -> None:
    app_settings = settings_for(tmp_path / "two-factor-limit.db", login_attempts=3)
    with make_client(app_settings) as client:
        _, secret = complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        assert (
            client.post(
                "/api/auth/logout",
                headers=refresh_headers(client),
            ).status_code
            == 204
        )
        challenge = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        ).json()
        valid_code = pyotp.TOTP(secret).at(time() + 30)
        invalid_code = "000000" if valid_code != "000000" else "111111"
        for _ in range(3):
            failed = client.post(
                "/api/auth/2fa/verify",
                json={
                    "challenge_token": challenge["challenge_token"],
                    "code": invalid_code,
                },
            )
            assert failed.status_code == 401

        replacement_challenge = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        ).json()
        limited = client.post(
            "/api/auth/2fa/verify",
            json={
                "challenge_token": replacement_challenge["challenge_token"],
                "code": valid_code,
            },
        )
        assert limited.status_code == 429


def test_two_factor_code_and_challenge_are_consumed_atomically(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        _, secret = complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        assert (
            client.post(
                "/api/auth/logout",
                headers=refresh_headers(client),
            ).status_code
            == 204
        )
        challenge = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        ).json()["challenge_token"]
        code = pyotp.TOTP(secret).at(time() + 30)
        barrier = Barrier(2)

        def verify() -> int:
            barrier.wait()
            return client.post(
                "/api/auth/2fa/verify",
                json={"challenge_token": challenge, "code": code},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(
                future.result() for future in (pool.submit(verify), pool.submit(verify))
            )
        assert statuses == [200, 401]


def test_student_login_verifies_password_for_unknown_accounts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifications: list[tuple[str, str]] = []

    def spy(password: str, encoded: str) -> bool:
        verifications.append((password, encoded))
        return False

    monkeypatch.setattr("app.routers.student_auth.verify_password", spy)
    with make_client(settings_for(tmp_path / "student-timing.db")) as client:
        response = client.post(
            "/api/student-auth/login",
            json={"identifier": "ghost.student", "password": "wrong-password"},
        )

    assert response.status_code == 401
    # The verification must run even for unknown identifiers so the response
    # time does not reveal whether the account exists.
    assert verifications == [("wrong-password", DUMMY_PASSWORD_HASH)]


@pytest.mark.parametrize(
    ("decoder", "payload"),
    [
        (decode_access_token, {"type": "student_access", "ver": "v"}),
        (decode_access_token, {"type": "two_factor_setup", "ver": "v"}),
        (decode_student_access_token, {"type": "access", "ver": "v"}),
        (decode_student_access_token, {"type": "two_factor_setup", "ver": "v"}),
        (decode_two_factor_token, {"type": "access", "jti": "identifier"}),
        (decode_two_factor_token, {"type": "student_access", "jti": "identifier"}),
    ],
)
def test_signed_tokens_are_refused_for_another_purpose(decoder, payload) -> None:
    """Every token is signed with the same key, so only `type` separates them.

    Without this check a two-factor challenge, which is issued before any code
    is verified, would be accepted wherever an access token is expected.
    """
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "1", "iat": now, "exp": now + timedelta(minutes=5), **payload},
        JWT_SECRET,
        algorithm="HS256",
    )

    with pytest.raises(jwt.InvalidTokenError):
        decoder(token, JWT_SECRET)


@pytest.mark.parametrize("version", ["", 1, None, []])
def test_access_tokens_require_a_usable_version_claim(version) -> None:
    """A blank or non-textual version cannot be compared against the stored one."""
    now = datetime.now(UTC)
    payload = {
        "sub": "1",
        "type": "access",
        "ver": version,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, JWT_SECRET)

    student_token = jwt.encode(
        {**payload, "type": "student_access"}, JWT_SECRET, algorithm="HS256"
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_student_access_token(student_token, JWT_SECRET)


@pytest.mark.parametrize("token_id", ["", 1, None])
def test_two_factor_tokens_require_a_usable_identifier(token_id) -> None:
    """The identifier is hashed into the single-use challenge record."""
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "1",
            "type": "two_factor_verification",
            "jti": token_id,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        JWT_SECRET,
        algorithm="HS256",
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_two_factor_token(token, JWT_SECRET)


def test_a_two_factor_challenge_is_not_accepted_as_an_access_token(
    tmp_path: Path,
) -> None:
    """The challenge is handed out before the code is checked.

    It authenticates nothing on its own, so presenting it as a bearer token
    must not reach an authenticated route.
    """
    with make_client(settings_for(tmp_path / "challenge-token.db")) as client:
        started = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert started.status_code == 200
        challenge_token = started.json()["challenge_token"]

        refused = client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {challenge_token}"},
        )
        assert refused.status_code == 401


def test_a_student_token_does_not_open_the_teacher_api(tmp_path: Path) -> None:
    """Both audiences send a bearer token signed with the same key."""
    with make_client(settings_for(tmp_path / "audience-token.db")) as client:
        environment = exam_environment(client)
        student_headers = environment["student_headers"]

        refused = client.get("/api/users/me", headers=student_headers)
        assert refused.status_code == 401
        assert refused.json()["detail"]["code"] == "AUTH_TOKEN_INVALID"
        assert client.get("/api/classes", headers=student_headers).status_code == 401
        assert (
            client.get("/api/admin/users", headers=student_headers).status_code == 401
        )

        # And the teacher's own token is refused by the student API.
        teacher_token = environment["teacher_headers"]["Authorization"]
        assert (
            client.get(
                "/api/student-auth/me", headers={"Authorization": teacher_token}
            ).status_code
            == 401
        )


def test_teacher_unlocks_a_student_locked_out_by_failed_logins(
    tmp_path: Path,
) -> None:
    settings = settings_for(tmp_path / "student-unlock.db", login_attempts=3)
    with make_client(settings) as client:
        environment = exam_environment(client)
        account = environment["account"]
        credentials = {
            "identifier": account["identifier"],
            "password": account["generated_password"],
        }
        # A classmate who guesses the identifier exhausts its attempts.
        for _ in range(3):
            failed = client.post(
                "/api/student-auth/login",
                json={**credentials, "password": "not-the-password"},
            )
            assert failed.status_code == 401
        locked = client.post("/api/student-auth/login", json=credentials)
        assert locked.status_code == 429

        saved = client.post(
            f"/api/students/{account['id']}/update",
            headers=environment["teacher_headers"],
            json={
                "identifier": account["identifier"],
                "display_name": account["display_name"],
                "is_active": True,
            },
        )
        assert saved.status_code == 200
        assert (
            client.post("/api/student-auth/login", json=credentials).status_code == 200
        )

        # Renaming the identifier releases the new name as well.
        for _ in range(3):
            client.post(
                "/api/student-auth/login",
                json={"identifier": "edge.renamed", "password": "not-the-password"},
            )
        renamed = client.post(
            f"/api/students/{account['id']}/update",
            headers=environment["teacher_headers"],
            json={
                "identifier": "edge.renamed",
                "display_name": account["display_name"],
                "is_active": True,
            },
        )
        assert renamed.status_code == 200
        assert (
            client.post(
                "/api/student-auth/login",
                json={**credentials, "identifier": "edge.renamed"},
            ).status_code
            == 200
        )


def test_student_logout_revokes_tokens_but_keeps_quiz_participation(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "student-logout.db")) as client:
        environment = exam_environment(client)
        quiz_session, participant_headers = launch_and_join(client, environment)
        student_headers = environment["student_headers"]

        logged_out = client.post("/api/student-auth/logout", headers=student_headers)
        assert logged_out.status_code == 204
        assert (
            client.get("/api/student-auth/me", headers=student_headers).status_code
            == 401
        )
        assert (
            client.post("/api/student-auth/logout", headers=student_headers).status_code
            == 401
        )
        assert (
            client.get(
                f"/api/quizzes/student/sessions/{quiz_session['join_code']}",
                headers=participant_headers,
            ).status_code
            == 200
        )
        relogin = client.post(
            "/api/student-auth/login",
            json={
                "identifier": environment["account"]["identifier"],
                "password": environment["account"]["generated_password"],
            },
        )
        assert relogin.status_code == 200
