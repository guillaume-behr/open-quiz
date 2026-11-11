from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta, tzinfo
from datetime import time as day_start
from hashlib import sha256
from hmac import compare_digest
from hmac import new as hmac_new
from secrets import token_urlsafe
from threading import BoundedSemaphore
from zoneinfo import ZoneInfo

import jwt
import pyotp
from cryptography.fernet import Fernet
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash(token_urlsafe(32))
# Argon2 takes tens of megabytes for each hash it computes. Sign-in attempts
# arrive on the request thread pool, so without a bound a flood of them would
# hold that memory once per thread; past this many they wait their turn.
MAX_CONCURRENT_PASSWORD_HASHES = 4
password_hashing = BoundedSemaphore(MAX_CONCURRENT_PASSWORD_HASHES)
ACCESS_TOKEN_REQUIRED_CLAIMS = ["sub", "type", "ver", "iat", "exp"]
TWO_FACTOR_TOKEN_REQUIRED_CLAIMS = ["sub", "type", "jti", "iat", "exp"]
TWO_FACTOR_TRUST_TOKEN_TYPE = "two_factor_trust"  # noqa: S105 - a JWT type.
# A browser trusted after a two-factor login skips the code until the end of
# the user's day, and never for longer than this.
TWO_FACTOR_TRUST_MAXIMUM = timedelta(hours=24)


def hash_password(password: str) -> str:
    with password_hashing:
        return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    with password_hashing:
        return password_hash.verify(password, encoded)


def access_token_version(
    encoded_password: str,
    secret: str,
    generation: int = 0,
) -> str:
    """Bind a token to the stored password, so a change invalidates it."""
    return hmac_new(
        secret.encode(),
        f"{generation}:{encoded_password}".encode(),
        sha256,
    ).hexdigest()


def create_access_token(
    user_id: int,
    secret: str,
    expires_minutes: int,
    version: str,
    *,
    session_expires_at: int | None = None,
) -> str:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=expires_minutes)
    if session_expires_at is not None:
        expires_at = min(
            expires_at,
            datetime.fromtimestamp(session_expires_at, UTC),
        )
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "ver": version,
            "iat": now,
            "exp": expires_at,
        },
        secret,
        algorithm="HS256",
    )


def decode_access_token(token: str, secret: str) -> tuple[int, str]:
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"require": ACCESS_TOKEN_REQUIRED_CLAIMS},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Unexpected token type")
    version = payload.get("ver")
    if not isinstance(version, str) or not version:
        raise jwt.InvalidTokenError("Missing token version")
    return int(payload["sub"]), version


def create_student_access_token(
    student_id: int, secret: str, version: str, expires_hours: int
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(student_id),
            "type": "student_access",
            "ver": version,
            "iat": now,
            "exp": now + timedelta(hours=expires_hours),
        },
        secret,
        algorithm="HS256",
    )


def decode_student_access_token(token: str, secret: str) -> tuple[int, str]:
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"require": ACCESS_TOKEN_REQUIRED_CLAIMS},
    )
    if payload.get("type") != "student_access":
        raise jwt.InvalidTokenError("Unexpected token type")
    version = payload.get("ver")
    if not isinstance(version, str) or not version:
        raise jwt.InvalidTokenError("Missing token version")
    return int(payload["sub"]), version


def create_two_factor_token(
    user_id: int, secret: str, purpose: str
) -> tuple[str, str, int]:
    now = datetime.now(UTC)
    token_id = token_urlsafe(32)
    expires_at = now + timedelta(minutes=5)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "type": purpose,
            "jti": token_id,
            "iat": now,
            "exp": expires_at,
        },
        secret,
        algorithm="HS256",
    )
    return token, sha256(token_id.encode()).hexdigest(), int(expires_at.timestamp())


def decode_two_factor_token(token: str, secret: str) -> tuple[int, str, str]:
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"require": TWO_FACTOR_TOKEN_REQUIRED_CLAIMS},
    )
    purpose = payload["type"]
    if purpose not in {"two_factor_setup", "two_factor_verification"}:
        raise jwt.InvalidTokenError("Unexpected token type")
    token_id = payload["jti"]
    if not isinstance(token_id, str) or not token_id:
        raise jwt.InvalidTokenError("Missing token identifier")
    return int(payload["sub"]), purpose, sha256(token_id.encode()).hexdigest()


