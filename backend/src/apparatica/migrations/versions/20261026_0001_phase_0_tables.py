"""Phase 0 tables: problems, versions, tags, reference solutions, toolchain profiles,
submissions, stage results, artifacts, feature flags (specs/04 §4).

Revision ID: 0001
Revises:
Create Date: 2026-10-26 00:19:19.534513
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "rules",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_feature_flags")),
    )
    op.create_table(
        "problems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("is_published", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("number > 0", name=op.f("ck_problems_number_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_problems")),
        sa.UniqueConstraint("number", name=op.f("uq_problems_number")),
        sa.UniqueConstraint("slug", name=op.f("uq_problems_slug")),
    )
    op.create_table(
        "tags",
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("sort", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("slug", name=op.f("pk_tags")),
    )
    op.create_table(
        "toolchain_profiles",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("image", sa.Text(), nullable=False),
        sa.Column("image_digest", sa.Text(), nullable=False),
        sa.Column("tools", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("liberty", sa.Text(), nullable=True),
        sa.Column("normalization_version", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_toolchain_profiles")),
    )
    op.create_index(
        "uq_toolchain_profiles_language_default",
        "toolchain_profiles",
        ["language"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_table(
        "problem_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("statement_md", sa.Text(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("interface", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("package_uri", sa.Text(), nullable=False),
        sa.Column("resource_class", sa.Text(), nullable=False),
        sa.Column("leaderboard_epoch", sa.Integer(), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_problem_versions_content_hash_sha256")
        ),
        sa.CheckConstraint(
            "leaderboard_epoch > 0", name=op.f("ck_problem_versions_leaderboard_epoch_positive")
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_problem_versions_version_positive")),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["problems.id"], name=op.f("fk_problem_versions_problem_id_problems")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_problem_versions")),
        sa.UniqueConstraint("problem_id", "id", name=op.f("uq_problem_versions_problem_id_id")),
        sa.UniqueConstraint(
            "problem_id", "version", name=op.f("uq_problem_versions_problem_id_version")
        ),
    )
    op.create_index(
        "ix_problem_versions_tags",
        "problem_versions",
        ["tags"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_table(
        "reference_solutions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("problem_version_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("explanation_md", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["problem_version_id"],
            ["problem_versions.id"],
            name=op.f("fk_reference_solutions_problem_version_id_problem_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reference_solutions")),
    )
    op.create_index(
        op.f("ix_reference_solutions_problem_version_id"),
        "reference_solutions",
        ["problem_version_id"],
        unique=False,
    )
    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("problem_version_id", sa.Uuid(), nullable=False),
        sa.Column("guest_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=True),
        sa.Column("ast_hash", sa.Text(), nullable=True),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("toolchain_profile_id", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "accepted",
                "accepted_with_warnings",
                "wrong_answer",
                "compile_error",
                "limit_exceeded",
                "forbidden_construct",
                "cancelled",
                "internal_error",
                name="submission_status",
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("verdict_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("queue_class", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_ip_hash", sa.Text(), nullable=True),
        sa.CheckConstraint("kind IN ('run', 'submit')", name=op.f("ck_submissions_kind")),
        sa.CheckConstraint("attempt > 0", name=op.f("ck_submissions_attempt_positive")),
        sa.CheckConstraint("seed >= 0", name=op.f("ck_submissions_seed_non_negative")),
        sa.ForeignKeyConstraint(
            ["problem_version_id"],
            ["problem_versions.id"],
            name=op.f("fk_submissions_problem_version_id_problem_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["toolchain_profile_id"],
            ["toolchain_profiles.id"],
            name=op.f("fk_submissions_toolchain_profile_id_toolchain_profiles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
    )
    op.create_index("ix_submissions_ast_hash", "submissions", ["ast_hash"], unique=False)
    op.create_index(
        "ix_submissions_guest_id_created_at",
        "submissions",
        ["guest_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_submissions_problem_version_id_status",
        "submissions",
        ["problem_version_id", "status"],
        unique=False,
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("stage_key", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_artifacts_size_bytes_non_negative")),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_artifacts_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifacts")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_artifacts_storage_key")),
    )
    op.create_index(
        op.f("ix_artifacts_submission_id"), "artifacts", ["submission_id"], unique=False
    )
    op.create_table(
        "stage_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("stage_key", sa.Text(), nullable=False),
        sa.Column("stage_type", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "passed",
                "warning",
                "failed",
                "skipped",
                "cancelled",
                "error",
                name="stage_status",
            ),
            nullable=False,
        ),
        sa.Column("failure_kind", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metrics_schema", sa.Text(), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(status = 'failed') = (failure_kind IS NOT NULL)",
            name=op.f("ck_stage_results_failure_kind_iff_failed"),
        ),
        sa.CheckConstraint(
            "failure_kind IN ('forbidden', 'compile', 'wrong', 'limit')",
            name=op.f("ck_stage_results_failure_kind"),
        ),
        sa.CheckConstraint(
            "duration_ms >= 0", name=op.f("ck_stage_results_duration_ms_non_negative")
        ),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_stage_results_ordinal_non_negative")),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_stage_results_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stage_results")),
        sa.UniqueConstraint(
            "submission_id", "stage_key", name=op.f("uq_stage_results_submission_id_stage_key")
        ),
    )
    # problems and problem_versions refer to each other: the current version is added last.
    op.create_foreign_key(
        "fk_problems_current_version",
        "problems",
        "problem_versions",
        ["id", "current_version_id"],
        ["problem_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_problems_current_version", "problems", type_="foreignkey")
    op.drop_table("stage_results")
    op.drop_index(op.f("ix_artifacts_submission_id"), table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_submissions_problem_version_id_status", table_name="submissions")
    op.drop_index("ix_submissions_guest_id_created_at", table_name="submissions")
    op.drop_index("ix_submissions_ast_hash", table_name="submissions")
    op.drop_table("submissions")
    op.drop_index(
        op.f("ix_reference_solutions_problem_version_id"), table_name="reference_solutions"
    )
    op.drop_table("reference_solutions")
    op.drop_index("ix_problem_versions_tags", table_name="problem_versions", postgresql_using="gin")
    op.drop_table("problem_versions")
    op.drop_index(
        "uq_toolchain_profiles_language_default",
        table_name="toolchain_profiles",
        postgresql_where=sa.text("is_default"),
    )
    op.drop_table("toolchain_profiles")
    op.drop_table("tags")
    op.drop_table("problems")
    op.drop_table("feature_flags")
    sa.Enum(name="stage_status").drop(op.get_bind())
    sa.Enum(name="submission_status").drop(op.get_bind())
