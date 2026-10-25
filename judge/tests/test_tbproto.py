import json
from pathlib import Path
from typing import Any

import pytest

# Module import: pytest would try to collect the imported TestCase, TestStart... classes.
from judge.languages.systemverilog import tbproto

SCHEMA_FILE = Path(__file__).parents[1] / "schemas" / "tb-result.schema.json"
LIMIT = 1 << 20


def rec(event: str, **fields: Any) -> dict[str, Any]:
    return {"v": 1, "event": event, **fields}


def start(groups: list[str] | None = None) -> dict[str, Any]:
    return rec("suite_start", seed=41917, groups=groups)


def started(test_id: str, cycle: int = 0, group: str = "public") -> dict[str, Any]:
    return rec("test_start", id=test_id, name=f"тест {test_id}", group=group, cycle=cycle)


def ended(test_id: str, status: str, begin: int, end: int) -> dict[str, Any]:
    return rec("test_end", id=test_id, status=status, cycles=end - begin, cycle=end)


def mismatch(test_id: str, cycle: int, **fields: Any) -> dict[str, Any]:
    values = {"signal": "rdata", "expected": "8'h3a", "actual": "8'h00"} | fields
    return rec("mismatch", test=test_id, cycle=cycle, time_ps=cycle * 10_000, **values)


def skip(test_id: str) -> dict[str, Any]:
    return rec("test_skip", id=test_id, name=f"тест {test_id}", group="public")


def end(passed: int, failed: int = 0, not_run: int = 0, cycles: int = 100) -> dict[str, Any]:
    return rec("suite_end", passed=passed, failed=failed, not_run=not_run, cycles=cycles)


def jsonl(*records: dict[str, Any]) -> bytes:
    return b"".join(json.dumps(r, ensure_ascii=False).encode() + b"\n" for r in records)


PASSING = [start(["public"]), started("t1"), ended("t1", "passed", 0, 40), end(1, cycles=40)]
FAILING = [
    start(["public", "hidden"]),
    started("t1"),
    ended("t1", "passed", 0, 40),
    started("t2", 40),
    mismatch("t2", 143),
    mismatch("t2", 143, signal="full", expected="1'h1", actual="1'h0", hint="Смотрите full"),
    ended("t2", "failed", 40, 200),
    skip("t3"),
    end(1, 1, 1, 200),
]


def test_passing_run() -> None:
    result = tbproto.parse_result(jsonl(*PASSING), max_bytes=LIMIT)
    assert result.start is not None
    assert result.start.seed == 41917
    assert result.start.groups == ["public"]
    assert [(t.id, t.status, t.start_cycle, t.end_cycle) for t in result.tests] == [
        ("t1", "passed", 0, 40)
    ]
    assert result.end == tbproto.SuiteEnd(
        v=1, event="suite_end", passed=1, failed=0, not_run=0, cycles=40
    )
    assert result.abort is None
    assert not result.truncated
    assert result.first_mismatch is None


def test_failing_run_skips_the_rest() -> None:
    result = tbproto.parse_result(jsonl(*FAILING), max_bytes=LIMIT)
    assert [(t.id, t.status) for t in result.tests] == [
        ("t1", "passed"),
        ("t2", "failed"),
        ("t3", "not_run"),
    ]
    failed = result.tests[1]
    assert [(m.signal, m.expected, m.actual, m.hint) for m in failed.mismatches] == [
        ("rdata", "8'h3a", "8'h00", None),
        ("full", "1'h1", "1'h0", "Смотрите full"),
    ]
    assert result.first_mismatch == failed.mismatches[0]
    assert result.tests[2].name == "тест t3"


def test_all_groups_and_wide_values() -> None:
    wide = "100'h000000000000000000000000a"
    records = [
        start(None),
        started("h1", group="hidden"),
        mismatch("h1", 5, expected=wide, actual="100'h0000000000000000000000000"),
        ended("h1", "failed", 0, 5),
        end(0, 1, cycles=5),
    ]
    result = tbproto.parse_result(jsonl(*records), max_bytes=LIMIT)
    assert result.start is not None
    assert result.start.groups is None
    assert result.tests[0].mismatches[0].expected == wide


def test_long_hint_is_truncated() -> None:
    records = [*FAILING]
    records[5] = mismatch("t2", 143, hint="я" * 600)
    hint = tbproto.parse_result(jsonl(*records), max_bytes=LIMIT).tests[1].mismatches[1].hint
    assert hint is not None
    assert len(hint) == tbproto.HINT_MAX_LENGTH
    assert hint.endswith("…")


def test_empty_file_is_an_unfinished_run() -> None:
    result = tbproto.parse_result(b"", max_bytes=LIMIT)
    assert result == tbproto.TbResult(None, (), None, None, truncated=False)


def test_cut_off_last_line_is_ignored() -> None:
    data = jsonl(start(), started("t1")) + b'{"v":1,"event":"mism'
    result = tbproto.parse_result(data, max_bytes=LIMIT)
    assert result.truncated
    assert [(t.id, t.status, t.end_cycle) for t in result.tests] == [("t1", "running", None)]
    assert result.end is None


def test_cycle_limit_inside_a_test() -> None:
    abort = rec("suite_abort", reason="max_cycles", cycle=200_001)
    result = tbproto.parse_result(jsonl(start(), started("t1"), abort), max_bytes=LIMIT)
    assert result.abort is not None
    assert result.abort.reason == "max_cycles"
    assert result.tests[0].status == "running"
    assert result.end is None


def test_testbench_error() -> None:
    abort = rec("suite_abort", reason="tb_error", cycle=0, message="duplicate test id t1")
    result = tbproto.parse_result(jsonl(start(), abort), max_bytes=LIMIT)
    assert result.abort is not None
    assert result.abort.message == "duplicate test id t1"


