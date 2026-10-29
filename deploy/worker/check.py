"""Check that a running stand judges submissions end to end: API, queue, worker, sandbox, ingestor.

    just stand-check        # the stand of deploy/compose.yaml, through Caddy

A guest submits the reference solution and a mutant of a demo problem, follows each check over
server-sent events until `finalized` and compares the verdict with the package. The wrong answer
also has to keep its waveform: the FST link of the failed stage answers with a redirect. Exit code
1 on a failure.
Environment: SITE_URL (Caddy, as the containers reach it), SITE_HOST (its site address) and
CHECK_TIMEOUT_S (per check).
"""

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROBLEMS = Path("/opt/apparatica/problems")
CHECKS = [  # (what, file of the package, expected status, stage with the FST)
    ("reference", "mux4/reference/mux4.sv", "accepted", None),
    ("mutant", "mux4/mutants/m01_swapped_inputs.sv", "wrong_answer", "sim_full"),
]

SITE = os.environ["SITE_URL"]
HOST = os.environ["SITE_HOST"]
TIMEOUT_S = float(os.environ.get("CHECK_TIMEOUT_S", "300"))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # the presigned URL is for the browser's address of the storage


jar = http.cookiejar.CookieJar()  # the guest cookie of the first submission
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)


def request(method: str, path: str, body: Any = None, timeout: float = 30) -> Any:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Host": HOST, "Content-Type": "application/json"}
    req = urllib.request.Request(f"{SITE}{path}", data, headers, method=method)
    return opener.open(req, timeout=timeout)


def get_json(path: str) -> Any:
    with request("GET", path) as response:
        return json.load(response)


def follow(submission: str) -> dict[str, Any]:
    """Read the event stream to `finalized` and return it."""
    deadline = time.monotonic() + TIMEOUT_S
    with request("GET", f"/api/v1/submissions/{submission}/events", timeout=TIMEOUT_S) as stream:
        for raw in stream:
            line = raw.decode().rstrip("\n")
            if line.startswith("data: "):
                event = json.loads(line[len("data: ") :])
                if event["type"] == "finalized":
                    return dict(event)
            if time.monotonic() > deadline:
                break
    raise AssertionError(f"no finalized event in {TIMEOUT_S:.0f} s")


def judge(what: str, file: str, expected: str, fst_stage: str | None) -> None:
    version = get_json("/api/v1/problems/mux4")["version"]
    code = (PROBLEMS / file).read_text(encoding="utf-8")
    body = {"problem": "mux4", "version": version, "kind": "submit", "code": code}
    with request("POST", "/api/v1/submissions", body) as response:
        submission = json.load(response)["id"]
    started = time.monotonic()
    finalized = follow(submission)
    status = get_json(f"/api/v1/submissions/{submission}")["status"]
    took = time.monotonic() - started
    if finalized["status"] != expected or status != expected:
        raise AssertionError(f"{status} (event {finalized['status']}), expected {expected}")
    if fst_stage is not None:
        path = f"/api/v1/submissions/{submission}/artifacts/fst?stage={fst_stage}"
        try:
            request("GET", path).close()
        except urllib.error.HTTPError as error:
            if error.code != 302:
                raise
        else:
            raise AssertionError("the FST link did not redirect to the storage")
    print(f"ok   {what}: {expected} in {took:.1f} s")


def main() -> int:
    failed = False
    for check in CHECKS:
        try:
            judge(*check)
        except Exception as error:  # every failure is reported, the check goes on
            failed = True
            detail = error.read().decode() if isinstance(error, urllib.error.HTTPError) else ""
            print(f"FAIL {check[0]}: {error!r} {detail}".rstrip())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
