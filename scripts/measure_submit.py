"""Measure the time of a Submit on a running site (NFR-PERF-02, T3a.7), or of a Run with --kind run
(NFR-PERF-01): p50 of a check without the queue, and where the time goes by stage and parameter set.

Each round submits the reference solution of a demo problem as a new guest (a guest has a quota of
checks per hour) and waits for the verdict over server-sent events. A unique line of whitespace
changes the code, so the build and stage caches (specs/07 §2.3) miss, as they do for a new
solution. Rounds
go one after another: a check never waits behind another one of the measurement.

    python scripts/measure_submit.py --site http://localhost:8080 --problem sync-fifo --rounds 10

Standard library only, so it also runs on a server next to a checkout of the repository. --host
sets the Host header when the site is reached by another address (Caddy from a container). The time
of a check is `finished_at - started_at` of the submission: from the worker taking the job to the
verdict.
"""

import argparse
import http.cookiejar
import json
import secrets
import statistics
import sys
import time
import urllib.request
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROBLEMS = Path(__file__).resolve().parents[1] / "problems"
PRIMARY_SET = "default"  # the id of the primary parameter set (judge.core.stage)


@dataclass
class Round:
    """One measured check."""

    check_s: float  # finished_at - started_at
    queue_s: float  # started_at - created_at
    wall_s: float  # POST to the finalized event, as the client sees it
    stages_s: dict[str, float] = field(default_factory=dict)  # stage key → its instances, s
    sets_s: dict[str, float] = field(default_factory=dict)  # set id → its instances, s


def round_of(submission: dict[str, Any], wall_s: float) -> Round:
    """The times of a finished submission as `GET /submissions/{id}` returns it."""
    created = datetime.fromisoformat(submission["created_at"])
    started = datetime.fromisoformat(submission["started_at"])
    finished = datetime.fromisoformat(submission["finished_at"])
    stages: dict[str, float] = defaultdict(float)
    sets: dict[str, float] = defaultdict(float)
    for stage in submission["stages"]:
        seconds = (stage["duration_ms"] or 0) / 1000
        stages[stage["key"].partition("@")[0]] += seconds
        sets[(stage["param_set"] or {}).get("id", PRIMARY_SET)] += seconds
    return Round(
        check_s=(finished - started).total_seconds(),
        queue_s=(started - created).total_seconds(),
        wall_s=wall_s,
        stages_s=dict(stages),
        sets_s=dict(sets),
    )


def p50(values: Sequence[float]) -> float:
    return statistics.median(values)


def p95(values: Sequence[float]) -> float:
    if len(values) < 2:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def report(rounds: Sequence[Round]) -> list[str]:
    """The table of the measurement: totals, then each stage and each set in order of time."""

    def row(name: str, values: Sequence[float]) -> str:
        return f"{name:<22} {p50(values):>7.2f} {p95(values):>7.2f} {max(values):>7.2f}"

    def keys(parts: Iterable[dict[str, float]]) -> list[str]:
        seen = {key for part in parts for key in part}
        total = {key: sum(part.get(key, 0.0) for part in parts) for key in seen}
        return sorted(seen, key=lambda key: -total[key])

    lines = [f"{len(rounds)} Submits, s{'':<11} {'p50':>7} {'p95':>7} {'max':>7}"]
    lines.append(row("check (no queue)", [r.check_s for r in rounds]))
    lines.append(row("queue", [r.queue_s for r in rounds]))
    lines.append(row("client wall", [r.wall_s for r in rounds]))
    lines.append("by stage (all instances)")
    for key in keys([r.stages_s for r in rounds]):
        lines.append(row(f"  {key}", [r.stages_s.get(key, 0.0) for r in rounds]))
    lines.append("by parameter set (all stages)")
    for key in keys([r.sets_s for r in rounds]):
        lines.append(row(f"  {key}", [r.sets_s.get(key, 0.0) for r in rounds]))
    return lines


