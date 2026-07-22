import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO, Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from .config import Settings


class ObjectStorage(Protocol):
    def put_file(self, key: str, source: Path) -> None: ...

    def put_bytes(self, key: str, content: bytes, content_type: str) -> None: ...

    def iter_object(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]: ...

    def delete_prefix(self, prefix: str) -> None: ...


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        resolved = (self.root / key).resolve()
        if self.root not in resolved.parents:
            raise ValueError("Object key escapes the storage root")
        return resolved

    def put_file(self, key: str, source: Path) -> None:
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(source, destination)

    def put_bytes(self, key: str, content: bytes, content_type: str) -> None:
        del content_type
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(content)

    def iter_object(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        with self._resolve(key).open("rb") as handle:
            while chunk := handle.read(chunk_size):
                yield chunk

    def delete_prefix(self, prefix: str) -> None:
        target = self._resolve(prefix.rstrip("/"))
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        for attempt in range(settings.s3_connect_retries):
            try:
                self.client.head_bucket(Bucket=self.bucket)
                break
            except EndpointConnectionError:
                if attempt == settings.s3_connect_retries - 1:
                    raise
                time.sleep(1)
            except ClientError as exc:
                error_code = str(exc.response.get("Error", {}).get("Code", ""))
                if error_code in {"404", "NoSuchBucket", "NotFound"}:
                    self.client.create_bucket(Bucket=self.bucket)
                    break
                raise

    def put_file(self, key: str, source: Path) -> None:
        self.client.upload_file(str(source), self.bucket, key)

    def put_bytes(self, key: str, content: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=content_type)

    def iter_object(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body: BinaryIO = response["Body"]
        while chunk := body.read(chunk_size):
            yield chunk

    def delete_prefix(self, prefix: str) -> None:
        while True:
            response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
            if not objects:
                break
            self.client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": objects, "Quiet": True},
            )
            if not response.get("IsTruncated"):
                break


def create_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_backend == "s3":
        return S3ObjectStorage(settings)
    return LocalObjectStorage(settings.storage_root)
