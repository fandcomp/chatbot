import uuid

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


def build_original_object_key(
    organization_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID, filename: str
) -> str:
    return (
        f"organization/{organization_id}/documents/{document_id}/"
        f"versions/{version_id}/original/{filename}"
    )


def put_object(key: str, body: bytes, content_type: str) -> None:
    _client.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=body, ContentType=content_type)


def get_object_bytes(key: str) -> bytes:
    response = _client.get_object(Bucket=settings.S3_BUCKET, Key=key)
    return response["Body"].read()


def delete_object(key: str) -> None:
    _client.delete_object(Bucket=settings.S3_BUCKET, Key=key)
