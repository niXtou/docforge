"""add validation_errors and field_evidence to extraction_jobs

Persists the final validation error list and the per-field provenance map
(evidence quotes) so GET /api/extract/{id}/result can return them after the
workflow finishes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("extraction_jobs", sa.Column("validation_errors", sa.JSON(), nullable=True))
    op.add_column("extraction_jobs", sa.Column("field_evidence", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("extraction_jobs", "field_evidence")
    op.drop_column("extraction_jobs", "validation_errors")
