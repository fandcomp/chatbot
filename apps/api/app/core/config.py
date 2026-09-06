from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT_ENV_FILE), extra="ignore")

    # DATABASE
    DATABASE_URL: str
    POSTGRES_USER: str = "chatbot"
    POSTGRES_PASSWORD: str = "chatbot"
    POSTGRES_DB: str = "chatbot"

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

    # FILE
    MAX_FILE_SIZE_MB: int = 50

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

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def session_cookie_secure(self) -> bool:
        return self.ENVIRONMENT != "development"


settings = Settings()
