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


settings = Settings()
