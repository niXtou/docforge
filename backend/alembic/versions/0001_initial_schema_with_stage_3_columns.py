"""initial schema with stage 3 columns

Revision ID: 0001
Revises:
Create Date: 2026-03-18 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "extraction_schemas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("json_schema", sa.JSON(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "extraction_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("schema_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("model_used", sa.String(length=100), nullable=False),
        sa.Column("result_data", sa.JSON(), nullable=True),
        sa.Column("validation_passed", sa.Boolean(), nullable=True),
        sa.Column("retries_used", sa.Integer(), nullable=False),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("chunks_processed", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        # Stage 3 columns
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("api_key", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["schema_id"], ["extraction_schemas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("extraction_jobs")
    op.drop_table("extraction_schemas")
