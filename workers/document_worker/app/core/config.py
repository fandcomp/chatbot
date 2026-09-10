from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# workers/document_worker/app/core/config.py -> repo root is 4 parents up.
REPO_ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT_ENV_FILE), extra="ignore")

    DATABASE_URL: str
    REDIS_URL: str
    S3_ENDPOINT: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_BUCKET: str

    # STRUCTURE (M4) — mirrors apps/api/app/core/config.py; both read the
    # same repo-root .env, per this repo's hand-synced-config pattern.
    STRUCTURE_HIGH_CONFIDENCE: float = 0.90
    STRUCTURE_REVIEW_THRESHOLD: float = 0.70

    # CHUNKING (M5) — worker-only, apps/api never computes chunks so no
    # hand-sync duplication is needed here.
    CHUNK_MAX_TOKENS: int = 400

    # INDEXING (M6) — mirrors apps/api/app/core/config.py's QDRANT_URL/
    # QDRANT_API_KEY/VOYAGE_API_KEY/EMBEDDING_MODEL (same hand-synced-config
    # pattern as STRUCTURE_HIGH_CONFIDENCE above); VOYAGE_EMBEDDING_DIMENSION
    # is worker-only since apps/api never calls Voyage itself.
    QDRANT_URL: str
    QDRANT_API_KEY: str = ""
    VOYAGE_API_KEY: str = ""
    EMBEDDING_MODEL: str = "voyage-context-4"
    VOYAGE_EMBEDDING_DIMENSION: int = 1024

    # LAN ARCHIVE CONNECTOR (LAN-M1, ADR-020) — mirrors
    # apps/api/app/core/config.py's own CONNECTOR_ALLOWED_HOSTS (hand-synced-
    # config pattern, same as STRUCTURE_HIGH_CONFIDENCE above). This worker
    # is the one that actually enforces the allowlist against a real UNC
    # path (windows_unc_adapter.py) — apps/api's copy only gates SourceRoot
    # creation.
    CONNECTOR_ALLOWED_HOSTS: str = ""
    SCAN_PAGE_SIZE: int = 500

    @property
    def connector_allowed_hosts_list(self) -> list[str]:
        return [host.strip().lower() for host in self.CONNECTOR_ALLOWED_HOSTS.split(",") if host.strip()]


settings = Settings()