def two_factor_trust_version(
    encoded_password: str,
    encrypted_totp_secret: str,
    secret: str,
    generation: int = 0,
) -> str:
    """Bind a trusted browser to the password and the enrolled authenticator.

    Changing the password, resetting two-factor authentication (a new
    enrollment stores a new secret) or bumping the access token generation
    (disabling the account) stops every trusted browser from skipping the code.
    """
    return hmac_new(
        secret.encode(),
        f"two-factor-trust:{generation}:{encoded_password}:{encrypted_totp_secret}".encode(),
        sha256,
    ).hexdigest()


def resolve_timezone(name: str | None) -> tzinfo:
    """The browser's time zone, or UTC when it is missing or unknown."""
    if not name:
        return UTC
    try:
        return ZoneInfo(name)
    except KeyError, ValueError, OSError:
        # ZoneInfoNotFoundError is a KeyError; malformed keys raise ValueError
        # and a directory such as "America" an OSError.
        return UTC


def end_of_trusted_day(now: datetime, timezone_name: str | None) -> datetime:
    """Next local midnight in the browser's time zone, capped at 24 hours."""
    # Aware arithmetic follows the wall clock of its own zone: in UTC, 24 hours
    # stay 24 hours even across a daylight saving change.
    now = now.astimezone(UTC)
    zone = resolve_timezone(timezone_name)
    local_date = now.astimezone(zone).date()
    next_midnight = datetime.combine(
        local_date + timedelta(days=1), day_start.min, tzinfo=zone
    )
    return min(next_midnight.astimezone(UTC), now + TWO_FACTOR_TRUST_MAXIMUM)


def create_two_factor_trust_token(
    user_id: int,
    secret: str,
    version: str,
    expires_at: datetime,
) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": TWO_FACTOR_TRUST_TOKEN_TYPE,
            "ver": version,
            "iat": datetime.now(UTC),
            "exp": expires_at,
        },
        secret,
        algorithm="HS256",
    )


def decode_two_factor_trust_token(token: str, secret: str) -> tuple[int, str]:
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"require": ACCESS_TOKEN_REQUIRED_CLAIMS},
    )
    if payload.get("type") != TWO_FACTOR_TRUST_TOKEN_TYPE:
        raise jwt.InvalidTokenError("Unexpected token type")
    version = payload.get("ver")
    if not isinstance(version, str) or not version:
        raise jwt.InvalidTokenError("Missing token version")
    return int(payload["sub"]), version


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name="Open Quiz",
    )


def _cipher(encryption_key: str) -> Fernet:
    key = urlsafe_b64encode(sha256(encryption_key.encode()).digest())
    return Fernet(key)


def encrypt_totp_secret(secret: str, encryption_key: str) -> str:
    return _cipher(encryption_key).encrypt(secret.encode()).decode()


def decrypt_totp_secret(encrypted_secret: str, encryption_key: str) -> str:
    return _cipher(encryption_key).decrypt(encrypted_secret.encode()).decode()


def encrypt_student_password(password: str, encryption_key: str) -> str:
    return _cipher(encryption_key).encrypt(password.encode()).decode()


def decrypt_student_password(encrypted_password: str, encryption_key: str) -> str:
    return _cipher(encryption_key).decrypt(encrypted_password.encode()).decode()


def verify_totp_code(
    secret: str,
    code: str,
    last_counter: int | None,
) -> int | None:
    # compare_digest raises on non-ASCII strings: such a code is just wrong.
    if not (code.isascii() and code.isdigit()):
        return None
    totp = pyotp.TOTP(secret)
    current_counter = totp.timecode(datetime.now(UTC))
    for counter in range(current_counter - 1, current_counter + 2):
        if (last_counter is None or counter > last_counter) and compare_digest(
            totp.generate_otp(counter), code
        ):
            return counter
    return None


def create_refresh_token() -> str:
    return token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def choice_token_key(secret: str) -> bytes:
    """A key of its own for student choice tokens (app/choice_tokens.py)."""
    return hmac_new(secret.encode(), b"student-choice-token-key", sha256).digest()


def student_choice_token(
    key: bytes, session_id: int, participant_id: int, choice_id: int
) -> str:
    """16 URL-safe characters naming one choice for one participant."""
    digest = hmac_new(
        key, f"{session_id}:{participant_id}:{choice_id}".encode(), sha256
    ).digest()
    return urlsafe_b64encode(digest[:12]).decode()


def refresh_request_proof(token: str, secret: str) -> str:
    """Bind refresh-cookie use to a value unavailable to same-origin workers."""
    return hmac_new(
        secret.encode(),
        f"refresh-proof:{token}".encode(),
        sha256,
    ).hexdigest()
