"""Unusual input to the auth routes gets the documented status, never a 500."""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Connection, text

from app.core.security import (
    encrypt_totp_secret,
    generate_totp_secret,
    verify_totp_code,
)
from app.models import TwoFactorCredential, User

from support import (
    concurrent_writes,
    login_admin,
    make_client,
    settings_for,
)

ARABIC_INDIC_DIGITS = "١٢٣٤٥٦"


def new_professor(client, username: str = "fresh.teacher") -> None:
    created = client.post(
        "/api/admin/users",
        headers=login_admin(client),
        json={
            "username": username,
            "display_name": "Fresh Teacher",
            "password": "a-secure-fresh-password",
        },
    )
    assert created.status_code == 201


def first_login(client, username: str = "fresh.teacher"):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": "a-secure-fresh-password"},
    )


def test_totp_codes_with_non_ascii_digits_are_refused() -> None:
    secret = "JBSWY3DPEHPK3PXP"
    assert verify_totp_code(secret, ARABIC_INDIC_DIGITS, None) is None


def test_a_non_ascii_code_is_rejected_before_any_attempt_counts(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "digits")) as client:
        new_professor(client)
        challenge = first_login(client).json()["challenge_token"]

        def attempts() -> int:
            engine = client.app.state.session_factory.kw["bind"]
            with engine.connect() as connection:
                return connection.execute(
                    text("SELECT COALESCE(SUM(attempts), 0) FROM login_rate_limits")
                ).scalar_one()

        before = attempts()
        refused = client.post(
            "/api/auth/2fa/verify",
            json={"challenge_token": challenge, "code": ARABIC_INDIC_DIGITS},
        )
        assert refused.status_code == 422
        assert attempts() == before


def test_an_oversized_chunked_body_is_refused_with_413(tmp_path: Path) -> None:
    settings = settings_for(tmp_path / "chunked")
    with make_client(settings) as client:

        def chunks() -> Iterator[bytes]:
            yield b'{"username": "'
            for _ in range(settings.max_request_body_bytes // 1024 + 1):
                yield b"x" * 1024
            yield b'", "password": "x"}'

        refused = client.post(
            "/api/auth/login",
            content=chunks(),
            headers={"Content-Type": "application/json"},
        )
        assert "content-length" not in {key.lower() for key in refused.request.headers}
        assert refused.status_code == 413
        assert refused.json()["detail"]["code"] == "REQUEST_BODY_TOO_LARGE"


def test_two_first_logins_at_once_both_get_a_setup(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "setup-race")) as client:
        new_professor(client)
        with client.app.state.session_factory() as session:
            user_id = (
                session.query(User.id).filter_by(username="fresh.teacher").scalar()
            )

        other_secret = generate_totp_secret()

        def other_first_login(connection: Connection) -> None:
            connection.execute(
                TwoFactorCredential.__table__.insert().values(
                    user_id=user_id,
                    encrypted_secret=encrypt_totp_secret(
                        other_secret, client.app.state.settings.totp_encryption_key
                    ),
                    confirmed=False,
                )
            )

        with concurrent_writes(
            client, ("INSERT INTO two_factor_credentials", other_first_login)
        ) as fired:
            raced = first_login(client)
        assert fired
        assert raced.status_code == 200
        assert raced.json()["status"] == "setup_required"
        # Both logins enroll the same secret, so either can confirm it.
        assert raced.json()["secret"] == other_secret
        with client.app.state.session_factory() as session:
            assert (
                session.query(TwoFactorCredential).filter_by(user_id=user_id).count()
                == 1
            )
