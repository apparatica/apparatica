"""Job tokens (specs/07 §5.3) and toolchain profiles (specs/09 §2)."""

import asyncio
import uuid
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from apparatica.admin.cli import main
from apparatica.core.db import Database
from apparatica.core.settings import Settings, get_settings
from apparatica.main import create_app
from apparatica.submissions.models import ToolchainProfile
from apparatica.submissions.tokens import InvalidJobTokenError, JobTokens
from conftest import CONFIG_DIR

KEY = b"k" * 32
VERSIONS_LOCK = Path(__file__).parents[2] / "toolchain" / "versions.lock"


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def test_job_tokens() -> None:
    clock = Clock()
    tokens = JobTokens(KEY, ttl_s=60, clock=clock)
    submission = uuid.uuid4()
    token = tokens.issue(submission)
    assert token.startswith("v1.")
    claims = tokens.verify(token, submission)
    assert (claims.submission_id, claims.attempt_max, claims.exp) == (submission, 2, 1_000_060)

    with pytest.raises(InvalidJobTokenError, match="another submission"):
        tokens.verify(token, uuid.uuid4())
    with pytest.raises(InvalidJobTokenError, match="bad signature"):
        JobTokens(b"o" * 32, ttl_s=60, clock=clock).verify(token, submission)
    version, payload, mac = token.split(".")
    forged = tokens.issue(uuid.uuid4()).split(".")[1]
    with pytest.raises(InvalidJobTokenError, match="bad signature"):
        tokens.verify(f"{version}.{forged}.{mac}", submission)
    with pytest.raises(InvalidJobTokenError, match="version"):
        tokens.verify(f"v2.{payload}.{mac}", submission)
    with pytest.raises(InvalidJobTokenError, match="malformed"):
        tokens.verify("v1.x", submission)
    clock.now += 60
    with pytest.raises(InvalidJobTokenError, match="expired"):
        tokens.verify(token, submission)
    with pytest.raises(ValueError, match="32 bytes"):
        JobTokens(b"short", ttl_s=60)


def test_production_needs_a_job_token_key_and_a_queue() -> None:
    settings = Settings(environment="production", config_dir=CONFIG_DIR)
    with pytest.raises(RuntimeError, match="APX_JOB_TOKEN_KEY"):
        create_app(settings)
    keyed = settings.model_copy(update={"job_token_key": SecretStr("s" * 32)})
    with pytest.raises(RuntimeError, match="APX_QUEUE_URL"):
        create_app(keyed)
    keyed = keyed.model_copy(update={"queue_url": "redis://valkey-queue:6379/0"})
    tokens = create_app(keyed).state.job_tokens
    submission = uuid.uuid4()
    other = JobTokens(b"s" * 32, ttl_s=60)  # the ingestor with the same key
    assert other.verify(tokens.issue(submission), submission).submission_id == submission


def profiles(url: str) -> list[tuple[str, bool, dict[str, str]]]:
    async def run() -> list[tuple[str, bool, dict[str, str]]]:
        database = Database(url)
        try:
            async with database.sessions() as session:
                rows = await session.execute(
                    select(
                        ToolchainProfile.id, ToolchainProfile.is_default, ToolchainProfile.tools
                    ).order_by(ToolchainProfile.id)
                )
                return [(id, default, tools) for id, default, tools in rows]
        finally:
            await database.dispose()

    return asyncio.run(run())


def add(profile: str, *extra: str, digest: str = "sha256:" + "a" * 64) -> int:
    return main(
        [
            "toolchain",
            "add",
            profile,
            "--image",
            "ghcr.io/apparatica/toolchain",
            "--digest",
            digest,
            "--versions",
            str(VERSIONS_LOCK),
            "--normalization-version",
            "1",
            *extra,
        ]
    )


def test_toolchain_profiles(
    database_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APX_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        assert add("sv-2026.10.1") == 0
        assert add("sv-2026.10.2", "--default") == 0
        assert (
            capsys.readouterr().out == "created   sv-2026.10.1\ncreated   sv-2026.10.2, default\n"
        )
        [(_, old_default, tools), (_, new_default, _)] = profiles(database_url)
        assert (old_default, new_default) == (False, True)
        assert tools["verilator"] == "5.052"
        assert tools["pyslang"] == "12.0.0"
        assert "verilator_sha256" not in tools

        # Switching the default; a profile is immutable.
        assert add("sv-2026.10.1", "--default") == 0
        assert capsys.readouterr().out == "unchanged sv-2026.10.1, default\n"
        assert [default for _, default, _ in profiles(database_url)] == [True, False]
        assert add("sv-2026.10.1", digest="sha256:" + "b" * 64) == 1
        assert "is immutable" in capsys.readouterr().out
        assert add("sv-2026.10.3", digest="b" * 64) == 1
        assert "sha256:<hex>" in capsys.readouterr().out
    finally:
        get_settings.cache_clear()
