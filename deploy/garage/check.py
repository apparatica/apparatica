"""Check the object storage of a running stand against what the platform needs (ADR-0013).

    just stand-check        # the stand of deploy/compose.yaml, through Caddy

Checks: the permissions of the component keys, presigned GET with an attachment disposition,
CORS of the artifacts bucket, the waveview website. Lifecycle rules are readable only by the
owner of a bucket: garage-setup reads them back after setting them. Exit code 1 on a failure.
Environment: S3_URL, WEB_URL (the waveview website), ALLOWED_ORIGINS (comma-separated) and the
keys of the components, KEY_<COMPONENT>_ID / KEY_<COMPONENT>_SECRET.
"""

import os
import sys
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

failures: list[str] = []


def check(what: str, test: Callable[[], object]) -> None:
    try:
        test()
    except Exception as error:  # every failure is reported, the check goes on
        failures.append(what)
        print(f"FAIL {what}: {error!r}")
    else:
        print(f"ok   {what}")


def client(component: str):  # type: ignore[no-untyped-def]
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_URL"],
        region_name="garage",
        aws_access_key_id=os.environ[f"KEY_{component.upper()}_ID"],
        aws_secret_access_key=os.environ[f"KEY_{component.upper()}_SECRET"],
        config=Config(
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def denied(call: Callable[[], object]) -> None:
    try:
        call()
    except ClientError as error:
        if error.response["Error"]["Code"] in ("AccessDenied", "Forbidden", "403"):
            return
        raise
    raise AssertionError("the call was allowed")


def http(
    url: str, method: str = "GET", headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return (
                response.status,
                {k.lower(): v for k, v in response.headers.items()},
                response.read(),
            )
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read()


def main() -> int:
    api, worker, ingest = client("api"), client("worker"), client("ingest")
    key = f"check/{uuid.uuid4()}.log"
    body = b"stand check\n"

    check("api writes packages", lambda: api.put_object(Bucket="packages", Key=key, Body=body))
    check("worker reads packages", lambda: worker.get_object(Bucket="packages", Key=key))
    check(
        "worker cannot write packages",
        lambda: denied(lambda: worker.put_object(Bucket="packages", Key=key, Body=body)),
    )
    check(
        "worker writes artifacts", lambda: worker.put_object(Bucket="artifacts", Key=key, Body=body)
    )
    check("ingest reads artifacts", lambda: ingest.get_object(Bucket="artifacts", Key=key))
    check(
        "ingest cannot write artifacts",
        lambda: denied(lambda: ingest.put_object(Bucket="artifacts", Key=key, Body=body)),
    )
    check(
        "api cannot write artifacts",
        lambda: denied(lambda: api.put_object(Bucket="artifacts", Key=key, Body=body)),
    )
    check(
        "api cannot read build-cache",
        lambda: denied(lambda: api.get_object(Bucket="build-cache", Key=key)),
    )

    def presigned() -> None:
        url = api.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": "artifacts",
                "Key": key,
                "ResponseContentType": "application/octet-stream",
                "ResponseContentDisposition": 'attachment; filename="sim.log"',
            },
            ExpiresIn=60,
        )
        status, headers, data = http(url)
        assert (status, data) == (200, body), (status, data)
        assert headers.get("content-type") == "application/octet-stream", headers
        assert headers.get("content-disposition") == 'attachment; filename="sim.log"', headers
        tampered = url.replace("X-Amz-Expires=60", "X-Amz-Expires=61")
        assert http(tampered)[0] == 403, "a changed presigned URL is accepted"

    check("presigned GET with attachment disposition", presigned)

    def cors() -> None:
        url = api.generate_presigned_url(
            "get_object", Params={"Bucket": "artifacts", "Key": key}, ExpiresIn=60
        )
        for origin in os.environ["ALLOWED_ORIGINS"].split(","):
            preflight = {"Origin": origin, "Access-Control-Request-Method": "GET"}
            status, headers, _ = http(url, "OPTIONS", preflight)
            # Exactly the origin: a list of origins in the header is rejected by browsers.
            assert status == 200, (origin, status)
            assert headers.get("access-control-allow-origin") == origin, (origin, headers)
            status, headers, _ = http(url, headers={"Origin": origin})
            assert headers.get("access-control-allow-origin") == origin, (origin, headers)
        # Another origin: the preflight is refused, and a simple GET (no preflight) carries no
        # Allow-Origin, so the browser does not hand the body to the page. Garage puts "*" on
        # error answers only.
        foreign = "https://evil.example"
        preflight = {"Origin": foreign, "Access-Control-Request-Method": "GET"}
        assert http(url, "OPTIONS", preflight)[0] == 403
        status, headers, _ = http(url, headers={"Origin": foreign})
        assert status == 200, status
        assert "access-control-allow-origin" not in headers, headers

    check("CORS of artifacts: the allowed origins only", cors)

    def website() -> None:
        status, _, data = http(f"{os.environ['WEB_URL']}/")
        assert status == 200, status
        assert b"apparatica-waveview" in data, data[:200]

    check("waveview website serves its index", website)

    for name, s3, bucket in (("api", api, "packages"), ("worker", worker, "artifacts")):
        try:
            s3.delete_object(Bucket=bucket, Key=key)
        except ClientError as error:
            print(f"     cleanup of {bucket}/{key} by {name}: {error}")
    if failures:
        print(f"failed: {len(failures)}")
        return 1
    print("storage: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
