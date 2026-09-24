"""ground_truth_labels

Revision ID: 2669cdb38ea0
Revises: ba908d1aabdd
Create Date: 2026-05-31 14:00:23.717492

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2669cdb38ea0"
down_revision: str | None = "ba908d1aabdd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ground_truth",
        sa.Column(
            "post_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column(
            "labeled_by",
            sa.String(100),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "labeled_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            ondelete="CASCADE",
        ),
    )

    op.execute(
        sa.text(
            "ALTER TABLE ground_truth "
            "ADD CONSTRAINT ck_ground_truth_label "
            "CHECK (label IN ('organic','coordinated','uncertain'))"
        )
    )

    op.create_index("ix_ground_truth_label", "ground_truth", ["label"])


def downgrade() -> None:
    op.drop_index("ix_ground_truth_label", table_name="ground_truth")
    op.drop_constraint("ck_ground_truth_label", "ground_truth", type_="check")
    op.drop_table("ground_truth")
