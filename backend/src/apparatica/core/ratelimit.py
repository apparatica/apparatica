"""Rate limits against abuse (NFR-SEC-06): moving windows of the `limits` library in valkey-cache.

The counters may be lost (the cache evicts keys and starts empty), and an unreachable cache lets
requests through with a warning: these limits protect the platform, they are not the quotas that
users see. Exact quotas (checks per hour) are counted from the database by their modules.

Clients are told apart by a salted hash of their address (NFR-PRIV-01): an IPv4 address or the /64
network of an IPv6 one, since one host usually gets a whole /64.
"""

import hashlib
import hmac
import ipaddress
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from fastapi import Request
from limits import RateLimitItem, RateLimitItemPerSecond
from limits.aio.storage import MemoryStorage, RedisStorage, Storage
from limits.aio.strategies import MovingWindowRateLimiter
from limits.errors import StorageError

from apparatica.core.errors import ApiError, ErrorCode
from apparatica.core.platform import Window

log = structlog.get_logger(__name__)

# The cache must not hold a request up for long: it fails open instead.
CACHE_TIMEOUT_S = 1.0


@dataclass(frozen=True)
class WindowState:
    remaining: int
    reset_at: datetime | None  # when one more becomes available; None while any are left


class RateLimiter:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage
        self._limiter = MovingWindowRateLimiter(storage)

    @classmethod
    def connect(cls, cache_url: str | None) -> "RateLimiter":
        """Counters in valkey-cache, or in the memory of the process without it."""
        if cache_url is None:
            return cls(MemoryStorage())
        storage = RedisStorage(
            f"async+{cache_url}",
            wrap_exceptions=True,
            implementation="redispy",
            socket_connect_timeout=CACHE_TIMEOUT_S,
            socket_timeout=CACHE_TIMEOUT_S,
        )
        return cls(storage)

    async def hit(self, window: Window, *key: str) -> float | None:
        """Count one event. When the window is full, nothing is counted and the result is the
        number of seconds until the next event is allowed."""
        item = _item(window)
        try:
            if await self._limiter.hit(item, *key):
                return None
            stats = await self._limiter.get_window_stats(item, *key)
        except StorageError as error:
            log.warning("rate limit not checked", key=key[0], error=str(error.storage_error))
            return None
        return max(stats.reset_time - time.time(), 0.0)

    async def state(self, window: Window, *key: str) -> WindowState:
        try:
            stats = await self._limiter.get_window_stats(_item(window), *key)
        except StorageError as error:
            log.warning("rate limit not read", key=key[0], error=str(error.storage_error))
            return WindowState(window.limit, None)
        remaining = max(stats.remaining, 0)
        reset_at = None if remaining else datetime.fromtimestamp(stats.reset_time, UTC)
        return WindowState(remaining, reset_at)


def _item(window: Window) -> RateLimitItem:
    return RateLimitItemPerSecond(window.limit, window.window_s)


def rate_limited(
    quota: str,
    detail: str,
    *,
    limit: int,
    window_s: int | None = None,
    retry_after_s: float | None = None,
) -> ApiError:
    """RATE_LIMITED with `params.quota` naming the limit; `retry_after_s` and the `Retry-After`
    header when it is known when the next attempt can pass."""
    params: dict[str, object] = {"quota": quota, "limit": limit}
    headers = None
    if window_s is not None:
        params["window_s"] = window_s
    if retry_after_s is not None:
        seconds = max(1, math.ceil(retry_after_s))
        params["retry_after_s"] = seconds
        headers = {"Retry-After": str(seconds)}
    return ApiError(ErrorCode.RATE_LIMITED, detail, params=params, headers=headers)


class ClientAddresses:
    """Salted hashes of client addresses: rate limit keys and `submissions.client_ip_hash`."""

    def __init__(self, salt: bytes) -> None:
        if len(salt) < 32:
            raise ValueError("the address salt must have at least 32 bytes")
        self._salt = salt

    def hash(self, request: Request) -> str | None:
        """The address comes from the proxy (`--forwarded-allow-ips`); None without a client."""
        if request.client is None:
            return None
        host = request.client.host
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            network = host  # not an IP address, e.g. a unix socket or the test client
        else:
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is None:
                network = str(ipaddress.IPv6Network((address, 64), strict=False))
            elif isinstance(address, ipaddress.IPv6Address):
                network = str(address.ipv4_mapped)
            else:
                network = str(address)
        return hmac.new(self._salt, network.encode(), hashlib.sha256).hexdigest()
