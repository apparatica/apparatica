"""Prometheus metrics (NFR-OBS-02) and the log context of requests (NFR-OBS-01)."""

import json
import logging
import re
import time
import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import pytest
import redis
import structlog
from fastapi import APIRouter
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from prometheus_client.core import Metric

from apparatica.core.settings import Settings
from apparatica.judging.metrics import QueueCollector
from apparatica.main import create_app
from apparatica.submissions.api import SubmissionId
from judge.core.jobs import QUEUES, RESULTS_STREAM, position_key

DASHBOARD = Path(__file__).parents[2] / "deploy" / "grafana" / "dashboards" / "apparatica.json"
SUFFIXES = {"counter": ("_total",), "histogram": ("_bucket", "_count", "_sum"), "gauge": ("",)}


def sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    router = APIRouter()
    log = structlog.get_logger("test")

    @router.get("/submissions/{id}")
    async def submission(id: SubmissionId) -> None:
        log.info("inside")

    app.include_router(router, prefix="/api/v1/test")
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_requests_are_counted_by_route_template(client: TestClient) -> None:
    route = "/api/v1/test/submissions/{id}"
    before = sample("apparatica_http_requests_total", method="GET", route=route, status="200")
    unmatched = sample(
        "apparatica_http_requests_total", method="GET", route="unmatched", status="404"
    )
    errors = sample("apparatica_api_errors_total", code="NOT_FOUND")
    client.get(f"/api/v1/test/submissions/{uuid.uuid4()}")
    client.get("/api/v1/nope")
    assert sample("apparatica_http_requests_total", method="GET", route=route, status="200") == (
        before + 1
    )
    assert sample(
        "apparatica_http_requests_total", method="GET", route="unmatched", status="404"
    ) == (unmatched + 1)
    assert sample("apparatica_api_errors_total", code="NOT_FOUND") == errors + 1
    assert sample("apparatica_http_request_duration_seconds_count", method="GET", route=route) > 0


def test_a_path_parameter_may_span_segments(client: TestClient) -> None:
    client.get("/api/v1/problems/mux4/versions/1/assets/img/a.png")  # whatever the status
    text = client.get("/metrics").text
    assert 'route="/api/v1/problems/{slug}/versions/{version}/assets/{path}"' in text
    assert "a.png" not in text


def test_metrics_are_served_outside_the_api(client: TestClient) -> None:
    client.get("/api/v1/health")
    client.get("/metrics")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'apparatica_http_requests_total{method="GET",route="/api/v1/health"' in response.text
    assert 'apparatica_http_requests_total{method="GET",route="/metrics"' in response.text
    assert "/metrics" not in client.get("/api/v1/openapi.json").json()["paths"]


def test_the_submission_of_the_path_is_in_every_record_of_the_request(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    submission = str(uuid.uuid4())
    with caplog.at_level(logging.INFO):
        client.get(f"/api/v1/test/submissions/{submission}")
        client.get("/api/v1/health")
    records: list[dict[str, Any]] = [r.msg for r in caplog.records if isinstance(r.msg, dict)]
    [inside] = [r for r in records if r["event"] == "inside"]
    request, health = [r for r in records if r["event"] == "request"]
    assert inside["submission_id"] == request["submission_id"] == submission
    assert inside["request_id"] == request["request_id"]
    assert "submission_id" not in health  # the context ends with the request


def values(metrics: list[Metric]) -> dict[tuple[str, tuple[str, ...]], float]:
    return {
        (s.name, tuple(s.labels.values())): s.value for metric in metrics for s in metric.samples
    }


def test_the_queues_are_read_at_every_scrape(valkey_url: str) -> None:
    client = redis.Redis.from_url(valkey_url)
    client.flushdb()
    now = time.time()
    client.zadd(position_key("judge.light"), {"a": now - 30, "b": now - 5})
    client.xadd(RESULTS_STREAM, {"r": "{}"})
    collected = values(list(QueueCollector(client, QUEUES).collect()))
    assert collected[("apparatica_queue_waiting", ("judge.light",))] == 2
    assert collected[("apparatica_queue_waiting", ("judge.heavy",))] == 0
    assert 30 <= collected[("apparatica_queue_oldest_wait_seconds", ("judge.light",))] < 60
    assert collected[("apparatica_queue_oldest_wait_seconds", ("judge.rejudge",))] == 0
    assert collected[("apparatica_results_pending", ())] == 1
    client.flushdb()


def test_queue_metrics_are_left_out_while_valkey_is_down() -> None:
    down = redis.Redis(port=1, socket_connect_timeout=0.2)
    collector = QueueCollector(down, QUEUES)
    assert list(collector.collect()) == []
    assert {metric.name for metric in collector.describe()} == {
        "apparatica_queue_waiting",
        "apparatica_queue_oldest_wait_seconds",
        "apparatica_results_pending",
    }


def exposed(families: Iterable[Metric]) -> set[str]:
    return {f.name + suffix for f in families for suffix in SUFFIXES.get(f.type, ())}


def test_the_dashboard_shows_metrics_of_the_api_and_the_ingestor() -> None:
    """The worker checks its own (`apparatica_worker_*`) in its tests."""
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    exprs = [t["expr"] for panel in dashboard["panels"] for t in panel.get("targets", [])]
    shown = {name for expr in exprs for name in re.findall(r"\bapparatica_\w+", expr)}
    queues = QueueCollector(redis.Redis(), QUEUES).describe()  # registered by the ingestor
    names = exposed(REGISTRY.collect()) | exposed(queues)
    missing = {name for name in shown if not name.startswith("apparatica_worker_")} - names
    assert not missing
