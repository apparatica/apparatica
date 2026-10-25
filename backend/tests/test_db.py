"""The Phase 0 schema on a real Postgres (specs/04 §4): migrations, constraints, flag overrides."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import Connection, delete, func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

import apparatica.models  # noqa: F401 (fills Base.metadata)
from apparatica.cli import alembic_config
from apparatica.core.db import Base, Database
from apparatica.core.ids import uuid7
from apparatica.core.models import FeatureFlag
from apparatica.core.settings import Settings
from apparatica.main import create_app
from apparatica.problems.models import Problem, ProblemVersion
from apparatica.submissions.models import (
    STAGE_STATUSES,
    SUBMISSION_STATUSES,
    Artifact,
    StageResult,
    Submission,
    ToolchainProfile,
)


def with_session(url: str, scenario: Callable[[Database], Awaitable[None]]) -> None:
    async def run() -> None:
        database = Database(url)
        try:
            await scenario(database)
        finally:
            await database.dispose()

    asyncio.run(run())


async def scalars(database: Database, statement: str) -> list[Any]:
    async with database.engine.connect() as connection:
        return list((await connection.execute(text(statement))).scalars())


async def rejected(
    database: Database, *rows: Base, error: type[Exception] = IntegrityError
) -> None:
    with pytest.raises(error):
        async with database.sessions.begin() as session:
            session.add_all(rows)


# Ids are set here: the default (uuid7) is applied only on flush.
def problem(number: int) -> Problem:
    return Problem(id=uuid7(), slug=f"problem-{number}", number=number)


def version(problem: Problem, number: int = 1, **fields: Any) -> ProblemVersion:
    values: dict[str, Any] = {
        "id": uuid7(),
        "problem_id": problem.id,
        "version": number,
        "content_hash": "0" * 64,
        "language": "systemverilog",
        "kind": "design",
        "title": "Problem",
        "difficulty": "easy",
        "tags": ["combinational"],
        "statement_md": "",
        "template": "",
        "interface": {},
        "manifest": {},
        "package_uri": f"problems/{problem.slug}/{number}.tar.zst",
        "resource_class": "light",
        "leaderboard_epoch": 1,
    }
    return ProblemVersion(**(values | fields))


def profile(id: str = "sv-2026.10", **fields: Any) -> ToolchainProfile:
    values: dict[str, Any] = {
        "id": id,
        "language": "systemverilog",
        "image": "ghcr.io/apparatica/toolchain",
        "image_digest": "sha256:" + "0" * 64,
        "tools": {"verilator": "5.052"},
        "normalization_version": 1,
    }
    return ToolchainProfile(**(values | fields))


async def add(database: Database, *rows: Base) -> None:
    async with database.sessions.begin() as session:
        for row in rows:  # in order: the tables have no ORM relationships to sort by
            session.add(row)
            await session.flush()


def test_migrations_match_the_models(database_url: str) -> None:
    def differences(connection: Connection) -> list[Any]:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        return list(compare_metadata(context, Base.metadata))

    async def scenario(database: Database) -> None:
        async with database.engine.connect() as connection:
            assert await connection.run_sync(differences) == []

    with_session(database_url, scenario)


def test_migrations_downgrade_to_an_empty_database(database_url: str) -> None:
    config = alembic_config(database_url)
    command.downgrade(config, "base")

    async def empty(database: Database) -> None:
        tables = await scalars(
            database, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        assert tables == ["alembic_version"]
        assert await scalars(database, "SELECT typname FROM pg_type WHERE typtype = 'e'") == []

    with_session(database_url, empty)
    command.upgrade(config, "head")


def test_status_types_list_the_statuses_of_the_code(database_url: str) -> None:
    # A new status in the judge needs a migration (ALTER TYPE ... ADD VALUE).
    async def scenario(database: Database) -> None:
        for name, values in (
            ("submission_status", SUBMISSION_STATUSES),
            ("stage_status", STAGE_STATUSES),
        ):
            labels = await scalars(
                database,
                "SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_type.oid = enumtypid"
                f" WHERE typname = '{name}' ORDER BY enumsortorder",
            )
            assert tuple(labels) == values

    with_session(database_url, scenario)


def test_problem_versions(database_url: str) -> None:
    async def scenario(database: Database) -> None:
        first, second = problem(1), problem(2)
        v1 = version(first)
        await add(database, first, second, v1)
        assert v1.id.version == 7

        async with database.sessions.begin() as session:
            (await session.get_one(Problem, first.id)).current_version_id = v1.id
        # The current version of a problem is one of its own versions.
        with pytest.raises(IntegrityError):
            async with database.sessions.begin() as session:
                (await session.get_one(Problem, second.id)).current_version_id = v1.id

        await rejected(database, version(first, 1))  # (problem_id, version) is unique
        await rejected(database, version(first, 2, content_hash="sha256:" + "0" * 64))
        await rejected(database, problem(1))  # the catalogue number is unique
        await rejected(database, Problem(slug="problem-1", number=3))

        async with database.sessions() as session:
            tagged = await session.scalars(
                select(ProblemVersion.id).where(ProblemVersion.tags.contains(["combinational"]))
            )
            assert tagged.all() == [v1.id]

    with_session(database_url, scenario)


def test_one_default_toolchain_profile_per_language(database_url: str) -> None:
    async def scenario(database: Database) -> None:
        await add(database, profile("sv-2026.10", is_default=True), profile("sv-2026.11"))
        await rejected(database, profile("sv-2027.01", is_default=True))
        await add(database, profile("vhdl-2026.10", language="vhdl", is_default=True))

    with_session(database_url, scenario)


def submission(problem_version: ProblemVersion, **fields: Any) -> Submission:
    values: dict[str, Any] = {
        "id": uuid7(),
        "problem_version_id": problem_version.id,
        "kind": "run",
        "code": "module m; endmodule\n",
        "seed": 2**63 - 1,
        "toolchain_profile_id": "sv-2026.10",
        "queue_class": "light",
    }
    return Submission(**(values | fields))


def stage(row: Submission, key: str, status: str, **fields: Any) -> StageResult:
    return StageResult(
        submission_id=row.id, stage_key=key, stage_type=key, ordinal=0, status=status, **fields
    )


def test_submissions_and_stage_results(database_url: str) -> None:
    async def scenario(database: Database) -> None:
        owner = problem(1)
        v1 = version(owner)
        row = submission(v1)
        await add(database, owner, v1, profile(), row)
        async with database.sessions() as session:
            stored = await session.get_one(Submission, row.id)
            assert (stored.status, stored.attempt, stored.verdict_detail) == ("queued", 1, None)

        await add(
            database,
            stage(row, "lint", "passed", metrics={"warnings": 0}, metrics_schema="lint/v1"),
            stage(row, "sim", "failed", failure_kind="wrong"),
            Artifact(
                submission_id=row.id,
                stage_key="sim",
                kind="log",
                storage_key=f"submissions/{row.id}/sim.log",
                size_bytes=10,
                sha256="0" * 64,
            ),
        )
        await rejected(database, stage(row, "lint", "passed"))  # stage keys are unique
        await rejected(database, stage(row, "synth", "failed"))  # a failure needs its kind
        await rejected(database, stage(row, "synth", "passed", failure_kind="wrong"))
        await rejected(database, stage(row, "synth", "failed", failure_kind="slow"))
        await rejected(database, stage(row, "synth", "unknown"), error=DBAPIError)
        await rejected(database, submission(v1, kind="practice"))
        await rejected(database, submission(v1, seed=-1))

        # Deleting a submission (guest retention, Ф1) deletes its results.
        async with database.sessions.begin() as session:
            await session.execute(delete(Submission).where(Submission.id == row.id))
        async with database.sessions() as session:
            for model in (StageResult, Artifact):
                assert await session.scalar(select(func.count()).select_from(model)) == 0

    with_session(database_url, scenario)


def test_feature_flags_come_from_the_table(database_url: str, settings: Settings) -> None:
    async def overrides(database: Database) -> None:
        await add(
            database,
            FeatureFlag(key="captcha", enabled=True),
            FeatureFlag(key="formal_stage", enabled=False),
            FeatureFlag(key="no_such_flag", enabled=True),
        )
        async with database.sessions() as session:
            flag = await session.get_one(FeatureFlag, "captcha")
            assert flag.rules == {}
            assert flag.updated_at.tzinfo is not None

    with_session(database_url, overrides)
    app = create_app(settings.model_copy(update={"database_url": database_url}))
    with TestClient(app) as client:
        features = client.get("/api/v1/config").json()["features"]
    assert features == {
        "captcha": True,
        "formal_stage": False,
        "industrial_mode": False,
        "reports": False,
    }
