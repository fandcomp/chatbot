"""Unit tests for Settings' own validation — gap audit 2026-09-15 found
nothing previously enforced JWT_SECRET_KEY's strength, so a weak or
unedited-placeholder secret would boot a working app anyway.
"""

import pytest

from app.core.config import Settings

_OTHER_REQUIRED_FIELDS = {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
    "REDIS_URL": "redis://localhost:6379/0",
    "QDRANT_URL": "http://localhost:6333",
}


def test_rejects_a_jwt_secret_shorter_than_the_minimum() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET_KEY must be at least"):
        Settings(**_OTHER_REQUIRED_FIELDS, JWT_SECRET_KEY="too-short")


def test_rejects_the_env_example_placeholder_verbatim() -> None:
    # .env.example's own documented placeholder — must never be usable as
    # a real secret if an operator forgets to edit it.
    with pytest.raises(ValueError, match="JWT_SECRET_KEY must be at least"):
        Settings(**_OTHER_REQUIRED_FIELDS, JWT_SECRET_KEY="change-me-in-every-environment")


def test_accepts_a_sufficiently_long_secret() -> None:
    strong_secret = "a" * 32
    settings = Settings(**_OTHER_REQUIRED_FIELDS, JWT_SECRET_KEY=strong_secret)
    assert settings.JWT_SECRET_KEY == strong_secret


def test_db_pool_settings_default_to_sqlalchemys_own_library_defaults() -> None:
    # Gap audit 2026-09-15: these must stay a no-op on today's deployment —
    # create_async_engine used to get these from SQLAlchemy's own unstated
    # defaults, now they're explicit.
    settings = Settings(**_OTHER_REQUIRED_FIELDS, JWT_SECRET_KEY="a" * 32)
    assert settings.DB_POOL_SIZE == 5
    assert settings.DB_MAX_OVERFLOW == 10
    assert settings.DB_POOL_TIMEOUT_SECONDS == 30
