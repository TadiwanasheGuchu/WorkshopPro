"""Object storage adaptor (S3-compatible: MinIO locally, any S3 service in production).

Objects are private. The browser never receives storage URLs or credentials; files are
streamed through the API after a permission check (app/api/v1/files.py).
"""

import logging
from functools import lru_cache
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class StorageError(Exception):
    pass


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class S3Storage:
    def __init__(
        self, endpoint: str | None, bucket: str, access_key: str, secret_key: str, region: str
    ) -> None:
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3},
            ),
        )

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)
            logger.info("storage_bucket_created", extra={"bucket": self.bucket})

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        except ClientError as exc:
            raise StorageError("Could not store the file.") from exc

    def get(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            raise StorageError("File not available.") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            raise StorageError("Could not delete the file.") from exc


class InMemoryStorage:
    """Used in tests."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise StorageError("File not available.")
        return self.objects[key][0]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


@lru_cache
def get_storage() -> ObjectStorage:
    s = get_settings()
    storage = S3Storage(
        endpoint=s.storage_endpoint_url,
        bucket=s.storage_bucket,
        access_key=s.storage_access_key,
        secret_key=s.storage_secret_key,
        region=s.storage_region,
    )
    if s.storage_auto_create_bucket:
        try:
            storage.ensure_bucket()
        except Exception:
            logger.warning("storage_bucket_check_failed")
    return storage
