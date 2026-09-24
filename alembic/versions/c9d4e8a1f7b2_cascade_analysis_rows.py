"""cascade analysis rows on post delete

Revision ID: c9d4e8a1f7b2
Revises: 2669cdb38ea0
Create Date: 2026-09-23 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d4e8a1f7b2"
down_revision: str | None = "2669cdb38ea0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, column, referenced_table) for foreign keys that must cascade so
# deleting a project (and its posts) cannot fail on dependent analysis rows.
CASCADE_FKS = [
    ("heuristic_scores", "post_id", "posts"),
    ("llm_analysis", "post_id", "posts"),
    ("post_embeddings", "post_id", "posts"),
    ("narrative_posts", "post_id", "posts"),
    ("narrative_posts", "narrative_id", "narratives"),
]


def _fk_name(conn, table: str, column: str) -> str | None:
    row = conn.execute(
        sa.text(
            "SELECT tc.constraint_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            " AND tc.table_name = kcu.table_name "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "AND tc.table_name = :table AND kcu.column_name = :column "
            "LIMIT 1"
        ),
        {"table": table, "column": column},
    ).fetchone()
    return row[0] if row else None


def upgrade() -> None:
    conn = op.get_bind()
    for table, column, ref_table in CASCADE_FKS:
        existing = _fk_name(conn, table, column)
        if existing is not None:
            op.drop_constraint(existing, table, type_="foreignkey")
        op.create_foreign_key(
            f"fk_{table}_{column}_cascade", table, ref_table, [column], ["id"], ondelete="CASCADE"
        )


def downgrade() -> None:
    conn = op.get_bind()
    for table, column, ref_table in reversed(CASCADE_FKS):
        existing = _fk_name(conn, table, column)
        if existing is not None:
            op.drop_constraint(existing, table, type_="foreignkey")
        op.create_foreign_key(f"fk_{table}_{column}", table, ref_table, [column], ["id"])
