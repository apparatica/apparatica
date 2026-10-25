"""UUIDv7 identifiers (RFC 9562): time-ordered, used for primary keys and request ids (specs/04 §4).

Python 3.13 has no `uuid.uuid7`; this is the RFC layout with a monotonic counter in `rand_a`.
"""

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = 0
_counter = 0


def uuid7() -> uuid.UUID:
    """48 bits of Unix milliseconds, version 7, a 12-bit counter that keeps ids of the same
    millisecond ordered, variant bits, 62 random bits."""
    global _last_ms, _counter
    with _lock:
        now = time.time_ns() // 1_000_000
        if now > _last_ms:
            _last_ms, _counter = now, int.from_bytes(os.urandom(2)) & 0x1FF
        else:  # same millisecond or a clock step back: keep counting from the last one
            _counter += 1
            if _counter > 0xFFF:
                _last_ms, _counter = _last_ms + 1, 0
        ms, counter = _last_ms, _counter
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76 | counter << 64
    value |= 0b10 << 62 | int.from_bytes(os.urandom(8)) & ((1 << 62) - 1)
    return uuid.UUID(int=value)
