"""persist media urls on posts

Revision ID: b8a4f2d6c3e1
Revises: d4b2c7a9e1f5
Create Date: 2026-09-23 19:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8a4f2d6c3e1"
down_revision: str | None = "d4b2c7a9e1f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plugins already extract media URLs (photos, documents, image embeds)
    # but the column was missing, so the worker silently dropped them.
    # Matches the style of the existing array columns (hashtags, mentions).
    op.add_column("posts", sa.Column("media_urls", postgresql.ARRAY(sa.Text), server_default="{}"))


def downgrade() -> None:
    op.drop_column("posts", "media_urls")
