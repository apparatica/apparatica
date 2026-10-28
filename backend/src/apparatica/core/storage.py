"""Object storage through the S3 API (ADR-0013): Garage in docker compose, any S3 elsewhere.

Buckets are separate per kind of data because Garage grants keys per bucket; the API writes
`packages` (problem import) and reads event journals from `artifacts`, the ingestor deletes
expired `artifacts`. Calls are blocking: async code runs them in a thread.

Browsers download artifacts by presigned URLs (specs/07 §4.4). The host is part of the signature,
so they are signed for the public endpoint (`s3_public_url`), which the API itself may not reach;
signing needs no network.
"""

from functools import cached_property
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config

from apparatica.core.settings import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class Storage:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @cached_property
    def _client(self) -> "S3Client":
        """Made on first use: without keys botocore looks for credentials, also on the network
        (instance metadata), and a process that never touches the storage must not wait for it."""
        return self._make_client(self._settings.s3_endpoint_url)

    @cached_property
    def _public(self) -> "S3Client":
        settings = self._settings
        return self._make_client(settings.s3_public_url or settings.s3_endpoint_url)

    def _make_client(self, endpoint_url: str | None) -> "S3Client":
        settings = self._settings
        secret = settings.s3_secret_access_key
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=secret.get_secret_value() if secret else None,
            # Buckets by path, not by subdomain; checksums only where the API requires them:
            # S3-compatible stores do not all support the defaults of botocore >= 1.36.
            config=Config(
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, bucket: str, key: str) -> bytes:
        return self._client.get_object(Bucket=bucket, Key=key)["Body"].read()

    def download_url(self, bucket: str, key: str, filename: str, expires_s: int) -> str:
        """A presigned GET of the public endpoint that saves the object as `filename`."""
        return self._public.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                "ResponseContentType": "application/octet-stream",
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=expires_s,
        )

    def delete(self, bucket: str, key: str) -> None:
        """Deleting a missing object succeeds: retried deletes are harmless."""
        self._client.delete_object(Bucket=bucket, Key=key)
