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