def test_size_limit() -> None:
    data = jsonl(*PASSING)
    assert tbproto.parse_result(data, max_bytes=len(data)).end is not None
    with pytest.raises(tbproto.ProtocolError, match="exceeds"):
        tbproto.parse_result(data, max_bytes=len(data) - 1)


def replace(records: list[dict[str, Any]], index: int, **fields: Any) -> list[dict[str, Any]]:
    changed = [*records]
    changed[index] = records[index] | fields
    return changed


def raw(records: list[dict[str, Any]], line: bytes, index: int) -> bytes:
    lines = jsonl(*records).splitlines(keepends=True)
    lines.insert(index, line)
    return b"".join(lines)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (raw(PASSING, b"not json\n", 1), "line 2: Invalid JSON"),
        (raw(PASSING, b"\n", 1), "line 2: Invalid JSON"),
        (raw(PASSING, b'{"v":1,"event":"test_start","name":"\xff"}\n', 1), "line 2"),
        (jsonl(*replace(PASSING, 0, v=2)), "line 1: suite_start.v: Input should be 1"),
        (jsonl(*replace(PASSING, 0, seed=2**64)), "suite_start.seed"),
        (jsonl(*replace(PASSING, 0, extra=1)), "suite_start.extra: Extra inputs"),
        (jsonl(*replace(PASSING, 1, event="test_begin")), "line 2: Input tag 'test_begin'"),
        (jsonl(*replace(PASSING, 1, cycle="0")), "test_start.cycle: Input should be"),
        (jsonl(*replace(FAILING, 4, expected="8'H3A")), "mismatch.expected: String should"),
        (jsonl(*replace(FAILING, 4, actual="0'h0")), "mismatch.actual"),
        (jsonl(*replace(FAILING, 4, actual="8'bx")), "mismatch.actual"),
        (jsonl(*PASSING[1:]), "line 1: test_start before suite_start"),
        (jsonl(start(), *PASSING), "line 2: second suite_start"),
        (jsonl(start(), mismatch("t1", 1)), "line 2: mismatch of t1 outside that test"),
        (jsonl(*replace(FAILING, 4, test="t1")), "line 5: mismatch of t1 outside that test"),
        (jsonl(*replace(FAILING, 4, cycle=10)), "mismatch before the start"),
        (jsonl(start(), started("t1"), started("t2")), "test_start t2 inside test t1"),
        (jsonl(*replace(PASSING, 2, id="t2")), "test_end of t2 outside that test"),
        (jsonl(*replace(PASSING, 2, cycles=39)), "test_end cycles of t1 do not match"),
        (jsonl(*replace(PASSING, 2, status="failed")), "status does not match its mismatches"),
        (jsonl(*replace(FAILING, 6, status="passed")), "status does not match its mismatches"),
        (jsonl(*PASSING[:3], started("t1", 40)), "duplicate test id t1"),
        (jsonl(*PASSING[:3], skip("t2")), "test_skip t2 contradicts the failed tests"),
        (jsonl(*FAILING[:7], started("t3", 200)), "test_start t3 contradicts"),
        (jsonl(*PASSING[:1], started("h1", group="hidden")), "group that was not selected"),
        (jsonl(*replace(PASSING, 3, passed=2)), "suite_end counts do not match"),
        (jsonl(*FAILING[:8], end(1, 1, 0, 200)), "suite_end counts do not match"),
        (jsonl(start(), started("t1"), end(0)), "suite_end inside test t1"),
        (jsonl(*PASSING, started("t2")), "line 5: test_start after the end of the suite"),
        (jsonl(*PASSING) + b'{"v":1', "line 5: data after the end of the suite"),
    ],
)
def test_protocol_violations(data: bytes, message: str) -> None:
    with pytest.raises(tbproto.ProtocolError, match=message) as error:
        tbproto.parse_result(data, max_bytes=LIMIT)
    assert error.value.line is None or str(error.value).startswith(f"line {error.value.line}:")


NONCE = "0f3c9a"
MARK = f"@@apx:{NONCE} "
SKIP = '{"v":1,"event":"test_skip","id":"t3","name":"","group":"g"}'
ABORT = '{"v":1,"event":"suite_abort","reason":"max_cycles","cycle":9}'
START = json.dumps(start())


@pytest.mark.parametrize(
    ("line", "text", "event"),
    [
        (MARK + SKIP, "", "test_skip"),
        (MARK + ABORT + "\r\n", "", "suite_abort"),
        ("count=3" + MARK + START, "count=3", "suite_start"),
        ("@@apx:ffffff " + START, "@@apx:ffffff " + START, None),
        (MARK.rstrip() + START, MARK.rstrip() + START, None),
        (MARK + "not json", "", None),
        (MARK + json.dumps(mismatch("t1", 3)), "", None),
        ("plain output", "plain output", None),
    ],
)
def test_split_progress(line: str, text: str, event: str | None) -> None:
    got_text, record = tbproto.split_progress(line, NONCE)
    assert got_text == text
    assert (record.event if record else None) == event


def test_split_progress_without_nonce_is_plain_text() -> None:
    line = "@@apx: " + json.dumps(start())
    assert tbproto.split_progress(line, "") == (line, None)


def test_new_nonce() -> None:
    nonce = tbproto.new_nonce()
    assert len(nonce) == 32
    assert int(nonce, 16) >= 0
    assert nonce != tbproto.new_nonce()


def test_committed_json_schema_is_up_to_date() -> None:
    assert SCHEMA_FILE.read_text(encoding="utf-8") == tbproto.tb_result_json_schema(), (
        "judge/schemas/tb-result.schema.json is stale: run `just schemas`"
    )
