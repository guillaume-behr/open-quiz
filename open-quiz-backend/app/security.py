from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
from secrets import token_urlsafe

import jwt
import pyotp
from cryptography.fernet import Fernet
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash(token_urlsafe(32))


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def create_access_token(user_id: int, secret: str, expires_minutes: int) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=expires_minutes),
        },
        secret,
        algorithm="HS256",
    )


def decode_access_token(token: str, secret: str) -> int:
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Unexpected token type")
    return int(payload["sub"])


def create_two_factor_token(user_id: int, secret: str, purpose: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": purpose,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )


def decode_two_factor_token(token: str, secret: str) -> tuple[int, str]:
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    purpose = payload["type"]
    if purpose not in {"two_factor_setup", "two_factor_verification"}:
        raise jwt.InvalidTokenError("Unexpected token type")
    return int(payload["sub"]), purpose


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name="Open Quiz",
    )


def _totp_cipher(encryption_key: str) -> Fernet:
    key = urlsafe_b64encode(sha256(encryption_key.encode()).digest())
    return Fernet(key)


def encrypt_totp_secret(secret: str, encryption_key: str) -> str:
    return _totp_cipher(encryption_key).encrypt(secret.encode()).decode()


def decrypt_totp_secret(encrypted_secret: str, encryption_key: str) -> str:
    return _totp_cipher(encryption_key).decrypt(encrypted_secret.encode()).decode()


def verify_totp_code(
    secret: str,
    code: str,
    last_counter: int | None,
) -> int | None:
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
