"""HTTP caching of responses (specs/05 §1): public GETs carry an ETag and Cache-Control."""

import hashlib

from fastapi import Request, Response
from pydantic import BaseModel
from starlette.responses import StreamingResponse

PUBLIC = "public, max-age=60, stale-while-revalidate=300"
PRIVATE = "private, no-store"
IMMUTABLE = "public, max-age=31536000, immutable"  # data of a problem version never changes


def cached_json(request: Request, body: BaseModel, cache_control: str = PUBLIC) -> Response:
    """The model as JSON with a strong ETag; 304 when the client already has this version."""
    data = body.model_dump_json().encode()
    return cached_bytes(request, data, "application/json", cache_control)


def cached_bytes(
    request: Request,
    data: bytes,
    media_type: str,
    cache_control: str,
    headers: dict[str, str] | None = None,
) -> Response:
    """The data with a strong ETag; 304 when the client already has this version."""
    etag = '"' + hashlib.sha256(data).hexdigest()[:32] + '"'
    headers = {**(headers or {}), "ETag": etag, "Cache-Control": cache_control}
    if etag in _etags(request.headers.get("if-none-match", "")):
        return Response(status_code=304, headers=headers)
    return Response(data, media_type=media_type, headers=headers)


def _etags(header: str) -> set[str]:
    return {tag.strip().removeprefix("W/") for tag in header.split(",") if tag.strip()}


class EventStreamResponse(StreamingResponse):
    """A `text/event-stream` route. Unlike `fastapi.sse.EventSourceResponse` the handler is not a
    generator: it returns the stream itself, so it can fail with problem+json before streaming."""

    media_type = "text/event-stream"
