"""Cancellation in a worker (specs/07 §3, FR-JDG-10): the channel, the key, the poll."""

import time
import uuid
from collections.abc import Iterator

import pytest
import redis

from apparatica_worker.cancel import LEASE_LOST_NOTE, Cancellation, CancelListener
from judge.core.jobs import CANCEL_CHANNEL, CANCEL_NOTES, cancel_key


@pytest.fixture
def listener(valkey_url: str) -> Iterator[CancelListener]:
    cancels = CancelListener(redis.Redis.from_url(valkey_url), poll_s=0.2)
    cancels.start()
    time.sleep(0.2)  # subscribed
    yield cancels
    cancels.stop()


def wait(cancellation: Cancellation, seconds: float = 3) -> bool:
    return cancellation.event.wait(seconds)


def test_a_message_cancels_the_running_attempt(valkey_url: str, listener: CancelListener) -> None:
    client = redis.Redis.from_url(valkey_url)
    running, other = uuid.uuid4(), uuid.uuid4()
    cancellation = Cancellation()
    with listener.watch(running, cancellation):
        client.publish(CANCEL_CHANNEL, f"{other} user")  # not ours
        client.publish(CANCEL_CHANNEL, "not-an-id user")
        time.sleep(0.1)
        assert not cancellation.event.is_set()
        client.publish(CANCEL_CHANNEL, f"{running} preempted")
        assert wait(cancellation)
    assert (cancellation.cancelled, cancellation.reason) == (True, "preempted")
    assert cancellation.note() == CANCEL_NOTES["preempted"]


def test_a_key_set_before_the_attempt_cancels_it_at_once(
    valkey_url: str, listener: CancelListener
) -> None:
    client = redis.Redis.from_url(valkey_url)
    submission = uuid.uuid4()
    client.set(cancel_key(submission), "user")
    cancellation = Cancellation()
    with listener.watch(submission, cancellation):
        assert cancellation.event.is_set()  # before the attempt runs anything
    assert cancellation.reason == "user"


def test_a_lost_message_is_found_by_the_poll(valkey_url: str, listener: CancelListener) -> None:
    client = redis.Redis.from_url(valkey_url)
    submission = uuid.uuid4()
    cancellation = Cancellation()
    with listener.watch(submission, cancellation):
        client.set(cancel_key(submission), "user")  # the message never came
        assert wait(cancellation)


def test_a_lost_lease_is_not_a_cancel() -> None:
    cancellation = Cancellation()
    cancellation.lose_lease()
    cancellation.cancel("user")  # too late: the attempt already stops for its lease
    assert cancellation.event.is_set()
    assert (cancellation.cancelled, cancellation.lease_lost) == (False, True)
    assert cancellation.note() == LEASE_LOST_NOTE
