"""The leader of the ingestors (ADR-0009): only one instance runs the periodic tasks.

`SET leader:ingest <instance> NX` with a TTL; the leader renews it on every tick, and another
instance takes it over when the leader stops renewing (died or lost Valkey).
"""

import redis.asyncio

LEADER_KEY = "leader:ingest"
LEADER_TTL_S = 30

# Renew or release only our own lock: an expired lock may belong to another instance now.
_RENEW = """
if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('pexpire', KEYS[1], ARGV[2]) end
return 0
"""
_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end
return 0
"""


class Leadership:
    def __init__(
        self, valkey: redis.asyncio.Redis, owner: str, *, ttl_s: float = LEADER_TTL_S
    ) -> None:
        self._valkey = valkey
        self._owner = owner
        self._ttl_ms = int(ttl_s * 1000)

    async def hold(self) -> bool:
        """Renew the lock if this instance leads, else take it if it is free."""
        renewed = await self._valkey.eval(_RENEW, 1, LEADER_KEY, self._owner, self._ttl_ms)
        if renewed:
            return True
        return bool(await self._valkey.set(LEADER_KEY, self._owner, nx=True, px=self._ttl_ms))

    async def release(self) -> None:
        await self._valkey.eval(_RELEASE, 1, LEADER_KEY, self._owner)
