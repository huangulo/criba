"""scope author graph edges by project and source

Revision ID: d4b2c7a9e1f5
Revises: c9d4e8a1f7b2
Create Date: 2026-09-23 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4b2c7a9e1f5"
down_revision: str | None = "c9d4e8a1f7b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fallback_project_id(conn) -> str:
    """Id of the oldest project, creating a default one if the table is empty.

    Edges written before scoping cannot be attributed reliably; assigning them
    to the oldest project keeps them reachable instead of dropping them.
    """
    row = conn.execute(
        sa.text("SELECT id FROM projects ORDER BY created_at ASC LIMIT 1")
    ).fetchone()
    if row is not None:
        return str(row[0])

    conn.execute(
        sa.text(
            "INSERT INTO projects (id, name, description) "
            "VALUES (gen_random_uuid(), 'Default', "
            "'Auto-created during author graph scoping migration')"
        )
    )
    return str(
        conn.execute(
            sa.text("SELECT id FROM projects ORDER BY created_at ASC LIMIT 1")
        ).fetchone()[0]
    )


def upgrade() -> None:
    conn = op.get_bind()

    op.add_column("author_graph", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("author_graph", sa.Column("source", sa.String(50), nullable=True))

    # Only existing edges need a fallback project; a fresh install must not
    # gain a spurious "Default" project just from running migrations.
    has_rows = conn.execute(sa.text("SELECT 1 FROM author_graph LIMIT 1")).fetchone()
    if has_rows is not None:
        fallback_id = _fallback_project_id(conn)
        conn.execute(
            sa.text("UPDATE author_graph SET project_id = :pid WHERE project_id IS NULL"),
            {"pid": fallback_id},
        )
        conn.execute(sa.text("UPDATE author_graph SET source = 'unknown' WHERE source IS NULL"))

    op.alter_column("author_graph", "project_id", nullable=False)
    op.alter_column("author_graph", "source", nullable=False)

    op.create_foreign_key(
        "fk_author_graph_project_id",
        "author_graph",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Replace the primary key so identical author IDs from different projects
    # or platforms no longer merge into one edge.
    op.drop_constraint("author_graph_pkey", "author_graph", type_="primary")
    op.create_primary_key(
        "author_graph_pkey",
        "author_graph",
        ["project_id", "source", "source_author", "target_author", "interaction"],
    )


def downgrade() -> None:
    conn = op.get_bind()

    # The unscoped primary key cannot hold the same author pair twice, so keep
    # only the highest-weight copy of edges that now exist per project/source.
    conn.execute(
        sa.text(
            "DELETE FROM author_graph a WHERE EXISTS ("
            "  SELECT 1 FROM author_graph b"
            "  WHERE b.source_author = a.source_author"
            "    AND b.target_author = a.target_author"
            "    AND b.interaction = a.interaction"
            "    AND (b.weight > a.weight OR (b.weight = a.weight AND b.ctid > a.ctid))"
            ")"
        )
    )

    op.drop_constraint("author_graph_pkey", "author_graph", type_="primary")
    op.create_primary_key(
        "author_graph_pkey",
        "author_graph",
        ["source_author", "target_author", "interaction"],
    )
    op.drop_constraint("fk_author_graph_project_id", "author_graph", type_="foreignkey")
    op.drop_column("author_graph", "source")
    op.drop_column("author_graph", "project_id")
