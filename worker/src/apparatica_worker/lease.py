"""The lease of a running check (specs/07 §3): one worker runs a check at a time.

The Redis broker requeues the message of a dead worker; a duplicate of a message whose check still
runs finds the lease taken and is dropped. The lease lives `LEASE_TTL_S` and is renewed every
`LEASE_RENEW_S`, so a dead worker loses it before its message is requeued.
"""

import threading
import uuid
from types import TracebackType
from typing import Self

import redis
import structlog

from judge.core.jobs import LEASE_RENEW_S, LEASE_TTL_S, lease_key

log = structlog.get_logger(__name__)

# Renew or release only a lease of this owner: an expired lease may belong to another worker now.
_RENEW = """
if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('pexpire', KEYS[1], ARGV[2]) end
return 0
"""
_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end
return 0
"""


class Lease:
    """`with Lease(...) as lease:` takes the lease if it is free (`held`) and keeps renewing it;
    `lost` is set when a renewal finds it gone: the check must stop."""

    def __init__(
        self,
        client: redis.Redis,
        submission_id: uuid.UUID,
        owner: str,
        *,
        ttl_s: float = LEASE_TTL_S,
        renew_s: float = LEASE_RENEW_S,
    ) -> None:
        self._client = client
        self._key = lease_key(submission_id)
        self._owner = owner
        self._ttl_ms = int(ttl_s * 1000)
        self._renew_s = renew_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._renew, daemon=True)
        self.held = False
        self.lost = threading.Event()

    def __enter__(self) -> Self:
        self.held = bool(self._client.set(self._key, self._owner, nx=True, px=self._ttl_ms))
        if self.held:
            self._thread.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.held:
            return
        self._stop.set()
        self._thread.join()
        try:
            self._client.eval(_RELEASE, 1, self._key, self._owner)
        except redis.RedisError as failure:  # it expires by itself
            log.warning("lease not released", key=self._key, error=repr(failure))

    def _renew(self) -> None:
        while not self._stop.wait(self._renew_s):
            try:
                renewed = self._client.eval(_RENEW, 1, self._key, self._owner, self._ttl_ms)
            except redis.RedisError as failure:  # may come back before the TTL runs out
                log.warning("lease not renewed", key=self._key, error=repr(failure))
                continue
            if not renewed:
                log.error("lease lost", key=self._key)
                self.lost.set()
                return
