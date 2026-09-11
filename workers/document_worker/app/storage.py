import uuid
from typing import BinaryIO

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.config import settings

_client = boto3.client(
    "s3",
    endpoint_url=settings.S3_ENDPOINT,
    aws_access_key_id=settings.S3_ACCESS_KEY,
    aws_secret_access_key=settings.S3_SECRET_KEY,
    config=BotoConfig(signature_version="s3v4"),
)


def _ensure_bucket_exists() -> None:
    try:
        _client.head_bucket(Bucket=settings.S3_BUCKET)
    except ClientError:
        _client.create_bucket(Bucket=settings.S3_BUCKET)


_ensure_bucket_exists()


def get_object_bytes(key: str) -> bytes:
    response = _client.get_object(Bucket=settings.S3_BUCKET, Key=key)
    return response["Body"].read()


def build_original_object_key(
    organization_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID, filename: str
) -> str:
    """LAN-M2 — mirrors apps/api/app/core/storage.py's own key convention
    exactly, so a promoted version lands in the same shape as an ordinary
    HTTP upload and the existing parse/chunk/index pipeline needs no
    special-casing for where a file came from."""
    return (
        f"organization/{organization_id}/documents/{document_id}/"
        f"versions/{version_id}/original/{filename}"
    )


def put_object_stream(key: str, fileobj: BinaryIO, content_type: str) -> None:
    """LAN-M2 — the worker's first write path to object storage (previously
    read-only). Uses boto3's managed `upload_fileobj` (chunked multipart
    transfer) rather than `put_object(Body=bytes)` so a ~100MB file is never
    fully materialized in memory here, matching the streaming-transfer
    requirement (addendum §6)."""
    _client.upload_fileobj(fileobj, settings.S3_BUCKET, key, ExtraArgs={"ContentType": content_type})
