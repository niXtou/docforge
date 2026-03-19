"""widen extraction_jobs.status from VARCHAR(20) to VARCHAR(50)

"completed_with_errors" is 21 chars — one over the previous limit.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "extraction_jobs",
        "status",
        existing_type=sa.String(20),
        type_=sa.String(50),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "extraction_jobs",
        "status",
        existing_type=sa.String(50),
        type_=sa.String(20),
        existing_nullable=False,
    )
