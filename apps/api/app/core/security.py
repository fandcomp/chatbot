from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# Precomputed so `login` can run a real bcrypt comparison even when no user
# matches the email, keeping response timing indistinguishable from a
# wrong-password case (avoids leaking account existence via a timing side channel).
_DUMMY_HASH = hash_password("dummy-password-for-constant-time-comparison")


def create_access_token(data: dict[str, Any], expires_minutes: int | None = None) -> str:
    to_encode = dict(data)
    expire = datetime.now(UTC) + timedelta(
        minutes=expires_minutes if expires_minutes is not None else settings.JWT_EXPIRE_MINUTES
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
