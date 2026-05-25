"""post embeddings table

Revision ID: ddd11b49ff81
Revises: 304d667e2a96
Create Date: 2026-05-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None

# revision identifiers, used by Alembic.
revision: str = "ddd11b49ff81"
down_revision: Union[str, None] = "304d667e2a96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    if Vector is not None:
        op.create_table(
            "post_embeddings",
            sa.Column(
                "post_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("posts.id"),
                primary_key=True,
            ),
            sa.Column("embedding", Vector(768), nullable=False),
            sa.Column("model_used", sa.String(100), server_default="nomic-embed-text"),
            sa.Column(
                "embedded_at",
                sa.TIMESTAMP(timezone=True),
                server_default=sa.func.now(),
            ),
        )

        op.alter_column(
            "narratives",
            "embedding",
            existing_type=sa.Text,
            type_=Vector(768),
            existing_nullable=True,
            postgresql_using="embedding::vector(768)",
        )
    else:
        op.execute("""
            CREATE TABLE post_embeddings (
                post_id UUID NOT NULL PRIMARY KEY REFERENCES posts(id),
                embedding vector(768) NOT NULL,
                model_used VARCHAR(100) NOT NULL DEFAULT 'nomic-embed-text',
                embedded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)

        op.execute("ALTER TABLE narratives ALTER COLUMN embedding TYPE vector(768)")


def downgrade() -> None:
    op.drop_table("post_embeddings")

    op.execute("ALTER TABLE narratives ALTER COLUMN embedding TYPE TEXT")
