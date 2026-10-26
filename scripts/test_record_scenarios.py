from judge.core.events import DoneEvent, LogEvent, StageEndEvent, StageStartEvent
from judge.core.stage import StageResult
from judge.core.verdict import Verdict
from record_scenarios import stream_ids, timeline, worker_events

START = StageStartEvent(stage="lint", stage_type="lint", ordinal=1)
END = StageEndEvent(result=StageResult(key="lint", type="lint", ordinal=1, status="passed"))


def log(text: str, ch: str = "out") -> LogEvent:
    return LogEvent(stage="lint", ch=ch, text=text)  # type: ignore[arg-type]


def test_log_lines_are_glued_like_the_worker_glues_them() -> None:
    events = worker_events(
        [(0, START), (10, log("a")), (50, log("b")), (60, log("c", "err")), (200, log("d"))],
        attempt=1,
    )
    assert [(ms, e["type"], e.get("ch"), e.get("text")) for ms, e in events] == [
        (0, "stage_start", None, None),
        (10, "log", "out", "a\nb\n"),
        (60, "log", "err", "c\n"),
        (200, "log", "out", "d\n"),
    ]
    assert {e["attempt"] for _, e in events} == {1}


def test_silent_stages_send_heartbeats() -> None:
    events = worker_events([(0, START), (2500, END), (5000, DoneEvent())], attempt=2)
    assert [(ms, e["type"], e.get("elapsed_ms")) for ms, e in events] == [
        (0, "stage_start", None),
        (1000, "heartbeat", 1000),
        (2000, "heartbeat", 2000),
        (2500, "stage_end", None),
        (5000, "done", None),  # no stage runs between them: no heartbeat
    ]


def test_the_stream_starts_in_the_queue_and_ends_finalized() -> None:
    attempt = worker_events([(1200, START), (1500, END), (1500, DoneEvent())], attempt=1)
    events = timeline([attempt], Verdict(status="accepted"))
    assert [e["type"] for _, e in events] == [
        "queue",
        "queue",
        "stage_start",
        "stage_end",
        "done",
        "finalized",
    ]
    assert events[-1] == (
        1620,
        {
            "type": "finalized",
            "status": "accepted",
            "verdict_detail": {
                "first_failure": None,
                "limit": None,
                "warnings": [],
                "error_codes": [],
            },
        },
    )


def test_stream_ids_number_the_events_of_one_millisecond() -> None:
    events = [(0, {"type": "a"}), (5, {"type": "b"}), (5, {"type": "c"}), (7, {"type": "d"})]
    assert [e["id"] for e in stream_ids(1000, events)] == ["1000-0", "1005-0", "1005-1", "1007-0"]
