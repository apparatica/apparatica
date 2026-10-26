"""Object storage through the S3 API (ADR-0013): Garage in docker compose, any S3 elsewhere.

Buckets are separate per kind of data because Garage grants keys per bucket; the API writes
`packages` (problem import), the ingestor deletes expired `artifacts`. Calls are blocking: async
code runs them in a thread.
"""

from typing import TYPE_CHECKING

import boto3
from botocore.config import Config

from apparatica.core.settings import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class Storage:
    def __init__(self, settings: Settings) -> None:
        secret = settings.s3_secret_access_key
        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
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

    def delete(self, bucket: str, key: str) -> None:
        """Deleting a missing object succeeds: retried deletes are harmless."""
        self._client.delete_object(Bucket=bucket, Key=key)
