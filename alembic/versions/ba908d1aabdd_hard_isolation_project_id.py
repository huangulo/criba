"""hard isolation project_id

Revision ID: ba908d1aabdd
Revises: a1b2c3d4e5f6
Create Date: 2026-05-29 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ba908d1aabdd"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT id FROM projects ORDER BY created_at ASC LIMIT 1")
    ).fetchone()

    if result is not None:
        fallback_id = str(result[0])
    else:
        conn.execute(
            sa.text(
                "INSERT INTO projects (id, name, description) "
                "VALUES (gen_random_uuid(), 'Default', 'Auto-created during isolation migration') "
                "RETURNING id"
            )
        )
        fallback_id = str(
            conn.execute(
                sa.text(
                    "SELECT id FROM projects ORDER BY created_at ASC LIMIT 1"
                )
            ).fetchone()[0]
        )

    op.add_column("posts", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.execute(sa.text(f"UPDATE posts SET project_id = '{fallback_id}' WHERE project_id IS NULL"))

    op.alter_column("posts", "project_id", nullable=False)

    op.create_foreign_key(
        "fk_posts_project_id",
        source_table="posts",
        referent_table="projects",
        local_cols=["project_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # constraint name is dynamic — discover it before dropping
    constraint_row = conn.execute(
        sa.text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'posts'::regclass AND contype = 'u'"
        )
    ).fetchone()

    if constraint_row is not None:
        op.drop_constraint(constraint_row[0], "posts", type_="unique")

    op.create_unique_constraint("uq_posts_source_source_id_project", "posts", ["source", "source_id", "project_id"])

    op.create_index("ix_posts_project_id", "posts", ["project_id"])

    op.add_column("narratives", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.execute(sa.text(f"UPDATE narratives SET project_id = '{fallback_id}' WHERE project_id IS NULL"))

    op.alter_column("narratives", "project_id", nullable=False)

    op.create_foreign_key(
        "fk_narratives_project_id",
        source_table="narratives",
        referent_table="projects",
        local_cols=["project_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    op.create_index("ix_narratives_project_id", "narratives", ["project_id"])

    op.add_column("campaigns", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.execute(sa.text(f"UPDATE campaigns SET project_id = '{fallback_id}' WHERE project_id IS NULL"))

    op.alter_column("campaigns", "project_id", nullable=False)

    op.create_foreign_key(
        "fk_campaigns_project_id",
        source_table="campaigns",
        referent_table="projects",
        local_cols=["project_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    op.create_index("ix_campaigns_project_id", "campaigns", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_campaigns_project_id", table_name="campaigns")
    op.drop_constraint("fk_campaigns_project_id", "campaigns", type_="foreignkey")
    op.drop_column("campaigns", "project_id")

    op.drop_index("ix_narratives_project_id", table_name="narratives")
    op.drop_constraint("fk_narratives_project_id", "narratives", type_="foreignkey")
    op.drop_column("narratives", "project_id")

    op.drop_index("ix_posts_project_id", table_name="posts")
    op.drop_constraint("uq_posts_source_source_id_project", "posts", type_="unique")
    op.drop_constraint("fk_posts_project_id", "posts", type_="foreignkey")
    op.drop_column("posts", "project_id")

    # Restore original unique constraint on (source, source_id)
    op.create_unique_constraint("uq_posts_source_source_id", "posts", ["source", "source_id"])
