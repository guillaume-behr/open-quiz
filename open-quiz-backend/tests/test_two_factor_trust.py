"""A browser that passed two-factor login today, and the daily cap on codes."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import time
from zoneinfo import ZoneInfo

import jwt
import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth_guards import (
    password_rate_subject,
    trusted_password_rate_subject,
    two_factor_rate_subject,
)
from app.models import (
    AuthenticationChallenge,
    LoginRateLimit,
    RefreshSession,
    TwoFactorCredential,
)
from app.routers.auth import TWO_FACTOR_TRUST_COOKIE, TWO_FACTOR_TRUST_COOKIE_PATH
from app.schemas import TwoFactorVerifyRequest
from app.security import (
    TWO_FACTOR_TRUST_MAXIMUM,
    create_access_token,
    create_two_factor_trust_token,
    decode_two_factor_trust_token,
    end_of_trusted_day,
    resolve_timezone,
)
from scripts.reset_two_factor import reset

from support import (
    ADMIN_PASSWORD,
    JWT_SECRET,
    complete_first_login,
    create_professor,
    forget_trusted_browser,
    login_admin,
    make_client,
    refresh_headers,
    settings_for,
)


def log_in(client: TestClient, username: str, password: str):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )


def log_out(client: TestClient) -> None:
    assert (
        client.post("/api/auth/logout", headers=refresh_headers(client)).status_code
        == 204
    )


def trust_cookie_header(response) -> str:
    return next(
        header
        for header in response.headers.get_list("set-cookie")
        if header.startswith(f"{TWO_FACTOR_TRUST_COOKIE}=")
    )


def test_a_trusted_browser_signs_in_without_a_code(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        log_out(client)

        signed_in = log_in(client, "root-admin", ADMIN_PASSWORD)
        assert signed_in.status_code == 200
        body = signed_in.json()
        assert body["status"] == "authenticated"
        assert "challenge_token" not in body
        assert body["refresh_proof"]
        me = client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["username"] == "root-admin"
        # The session is a real one: it refreshes like any other.
        assert (
            client.post(
                "/api/auth/refresh", headers=refresh_headers(client)
            ).status_code
            == 200
        )
        # Skipping the code does not extend the trust past the original day.
        assert TWO_FACTOR_TRUST_COOKIE not in signed_in.headers.get("set-cookie", "")


def test_the_trust_cookie_is_private_and_scoped_to_login(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        secret = response.json()["secret"]
        verified = client.post(
            "/api/auth/2fa/verify",
            json={
                "challenge_token": response.json()["challenge_token"],
                "code": pyotp.TOTP(secret).now(),
                "timezone": "Europe/Paris",
            },
        )
        assert verified.status_code == 200
        header = trust_cookie_header(verified)
        assert "HttpOnly" in header
        assert "SameSite=strict" in header
        assert f"Path={TWO_FACTOR_TRUST_COOKIE_PATH}" in header
        max_age = int(header.split("Max-Age=")[1].split(";")[0])
        assert 0 < max_age <= TWO_FACTOR_TRUST_MAXIMUM.total_seconds()


def test_a_wrong_password_is_refused_on_a_trusted_browser(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        refused = log_in(client, "root-admin", "not-the-admin-password")
        assert refused.status_code == 401


def test_wrong_passwords_from_elsewhere_do_not_lock_out_a_trusted_browser(
    tmp_path: Path,
) -> None:
    app_settings = settings_for(tmp_path / "test.db", login_attempts=3)
    with make_client(app_settings) as owner:
        complete_first_login(owner, "root-admin", ADMIN_PASSWORD)
        log_out(owner)
        with make_client(app_settings) as stranger:
            for _ in range(3):
                refused = log_in(stranger, "root-admin", "not-the-admin-password")
                assert refused.status_code == 401
            # The username's bucket is full: without the cookie, even the
            # right password is turned away.
            assert log_in(stranger, "root-admin", ADMIN_PASSWORD).status_code == 429

        signed_in = log_in(owner, "root-admin", ADMIN_PASSWORD)
        assert signed_in.status_code == 200
        assert signed_in.json()["status"] == "authenticated"


def test_a_trusted_browser_has_an_attempt_limit_of_its_own(tmp_path: Path) -> None:
    app_settings = settings_for(tmp_path / "test.db", login_attempts=3)
    with make_client(app_settings) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        for _ in range(3):
            refused = log_in(client, "root-admin", "not-the-admin-password")
            assert refused.status_code == 401
        assert log_in(client, "root-admin", ADMIN_PASSWORD).status_code == 429

        # Those guesses were counted against the trusted browser alone.
        with make_client(app_settings) as other_browser:
            challenged = log_in(other_browser, "root-admin", ADMIN_PASSWORD)
            assert challenged.status_code == 200
            assert challenged.json()["status"] == "verification_required"


def test_another_browser_or_account_still_needs_the_code(tmp_path: Path) -> None:
    app_settings = settings_for(tmp_path / "test.db")
    with make_client(app_settings) as client:
        admin_headers = login_admin(client)
        create_professor(
            client, admin_headers, "trusted.teacher", "a-secure-edge-password"
        )
        # The cookie now belongs to the teacher, not to the administrator.
        assert (
            log_in(client, "root-admin", ADMIN_PASSWORD).json()["status"]
            == "verification_required"
        )

    with make_client(app_settings) as other_browser:
        assert (
            log_in(other_browser, "trusted.teacher", "a-secure-edge-password").json()[
                "status"
            ]
            == "verification_required"
        )


# Built when the test runs, not when it is collected: a token minted at
# collection expires before a slow suite reaches the test, and is then refused
# for its age instead of for the reason the case names.
UNUSABLE_TRUST_COOKIES: dict[str, Callable[[], str]] = {
    "malformed": lambda: "not-a-token",
    "access-token": lambda: create_access_token(1, JWT_SECRET, 5, "version"),
    "expired": lambda: create_two_factor_trust_token(
        1, JWT_SECRET, "version", datetime.now(UTC) - timedelta(minutes=1)
    ),
    "foreign-secret": lambda: create_two_factor_trust_token(
        1,
        "another-secret-that-is-long-enough",
        "version",
        datetime.now(UTC) + timedelta(minutes=5),
    ),
    "non-numeric-subject": lambda: jwt.encode(
        {
            "sub": "not-a-number",
            "type": "two_factor_trust",
            "ver": "version",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        JWT_SECRET,
        algorithm="HS256",
    ),
}


@pytest.mark.parametrize("cookie", UNUSABLE_TRUST_COOKIES)
def test_an_unusable_trust_cookie_is_ignored(tmp_path: Path, cookie: str) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        forget_trusted_browser(client)
        client.cookies.set(TWO_FACTOR_TRUST_COOKIE, UNUSABLE_TRUST_COOKIES[cookie]())
        assert (
            log_in(client, "root-admin", ADMIN_PASSWORD).json()["status"]
            == "verification_required"
        )


def test_new_credentials_or_a_disabled_account_end_the_trust(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as admin_client:
        admin_headers = login_admin(admin_client)
        with make_client(settings_for(tmp_path / "test.db")) as teacher_client:
            teacher, _ = create_professor(
                teacher_client, admin_headers, "reset.teacher", "a-secure-edge-password"
            )
            assert (
                log_in(
                    teacher_client, "reset.teacher", "a-secure-edge-password"
                ).json()["status"]
                == "authenticated"
            )

            # Disabling then enabling the account bumps its token generation.
            for is_active in (False, True):
                assert (
                    admin_client.post(
                        f"/api/admin/users/{teacher['id']}/status",
                        headers=admin_headers,
                        json={"is_active": is_active},
                    ).status_code
                    == 200
                )
            assert (
                log_in(
                    teacher_client, "reset.teacher", "a-secure-edge-password"
                ).json()["status"]
                == "verification_required"
            )

            # A password reset does too, even without a 2FA reset.
            assert (
                admin_client.post(
                    f"/api/admin/users/{teacher['id']}/credentials",
                    headers=admin_headers,
                    json={
                        "password": "another-secure-edge-password",
                        "reset_two_factor": False,
                    },
                ).status_code
                == 200
            )
            assert (
                log_in(
                    teacher_client, "reset.teacher", "another-secure-edge-password"
                ).json()["status"]
                == "verification_required"
            )


def test_a_two_factor_reset_ends_the_trust(tmp_path: Path) -> None:
    app_settings = settings_for(tmp_path / "test.db")
    with make_client(app_settings) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        assert reset("root-admin", app_settings)
        # The old cookie cannot stand in for the new enrollment either.
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        log_out(client)
        assert (
            log_in(client, "root-admin", ADMIN_PASSWORD).json()["status"]
            == "authenticated"
        )


def test_browser_trust_can_be_turned_off(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        trusted_cookie = client.cookies.get(TWO_FACTOR_TRUST_COOKIE)
        assert trusted_cookie

    disabled = settings_for(tmp_path / "test.db", two_factor_browser_trust=False)
    with make_client(disabled) as client:
        # A cookie issued before the setting changed opens nothing.
        client.cookies.set(TWO_FACTOR_TRUST_COOKIE, trusted_cookie)
        assert (
            log_in(client, "root-admin", ADMIN_PASSWORD).json()["status"]
            == "verification_required"
        )

    with make_client(
        settings_for(tmp_path / "fresh.db", two_factor_browser_trust=False)
    ) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        assert client.cookies.get(TWO_FACTOR_TRUST_COOKIE) is None


def test_codes_are_capped_per_day(tmp_path: Path) -> None:
    app_settings = settings_for(
        tmp_path / "test.db",
        login_attempts=50,
        two_factor_daily_attempts=5,
    )
    with make_client(app_settings) as client:
        _, secret = complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        # complete_first_login already spent two of the five codes.
        log_out(client)
        forget_trusted_browser(client)
        challenge = log_in(client, "root-admin", ADMIN_PASSWORD).json()
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
        limited = client.post(
            "/api/auth/2fa/verify",
            json={"challenge_token": challenge["challenge_token"], "code": valid_code},
        )
        assert limited.status_code == 429
        assert limited.json()["detail"]["code"] == "AUTH_2FA_RATE_LIMITED"
        assert 0 < int(limited.headers["Retry-After"]) <= 86400

        # Resetting the enrollment lets the rightful owner enroll again.
        assert reset("root-admin", app_settings)
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)


def test_an_admin_credential_reset_clears_the_daily_cap(tmp_path: Path) -> None:
    app_settings = settings_for(
        tmp_path / "test.db",
        login_attempts=50,
        two_factor_daily_attempts=5,
    )
    with make_client(app_settings) as admin_client:
        admin_headers = login_admin(admin_client)
        with make_client(app_settings) as client:
            teacher, _ = create_professor(
                client, admin_headers, "capped.teacher", "a-secure-edge-password"
            )
            forget_trusted_browser(client)
            challenge = log_in(
                client, "capped.teacher", "a-secure-edge-password"
            ).json()
            for _ in range(4):
                client.post(
                    "/api/auth/2fa/verify",
                    json={
                        "challenge_token": challenge["challenge_token"],
                        "code": "000000",
                    },
                )
            assert (
                admin_client.post(
                    f"/api/admin/users/{teacher['id']}/credentials",
                    headers=admin_headers,
                    json={
                        "password": "another-secure-edge-password",
                        "reset_two_factor": True,
                    },
                ).status_code
                == 200
            )
            complete_first_login(
                client, "capped.teacher", "another-secure-edge-password"
            )


def test_the_script_and_the_admin_route_reset_two_factor_alike(
    tmp_path: Path,
) -> None:
    app_settings = settings_for(tmp_path / "test.db")
    with make_client(app_settings) as admin_client:
        admin_headers = login_admin(admin_client)
        app_state = admin_client.app.state
        teachers: dict[str, dict] = {}
        for username in ("route.teacher", "script.teacher"):
            with make_client(app_settings) as client:
                teachers[username], _ = create_professor(
                    client, admin_headers, username, "a-secure-edge-password"
                )
                # A pending challenge, and buckets someone filled.
                forget_trusted_browser(client)
                assert (
                    log_in(client, username, "a-secure-edge-password").json()["status"]
                    == "verification_required"
                )
            user_id = teachers[username]["id"]
            for subject in (
                password_rate_subject(username),
                trusted_password_rate_subject(user_id),
                two_factor_rate_subject(user_id),
            ):
                app_state.login_rate_limiter.reserve(subject)
            app_state.two_factor_daily_rate_limiter.reserve(
                two_factor_rate_subject(user_id)
            )

        assert (
            admin_client.post(
                f"/api/admin/users/{teachers['route.teacher']['id']}/credentials",
                headers=admin_headers,
                json={
                    "password": "another-secure-edge-password",
                    "reset_two_factor": True,
                },
            ).status_code
            == 200
        )
        assert reset("script.teacher", app_settings)

        def end_state(username: str) -> dict[str, object]:
            user_id = teachers[username]["id"]
            keys = [
                app_state.login_rate_limiter._account_key(subject)
                for subject in (
                    password_rate_subject(username),
                    trusted_password_rate_subject(user_id),
                    two_factor_rate_subject(user_id),
                )
            ] + [
                app_state.two_factor_daily_rate_limiter._account_key(
                    two_factor_rate_subject(user_id)
                )
            ]
            with app_state.session_factory() as session:
                return {
                    "refresh_sessions": session.scalar(
                        select(func.count()).where(RefreshSession.user_id == user_id)
                    ),
                    "live_refresh_sessions": session.scalar(
                        select(func.count()).where(
                            RefreshSession.user_id == user_id,
                            RefreshSession.revoked_at.is_(None),
                        )
                    ),
                    "challenges": session.scalar(
                        select(func.count()).where(
                            AuthenticationChallenge.user_id == user_id
                        )
                    ),
                    "two_factor": session.get(TwoFactorCredential, user_id),
                    "buckets": session.scalar(
                        select(func.count()).where(LoginRateLimit.limiter_key.in_(keys))
                    ),
                }

        route_state = end_state("route.teacher")
        assert route_state == end_state("script.teacher")
        assert route_state == {
            "refresh_sessions": 1,
            "live_refresh_sessions": 0,
            "challenges": 0,
            "two_factor": None,
            "buckets": 0,
        }


def test_the_trusted_day_ends_at_local_midnight() -> None:
    paris = ZoneInfo("Europe/Paris")
    now = datetime(2026, 11, 2, 23, 30, tzinfo=paris)
    assert end_of_trusted_day(now, "Europe/Paris") == datetime(
        2026, 11, 3, tzinfo=paris
    )
    assert end_of_trusted_day(now, None) == datetime(2026, 11, 3, tzinfo=UTC)


def test_the_trusted_day_never_exceeds_a_day() -> None:
    # The night clocks go back, a local day lasts 25 hours.
    now = datetime(2026, 10, 25, 0, 0, 30, tzinfo=ZoneInfo("Europe/Paris"))
    assert (
        end_of_trusted_day(now, "Europe/Paris")
        == now.astimezone(UTC) + TWO_FACTOR_TRUST_MAXIMUM
    )


@pytest.mark.parametrize("name", [None, "", "Not/A_Zone", "America", "../etc"])
def test_an_unknown_timezone_falls_back_to_utc(name: str | None) -> None:
    assert resolve_timezone(name) is UTC


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Europe/Paris", "Europe/Paris"),
        ("America/Argentina/Buenos_Aires", "America/Argentina/Buenos_Aires"),
        ("Etc/GMT+12", "Etc/GMT+12"),
        ("../etc/passwd", None),
        ("Europe/" + "a" * 64, None),
        (None, None),
    ],
)
def test_the_browser_timezone_is_sanitized(
    value: str | None, expected: str | None
) -> None:
    request = TwoFactorVerifyRequest(
        challenge_token="token", code="123456", timezone=value
    )
    assert request.timezone == expected


def test_trust_tokens_refuse_another_token_type() -> None:
    access_token = create_access_token(1, JWT_SECRET, 5, "version")
    with pytest.raises(jwt.InvalidTokenError, match="Unexpected token type"):
        decode_two_factor_trust_token(access_token, JWT_SECRET)


@pytest.mark.parametrize("version", [None, ""])
def test_trust_tokens_require_a_version(version: str | None) -> None:
    token = jwt.encode(
        {
            "sub": "1",
            "type": "two_factor_trust",
            "ver": version,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_two_factor_trust_token(token, JWT_SECRET)


def test_clearing_the_device_forgets_the_trusted_browser(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        forgotten = client.post(
            "/api/auth/logout",
            headers=refresh_headers(client),
            json={"forget_browser": True},
        )
        assert forgotten.status_code == 204
        assert client.cookies.get(TWO_FACTOR_TRUST_COOKIE) is None
        assert (
            log_in(client, "root-admin", ADMIN_PASSWORD).json()["status"]
            == "verification_required"
        )


def test_the_trusted_browser_is_forgotten_even_when_signed_out(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        log_out(client)
        assert client.cookies.get(TWO_FACTOR_TRUST_COOKIE)
        assert (
            client.post("/api/auth/logout", json={"forget_browser": True}).status_code
            == 204
        )
        assert client.cookies.get(TWO_FACTOR_TRUST_COOKIE) is None


def test_a_login_at_local_midnight_is_trusted_for_a_full_day() -> None:
    paris = ZoneInfo("Europe/Paris")
    now = datetime(2026, 11, 3, 0, 0, tzinfo=paris)
    assert end_of_trusted_day(now, "Europe/Paris") == datetime(
        2026, 11, 4, tzinfo=paris
    )


def test_the_short_spring_forward_day_ends_at_midnight() -> None:
    # Clocks go forward on 29 March 2026: that local day only lasts 23 hours.
    paris = ZoneInfo("Europe/Paris")
    now = datetime(2026, 3, 29, 0, 30, tzinfo=paris)
    end = end_of_trusted_day(now, "Europe/Paris")
    assert end == datetime(2026, 3, 30, tzinfo=paris)
    assert end - now.astimezone(UTC) == timedelta(hours=22, minutes=30)


def test_the_trusted_day_follows_the_browser_zone_not_utc() -> None:
    # 11:00 UTC is already 01:00 the next day in Kiribati (UTC+14).
    now = datetime(2026, 11, 3, 11, 0, tzinfo=UTC)
    kiritimati = ZoneInfo("Pacific/Kiritimati")
    assert end_of_trusted_day(now, "Pacific/Kiritimati") == datetime(
        2026, 11, 5, tzinfo=kiritimati
    )
    assert end_of_trusted_day(now, "Pacific/Kiritimati") - now <= (
        TWO_FACTOR_TRUST_MAXIMUM
    )
