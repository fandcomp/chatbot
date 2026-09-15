"""Gap audit 2026-09-15 (performance/latency pass): create_async_engine was
called with no explicit pool sizing, silently relying on SQLAlchemy's own
unstated defaults. Asserts the engine's actual pool is wired to the
now-explicit settings, not just that the settings themselves have the right
defaults (test_config.py covers that half).
"""

from app.core.config import settings
from app.core.database import engine


def test_engine_pool_is_wired_to_the_configured_settings() -> None:
    assert engine.pool.size() == settings.DB_POOL_SIZE
    assert engine.pool._max_overflow == settings.DB_MAX_OVERFLOW
    assert engine.pool._timeout == settings.DB_POOL_TIMEOUT_SECONDS
