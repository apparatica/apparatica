"""Prometheus metrics (NFR-OBS-02): the requests and errors of the API, `/metrics`.

Metrics live in the default registry of prometheus_client, next to the collectors of the process
(CPU, memory, GC); every module declares its own. The API serves them at `/metrics` on its own
port, outside `/api/v1`: the proxy routes only `/api/*`, so only Prometheus in the internal network
reaches them. The ingestor serves the same registry on `APX_METRICS_PORT`.
"""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Scope

METRICS_PATH = "/metrics"
UNMATCHED = "unmatched"  # the route of a request that matched none: no label per unknown path

HTTP_REQUESTS = Counter(
    "apparatica_http_requests",
    "Requests of the API by route template and response status",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "apparatica_http_request_duration_seconds",
    "Time to the end of the response; event streams are not timed",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
API_ERRORS = Counter(
    "apparatica_api_errors", "problem+json responses of the API by error code", ["code"]
)


def route_template(scope: Scope) -> str:
    """The path template of the route the request matched, e.g. `/api/v1/submissions/{id}`.

    FastAPI puts into the scope the route of its router, whose template lacks the prefix the
    router was included with: the prefix is the part of the path before the route matched.
    """
    route = scope.get("route")
    template: str | None = getattr(route, "path_format", None)
    regex = getattr(route, "path_regex", None)
    if template is None or regex is None:
        return UNMATCHED
    path: str = scope["path"]
    for start, char in enumerate(path):
        if char == "/" and regex.match(path[start:]):
            return path[:start] + template
    return UNMATCHED


async def metrics_endpoint(request: Request) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
