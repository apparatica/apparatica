"""Set up the Garage of the stand (ADR-0013): layout, buckets, keys, website, CORS, lifecycle,
the waveview site.

Idempotent: run on every `docker compose up` by the `garage-setup` service (the api image: Python
and boto3). The cluster is configured through the admin API; CORS and lifecycle rules through the
S3 API, as the application would, with a temporary key that owns the buckets. The same key uploads
the waveview builds of WAVEVIEW_DIR (the `waveview` service copies them out of their image).

Environment: GARAGE_ADMIN_URL, GARAGE_ADMIN_TOKEN, GARAGE_S3_URL, GARAGE_CAPACITY_GB, CORS_ORIGINS
(comma-separated), WAVEVIEW_DIR and the keys of the components, KEY_<COMPONENT>_ID /
KEY_<COMPONENT>_SECRET.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

BUCKETS = ("packages", "artifacts", "build-cache", "waveview")
# Who may do what (ADR-0013). The ingestor deletes expired artifacts: in Garage that is `write`.
PERMISSIONS: dict[str, dict[str, set[str]]] = {
    "api": {"packages": {"read", "write"}, "artifacts": {"read"}},
    "worker": {"packages": {"read"}, "artifacts": {"write"}, "build-cache": {"read", "write"}},
    "ingest": {"artifacts": {"read", "write"}},
}
# Retention (specs/07 §4.4): compiled simulations live a day. Incomplete uploads go everywhere.
# Other retention of artifacts needs rules by kind, which key prefixes cannot express: the
# periodic task of the ingestor applies it by artifacts.expires_at (ADR-0013).
EXPIRATION_DAYS = {"build-cache": 1}
ABORT_UPLOADS_DAYS = 1
SETUP_KEY = "apparatica-setup"
# The root of the website; the viewer lives under its version, <version>/index.html.
PLACEHOLDER = b"""<!doctype html><meta charset="utf-8"><title>waveview</title>
<!-- apparatica-waveview: the waveform viewer of Apparatica, under /<version>/ -->
"""
# Content types of the waveview files: the website serves what is stored.
WAVEVIEW_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".wasm": "application/wasm",
    ".txt": "text/plain; charset=utf-8",
}


def admin(method: str, endpoint: str, body: object | None = None, **query: str) -> Any:
    url = f"{os.environ['GARAGE_ADMIN_URL']}/v2/{endpoint}"
    if query:
        url += "?" + "&".join(f"{key}={value}" for key, value in query.items())
    request = urllib.request.Request(
        url,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['GARAGE_ADMIN_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        data = response.read()
    return json.loads(data) if data else None


def find(endpoint: str, **query: str) -> Any | None:
    try:
        return admin("GET", endpoint, **query)
    except urllib.error.HTTPError as error:
        if error.code in (400, 404):
            return None
        raise


def wait_for_garage() -> dict[str, Any]:
    for _ in range(60):
        try:
            return admin("GET", "GetClusterStatus")  # type: ignore[no-any-return]
        except (urllib.error.URLError, ConnectionError):
            time.sleep(1)
    sys.exit("Garage admin API does not answer")


def ensure_layout(status: dict[str, Any]) -> None:
    [node] = status["nodes"]
    if node["role"] is not None:
        return
    capacity = int(float(os.environ.get("GARAGE_CAPACITY_GB", "10")) * 10**9)
    admin(
        "POST",
        "UpdateClusterLayout",
        {"roles": [{"id": node["id"], "zone": "dc1", "capacity": capacity, "tags": []}]},
    )
    layout = admin("GET", "GetClusterLayout")
    admin("POST", "ApplyClusterLayout", {"version": layout["version"] + 1})
    print(f"layout: node {node['id'][:16]} with {capacity // 10**9} GB")


def ensure_bucket(alias: str) -> str:
    bucket = find("GetBucketInfo", globalAlias=alias)
    if bucket is None:
        bucket = admin("POST", "CreateBucket", {"globalAlias": alias})
        print(f"bucket: {alias} created")
    return str(bucket["id"])


def ensure_key(name: str, key_id: str, secret: str) -> None:
    key = find("GetKeyInfo", id=key_id)
    if key is None:
        admin(
            "POST",
            "ImportKey",
            {"accessKeyId": key_id, "secretAccessKey": secret, "name": f"apparatica-{name}"},
        )
        print(f"key: {name} imported")


def allow(bucket_id: str, key_id: str, permissions: set[str]) -> None:
    admin(
        "POST",
        "AllowBucketKey",
        {
            "bucketId": bucket_id,
            "accessKeyId": key_id,
            "permissions": {p: p in permissions for p in ("read", "write", "owner")},
        },
    )
    # Allow only adds: drop what the table no longer grants.
    revoked = {"read", "write", "owner"} - permissions
    if revoked:
        admin(
            "POST",
            "DenyBucketKey",
            {
                "bucketId": bucket_id,
                "accessKeyId": key_id,
                "permissions": {p: p in revoked for p in ("read", "write", "owner")},
            },
        )


def configure_buckets(buckets: dict[str, str]) -> None:
    """CORS and lifecycle through the S3 API, with a temporary owner key."""
    key = admin("POST", "CreateKey", {"name": SETUP_KEY})
    try:
        for bucket_id in buckets.values():
            allow(bucket_id, key["accessKeyId"], {"read", "write", "owner"})
        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ["GARAGE_S3_URL"],
            region_name="garage",
            aws_access_key_id=key["accessKeyId"],
            aws_secret_access_key=key["secretAccessKey"],
            config=Config(
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
        # The problem page reads FST by presigned URL; the waveview frame gets the bytes from it.
        # One rule per origin: Garage answers with every origin of the matching rule joined by
        # commas, which browsers reject.
        s3.put_bucket_cors(
            Bucket="artifacts",
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": [origin],
                        "AllowedMethods": ["GET", "HEAD"],
                        "AllowedHeaders": ["*"],
                        "ExposeHeaders": ["Content-Length", "Content-Range", "ETag"],
                        "MaxAgeSeconds": 3600,
                    }
                    for origin in origins
                ]
            },
        )
        for alias in buckets:
            rules: list[dict[str, Any]] = [
                {
                    "ID": "abort-incomplete-uploads",
                    "Status": "Enabled",
                    "Filter": {"Prefix": ""},
                    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": ABORT_UPLOADS_DAYS},
                }
            ]
            if alias in EXPIRATION_DAYS:
                rules.append(
                    {
                        "ID": "expire",
                        "Status": "Enabled",
                        "Filter": {"Prefix": ""},
                        "Expiration": {"Days": EXPIRATION_DAYS[alias]},
                    }
                )
            s3.put_bucket_lifecycle_configuration(
                Bucket=alias, LifecycleConfiguration={"Rules": rules}
            )
            stored = s3.get_bucket_lifecycle_configuration(Bucket=alias)["Rules"]
            if sorted(rule["ID"] for rule in stored) != sorted(rule["ID"] for rule in rules):
                sys.exit(f"lifecycle rules of {alias} were not stored: {stored}")
        if not exists(s3, "waveview", "index.html"):
            s3.put_object(
                Bucket="waveview", Key="index.html", Body=PLACEHOLDER, ContentType="text/html"
            )
        print(f"buckets: CORS for {', '.join(origins) or 'no origins'}; lifecycle rules stored")
        publish_waveview(s3, Path(os.environ.get("WAVEVIEW_DIR", "/nonexistent")))
    finally:
        admin("POST", "DeleteKey", id=key["accessKeyId"])


def exists(s3: Any, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise
    return True


def publish_waveview(s3: Any, root: Path) -> None:
    """Every version of the waveview site in `root` (<version>/...) that the bucket lacks. A version
    is immutable: its index.html goes last and marks it published."""
    versions = sorted(d for d in root.glob("*") if (d / "index.html").is_file())
    for version in versions:
        if exists(s3, "waveview", f"{version.name}/index.html"):
            print(f"waveview: {version.name} already published")
            continue
        files = sorted(p for p in version.rglob("*") if p.is_file())
        files.sort(key=lambda p: p.name == "index.html")
        for path in files:
            s3.put_object(
                Bucket="waveview",
                Key=f"{version.name}/{path.relative_to(version).as_posix()}",
                Body=path.read_bytes(),
                ContentType=WAVEVIEW_TYPES.get(path.suffix, "application/octet-stream"),
            )
        print(f"waveview: {version.name} published ({len(files)} files)")
    if not versions:
        print("waveview: no build to publish")


def main() -> None:
    ensure_layout(wait_for_garage())
    buckets = {alias: ensure_bucket(alias) for alias in BUCKETS}
    admin(
        "POST",
        "UpdateBucket",
        {"websiteAccess": {"enabled": True, "indexDocument": "index.html"}},
        id=buckets["waveview"],
    )
    for name, grants in PERMISSIONS.items():
        key_id = os.environ[f"KEY_{name.upper()}_ID"]
        ensure_key(name, key_id, os.environ[f"KEY_{name.upper()}_SECRET"])
        for alias in BUCKETS:
            allow(buckets[alias], key_id, grants.get(alias, set()))
    configure_buckets(buckets)
    print("garage: ready")


if __name__ == "__main__":
    main()
