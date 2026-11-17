"""Password hashing and opaque token helpers.

- Passwords: Argon2id (argon2-cffi defaults follow RFC 9106 recommendations).
- Session, reset and invitation tokens: 256-bit random values. Only a SHA-256 hash is
  stored, so a database leak does not reveal usable tokens.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

SESSION_COOKIE = "wp_session"
PORTAL_SESSION_COOKIE = "wp_portal_session"
CSRF_COOKIE = "wp_csrf"
CSRF_HEADER = "x-csrf-token"

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

_hasher = PasswordHasher()
# Verified against when the user does not exist, so response time does not reveal
# whether an email address is registered.
_DUMMY_HASH = _hasher.hash("workshoppro-timing-equaliser")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
