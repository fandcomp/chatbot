from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Gap audit 2026-09-15: nothing previously enforced JWT_SECRET_KEY's
# strength — an operator who left .env.example's placeholder unchanged, or
# used any other short/low-entropy value, would boot a working app that
# signs valid session cookies with a brute-forceable key (full auth
# bypass/impersonation, including OWNER). 32 chars is a practical floor for
# an HS256 signing key; the recommended `secrets.token_urlsafe(48)` from
# .env.example's own comment produces ~64.
_MIN_JWT_SECRET_LENGTH = 32

REPO_ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT_ENV_FILE), extra="ignore")

    # DATABASE
    DATABASE_URL: str
    POSTGRES_USER: str = "chatbot"
    POSTGRES_PASSWORD: str = "chatbot"
    POSTGRES_DB: str = "chatbot"
    # Gap audit 2026-09-15 (performance/latency pass): create_async_engine
    # was called with no pool sizing at all, silently relying on
    # SQLAlchemy's library defaults (pool_size=5, max_overflow=10,
    # pool_timeout=30) — correct by luck, not by intent, and with no way to
    # tune it per-deployment without editing code. Made explicit and
    # configurable; values below match those same defaults so this change
    # is a no-op on today's deployment.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT_SECONDS: int = 30

    # REDIS
    REDIS_URL: str

    # QDRANT
    QDRANT_URL: str
    QDRANT_API_KEY: str = ""

    # OBJECT STORAGE
    S3_ENDPOINT: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_BUCKET: str

    # HUGGING FACE
    HF_TOKEN: str = ""

    # MODEL ROUTING
    LLM_FAST_MODEL: str = ""
    LLM_STRONG_MODEL: str = ""
    LLM_FAST_FALLBACK: str = ""
    LLM_STRONG_FALLBACK: str = ""

    # VOYAGE
    VOYAGE_API_KEY: str = ""
    EMBEDDING_MODEL: str = "voyage-context-4"
    RERANK_MODEL: str = "rerank-2.5-lite"
    # (added, M7) mirrors workers/document_worker's config — apps/api now
    # calls Voyage itself for query-time embedding (this repo's existing
    # hand-synced-config pattern, see that config.py's own comment).
    VOYAGE_EMBEDDING_DIMENSION: int = 1024

    # ANALYTICS (added, M14) — rough per-tier cost estimate, not a precise
    # HF Inference Providers billing reconciliation (that data isn't exposed
    # anywhere this codebase can read yet).
    LLM_FAST_COST_PER_1K_TOKENS: float = 0.0
    LLM_STRONG_COST_PER_1K_TOKENS: float = 0.0

    # RETRIEVAL
    DENSE_TOP_K: int = 30
    SPARSE_TOP_K: int = 30
    RERANK_TOP_K: int = 6
    # (added, M7) size of the RRF-fused candidate list M7 hands to M8's
    # conditional reranker — distinct from DENSE_TOP_K/SPARSE_TOP_K (each
    # arm's own retrieval depth) and RERANK_TOP_K (M8's final evidence count).
    FUSION_TOP_K: int = 20
    # (added, gap audit 2026-09-15 / ADR-023) — Qdrant cosine-similarity
    # floor on the DENSE query only, applied before RRF fusion. Never
    # applied to the sparse (IDF-weighted) arm: that score has no
    # comparable universal scale (any sparse hit already shares at least
    # one term with the query by construction), so a generic floor there
    # would be arbitrary rather than principled. Deliberately conservative
    # (only excludes clearly-dissimilar candidates, cosine similarity near
    # zero or negative) — not benchmarked against real production query
    # data (none available in this dev environment, same limitation
    # LAN-M6 recorded for its own benchmarking); pending real calibration,
    # a permissive default protects retrieval recall over tightening
    # precision (spec §102's "correct retrieval" ranks above "security").
    DENSE_SIMILARITY_FLOOR: float = 0.2

    # FILE — per-file limit, deliberately separate from any total-archive
    # size (LAN archive can reach ~4TB; this never bounds that, see
    # docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md §1).
    MAX_FILE_SIZE_MB: int = 100

    # LAN ARCHIVE CONNECTOR (LAN-M1, ADR-020) — pilot defaults, not
    # benchmarked production values. CONNECTOR_ALLOWED_HOSTS/SHARES is an
    # explicit allowlist; a SourceRoot outside it is rejected at creation,
    # never silently expanded to a broader scope.
    CONNECTOR_ENABLED: bool = False
    CONNECTOR_ALLOWED_HOSTS: str = ""
    SCAN_PAGE_SIZE: int = 500
    # Unused until LAN-M2 (snapshot/transfer) — defined now so the config
    # surface doesn't need another migration when that milestone lands.
    SCAN_STABILITY_WINDOW_SECONDS: int = 30

    @property
    def connector_allowed_hosts_list(self) -> list[str]:
        return [host.strip().lower() for host in self.CONNECTOR_ALLOWED_HOSTS.split(",") if host.strip()]

    # STRUCTURE
    STRUCTURE_HIGH_CONFIDENCE: float = 0.90
    STRUCTURE_REVIEW_THRESHOLD: float = 0.70

    # CHAT
    MAX_RECENT_MESSAGES: int = 8
    ENABLE_SEMANTIC_CACHE: bool = True
    # M15 (spec §45/§47 rule 9) — exact-normalized-query answer cache, not
    # true embedding-similarity semantic matching (see ADR-017). Bounds how
    # stale a cached answer can be for invalidation paths this codebase
    # can't reach synchronously (see ADR-017's worker-side gap).
    ANSWER_CACHE_TTL_SECONDS: int = 600

    # PERFORMANCE
    LLM_REQUEST_TIMEOUT: int = 30
    RETRIEVAL_TIMEOUT: int = 10

    # APP
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:3000"

    # AUTH (added) — JWT session cookie, see ADR-015
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 720
    SESSION_COOKIE_NAME: str = "session"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _reject_weak_jwt_secret(cls, value: str) -> str:
        if len(value) < _MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least {_MIN_JWT_SECRET_LENGTH} characters "
                "(this also rejects .env.example's own placeholder value) — generate a "
                "real one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def session_cookie_secure(self) -> bool:
        return self.ENVIRONMENT != "development"


settings = Settings()