class Site:
    """The API of the site as a new guest: its own cookies (the CSRF token, the guest)."""

    def __init__(self, url: str, host: str | None) -> None:
        self._url, self._host = url.rstrip("/"), host
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))

    def _open(self, method: str, path: str, body: Any = None, timeout: float = 30) -> Any:
        headers = {"Content-Type": "application/json"}
        if self._host is not None:
            headers["Host"] = self._host
        if method != "GET":  # double submit of the CSRF token (docs/api.md)
            token = next((c.value or "" for c in self._jar if c.name == "ap_csrf"), "")
            headers["X-CSRF-Token"] = token
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(f"{self._url}{path}", data, headers, method=method)
        return self._opener.open(request, timeout=timeout)

    def get(self, path: str) -> Any:
        with self._open("GET", path) as response:
            return json.load(response)

    def post(self, path: str, body: Any) -> Any:
        with self._open("POST", path, body) as response:
            return json.load(response)

    def wait_finalized(self, submission: str, timeout: float) -> None:
        path = f"/api/v1/submissions/{submission}/events"
        with self._open("GET", path, timeout=timeout) as stream:
            for raw in stream:
                line = raw.decode().strip()
                if line.startswith("data: ") and json.loads(line[6:])["type"] == "finalized":
                    return
        raise RuntimeError(f"the event stream of {submission} ended without `finalized`")


def vary(code: str, nonce: int) -> str:
    """The code after a first line of the nonce's 64 bits as spaces and tabs. The canonical text
    of precheck, the key of the caches, keeps whitespace as it is; a comment would not do, it turns
    into spaces of the same length, and precheck forbids attributes."""
    return "".join(" \t"[nonce >> bit & 1] for bit in range(64)) + "\n" + code


def measure(
    url: str, host: str | None, problem: str, kind: str, code: str, timeout: float
) -> dict[str, Any]:
    """Check the code once as a new guest; return the finished submission and the wall time."""
    site = Site(url, host)
    version = site.get(f"/api/v1/problems/{problem}")["version"]
    code = vary(code, secrets.randbits(64))
    body = {"problem": problem, "version": version, "kind": kind, "code": code}
    started = time.monotonic()
    submission = site.post("/api/v1/submissions", body)["id"]
    site.wait_finalized(submission, timeout)
    wall = time.monotonic() - started
    return {"submission": site.get(f"/api/v1/submissions/{submission}"), "wall_s": wall}


def reference_of(problem: str) -> Path:
    found = sorted((PROBLEMS / problem / "reference").glob("*.sv"))
    if not found:
        raise SystemExit(f"no reference/*.sv in problems/{problem}; pass --solution")
    return found[0]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the time of a Submit (NFR-PERF-02).")
    parser.add_argument("--kind", choices=("submit", "run"), default="submit")
    parser.add_argument("--site", default="http://localhost:8080", help="the site's base URL")
    parser.add_argument("--host", help="the Host header, when the site is reached by another name")
    parser.add_argument("--problem", default="sync-fifo", help="the problem slug")
    parser.add_argument("--solution", type=Path, help="default: the package's reference")
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=300, help="per check, s")
    parser.add_argument("--expect", default="accepted", help="the status every check must get")
    args = parser.parse_args(argv)
    code = (args.solution or reference_of(args.problem)).read_text(encoding="utf-8")

    rounds: list[Round] = []
    for number in range(1, args.rounds + 1):
        result = measure(args.site, args.host, args.problem, args.kind, code, args.timeout)
        submission = result["submission"]
        if submission["status"] != args.expect:
            print(f"round {number}: {submission['status']}, expected {args.expect}")
            return 1
        rounds.append(round_of(submission, result["wall_s"]))
        print(f"round {number}: {rounds[-1].check_s:.2f} s", file=sys.stderr)
    print(f"{args.kind} {args.problem} at {args.site}")
    print("\n".join(report(rounds)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
