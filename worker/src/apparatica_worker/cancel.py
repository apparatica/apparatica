"""Cancellation of running checks (specs/07 §3, FR-JDG-10).

The API sets `cancel:<id>` to the reason and publishes `<id> <reason>` on `judge:cancel`. One
listener per worker process subscribes to the channel for all its slots; an attempt registers
before it checks the key, so a cancel that comes between the two is not missed. The keys of the
running attempts are also polled now and then: a message published while the subscription was
down still cancels.
"""

import contextlib
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any, get_args

import redis
import structlog

from judge.core.jobs import CANCEL_CHANNEL, CANCEL_NOTES, CancelReason, cancel_key

log = structlog.get_logger(__name__)

LEASE_LOST_NOTE = "cancelled: the check went to another worker"
POLL_S = 5.0


class Cancellation:
    """Why an attempt stops: a cancel of the user, a newer run, or the lease went elsewhere."""

    def __init__(self) -> None:
        self.event = threading.Event()  # the pipeline stops when it is set
        self.reason: CancelReason | None = None
        self.lease_lost = False

    def cancel(self, reason: CancelReason) -> None:
        if not self.event.is_set():
            self.reason = reason
            self.event.set()

    def lose_lease(self) -> None:
        if not self.event.is_set():
            self.lease_lost = True
            self.event.set()

    @property
    def cancelled(self) -> bool:
        """Cancelled by the API: the check ends as `cancelled`."""
        return self.reason is not None

    def note(self) -> str:
        return CANCEL_NOTES[self.reason] if self.reason is not None else LEASE_LOST_NOTE


def parse_reason(value: Any) -> CancelReason:
    text = value.decode() if isinstance(value, bytes) else str(value)
    return text if text in get_args(CancelReason) else "user"  # type: ignore[return-value]


class CancelListener:
    def __init__(self, client: redis.Redis, *, poll_s: float = POLL_S) -> None:
        self._client = client
        self._poll_s = poll_s
        self._watched: dict[uuid.UUID, Cancellation] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._listen, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    @contextlib.contextmanager
    def watch(self, submission_id: uuid.UUID, cancellation: Cancellation) -> Iterator[None]:
        """While the attempt runs, a cancel of its submission sets `cancellation`."""
        with self._lock:
            self._watched[submission_id] = cancellation
        try:
            self._check([submission_id])
            yield
        finally:
            with self._lock:
                self._watched.pop(submission_id, None)

    def _check(self, submissions: list[uuid.UUID]) -> None:
        if not submissions:
            return
        try:
            reasons = self._client.mget([cancel_key(s) for s in submissions])
        except redis.RedisError as error:
            log.warning("cancel keys unavailable", error=str(error))
            return
        for submission_id, reason in zip(submissions, reasons, strict=True):
            if reason is not None:
                self._cancel(submission_id, parse_reason(reason))

    def _cancel(self, submission_id: uuid.UUID, reason: CancelReason) -> None:
        with self._lock:
            cancellation = self._watched.get(submission_id)
        if cancellation is not None and not cancellation.event.is_set():
            log.info("check cancelled", submission_id=str(submission_id), reason=reason)
            cancellation.cancel(reason)

    def _listen(self) -> None:
        while not self._stop.is_set():
            try:
                pubsub: Any = self._client.pubsub(ignore_subscribe_messages=True)  # type: ignore[no-untyped-call]
                with pubsub:
                    pubsub.subscribe(CANCEL_CHANNEL)
                    self._receive(pubsub)
            except redis.RedisError as error:
                log.warning("cancel channel unavailable", error=str(error))
                self._stop.wait(1)

    def _receive(self, pubsub: Any) -> None:
        next_poll = time.monotonic() + self._poll_s
        while not self._stop.is_set():
            message = pubsub.get_message(timeout=min(1.0, self._poll_s))
            if message is not None:
                data = message["data"]
                text = data.decode() if isinstance(data, bytes) else str(data)
                submission, _, reason = text.partition(" ")
                with contextlib.suppress(ValueError):
                    self._cancel(uuid.UUID(submission), parse_reason(reason))
            if time.monotonic() >= next_poll:
                next_poll = time.monotonic() + self._poll_s
                with self._lock:
                    watched = list(self._watched)
                self._check(watched)
