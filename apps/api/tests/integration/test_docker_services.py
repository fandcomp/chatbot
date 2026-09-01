"""Integration tests against the real Docker Compose infra (Postgres, Redis, Qdrant, MinIO).

Requires `docker compose up -d` to be running from the repo root.
"""

import boto3
import pytest
import redis.asyncio as redis
from botocore.config import Config as BotoConfig
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine


@pytest.mark.asyncio
async def test_postgres_connection_succeeds_when_docker_service_is_up() -> None:
    # Arrange
    async with engine.connect() as conn:
        # Act
        result = await conn.execute(text("SELECT 1"))

        # Assert
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_redis_ping_succeeds_when_docker_service_is_up() -> None:
    # Arrange
    client = redis.from_url(settings.REDIS_URL)

    # Act
    pong = await client.ping()

    # Assert
    assert pong is True
    await client.aclose()


@pytest.mark.asyncio
async def test_qdrant_get_collections_succeeds_when_docker_service_is_up() -> None:
    # Arrange
    client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)

    # Act
    collections = await client.get_collections()

    # Assert
    assert collections is not None


def test_minio_list_buckets_succeeds_when_docker_service_is_up() -> None:
    # Arrange
    client = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        config=BotoConfig(signature_version="s3v4"),
    )

    # Act
    response = client.list_buckets()

    # Assert
    assert "Buckets" in response
