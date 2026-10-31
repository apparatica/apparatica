"""The metrics of the worker on the Grafana dashboard (deploy/grafana, NFR-OBS-02)."""

import json
import re
from pathlib import Path

from prometheus_client import REGISTRY

import apparatica_worker.metrics  # noqa: F401  # declares the metrics

DASHBOARD = Path(__file__).parents[2] / "deploy" / "grafana" / "dashboards" / "apparatica.json"
SUFFIXES = {"counter": ("_total",), "histogram": ("_bucket", "_count", "_sum"), "gauge": ("",)}


def test_the_dashboard_shows_metrics_of_the_worker() -> None:
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    exprs = [t["expr"] for panel in dashboard["panels"] for t in panel.get("targets", [])]
    shown = {name for expr in exprs for name in re.findall(r"\bapparatica_worker_\w+", expr)}
    names = {f.name + s for f in REGISTRY.collect() for s in SUFFIXES.get(f.type, ())}
    assert shown
    assert not shown - names
