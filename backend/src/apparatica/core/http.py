"""HTTP caching of JSON responses (specs/05 §1): public GETs carry an ETag and Cache-Control."""

import hashlib

from fastapi import Request, Response
from pydantic import BaseModel

PUBLIC = "public, max-age=60, stale-while-revalidate=300"
PRIVATE = "private, no-store"
IMMUTABLE = "public, max-age=31536000, immutable"  # data of a problem version never changes


def cached_json(request: Request, body: BaseModel, cache_control: str = PUBLIC) -> Response:
    """The model as JSON with a strong ETag; 304 when the client already has this version."""
    data = body.model_dump_json().encode()
    etag = '"' + hashlib.sha256(data).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Cache-Control": cache_control}
    if etag in _etags(request.headers.get("if-none-match", "")):
        return Response(status_code=304, headers=headers)
    return Response(data, media_type="application/json", headers=headers)


def _etags(header: str) -> set[str]:
    return {tag.strip().removeprefix("W/") for tag in header.split(",") if tag.strip()}
