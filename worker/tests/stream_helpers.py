import json
from typing import Any, cast

import redis


def read_stream(client: redis.Redis, key: str) -> list[tuple[str, Any]]:
    """The entries of a stream of the worker: (id, the JSON of its only field)."""
    entries = cast(list[tuple[bytes, dict[bytes, bytes]]], client.xrange(key))
    return [(entry_id.decode(), json.loads(*fields.values())) for entry_id, fields in entries]
