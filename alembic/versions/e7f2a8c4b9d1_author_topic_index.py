"""index posts by project, author, publish time

Revision ID: e7f2a8c4b9d1
Revises: b8a4f2d6c3e1
Create Date: 2026-09-23 21:10:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f2a8c4b9d1"
down_revision: str | None = "b8a4f2d6c3e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The LLM analysis task reads each author's prior posts (topic-history
    # evidence) with WHERE project_id/author_id ORDER BY published_at; without
    # this index every lookup seq-scans the posts table.
    op.create_index(
        "ix_posts_project_author_published",
        "posts",
        ["project_id", "author_id", "published_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_posts_project_author_published", table_name="posts")
