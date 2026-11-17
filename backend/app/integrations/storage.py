"""Object storage adaptor: S3-compatible (SeaweedFS locally, any S3 service in production),
or PostgreSQL for hosts without object storage (STORAGE_BACKEND=database).

Objects are private. The browser never receives storage URLs or credentials; files are
streamed through the API after a permission check (app/api/v1/files.py).
"""

import logging
from collections.abc import Iterator
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
    def list_keys(self) -> Iterator[str]: ...
    def content_type(self, key: str) -> str: ...


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

    def list_keys(self) -> Iterator[str]:
        """Every object key in the bucket (used by backups)."""
        pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket)
        for page in pages:
            for item in page.get("Contents", []):
                yield item["Key"]

    def content_type(self, key: str) -> str:
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            raise StorageError("File not available.") from exc
        return str(head.get("ContentType") or "application/octet-stream")


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

    def list_keys(self) -> Iterator[str]:
        yield from sorted(self.objects)

    def content_type(self, key: str) -> str:
        if key not in self.objects:
            raise StorageError("File not available.")
        return self.objects[key][1]


class DatabaseStorage:
    """STORAGE_BACKEND=database: object bytes in PostgreSQL (table stored_objects), for
    hosts without object storage or a persistent disk. Uses its own short transactions,
    like a call to S3 would."""

    def put(self, key: str, data: bytes, content_type: str) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from app.db.session import get_sessionmaker
        from app.models.storage import StoredObject

        values = {"key": key, "data": data, "content_type": content_type, "size_bytes": len(data)}
        with get_sessionmaker()() as db:
            stmt = insert(StoredObject).values(**values)
            db.execute(
                stmt.on_conflict_do_update(
                    index_elements=[StoredObject.key],
                    set_={k: stmt.excluded[k] for k in ("data", "content_type", "size_bytes")},
                )
            )
            db.commit()

    def _row(self, key: str) -> tuple[bytes, str]:
        from sqlalchemy import select

        from app.db.session import get_sessionmaker
        from app.models.storage import StoredObject

        with get_sessionmaker()() as db:
            row = db.execute(
                select(StoredObject.data, StoredObject.content_type).where(StoredObject.key == key)
            ).first()
        if row is None:
            raise StorageError("File not available.")
        return bytes(row[0]), row[1]

    def get(self, key: str) -> bytes:
        return self._row(key)[0]

    def content_type(self, key: str) -> str:
        return self._row(key)[1]

    def delete(self, key: str) -> None:
        from sqlalchemy import delete

        from app.db.session import get_sessionmaker
        from app.models.storage import StoredObject

        with get_sessionmaker()() as db:
            db.execute(delete(StoredObject).where(StoredObject.key == key))
            db.commit()

    def list_keys(self) -> Iterator[str]:
        from sqlalchemy import select

        from app.db.session import get_sessionmaker
        from app.models.storage import StoredObject

        with get_sessionmaker()() as db:
            keys = list(db.scalars(select(StoredObject.key).order_by(StoredObject.key)))
        yield from keys


@lru_cache
def get_storage() -> ObjectStorage:
    s = get_settings()
    if s.storage_backend == "database":
        return DatabaseStorage()
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
