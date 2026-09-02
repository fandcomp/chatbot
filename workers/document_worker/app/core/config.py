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


settings = Settings()
