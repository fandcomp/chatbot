import boto3
import redis.asyncio as redis
from botocore.config import Config as BotoConfig
from fastapi import APIRouter
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _check_postgres() -> str:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 - health check must never raise
        return f"error: {exc}"


async def _check_redis() -> str:
    try:
        client = redis.from_url(settings.REDIS_URL)
        await client.ping()
        await client.aclose()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


async def _check_qdrant() -> str:
    try:
        client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
        await client.get_collections()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


def _check_minio() -> str:
    try:
        client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            config=BotoConfig(signature_version="s3v4"),
        )
        client.list_buckets()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


@router.get("/health/ready")
async def health_ready() -> dict[str, object]:
    checks = {
        "postgres": await _check_postgres(),
        "redis": await _check_redis(),
        "qdrant": await _check_qdrant(),
        "minio": _check_minio(),
    }
    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
