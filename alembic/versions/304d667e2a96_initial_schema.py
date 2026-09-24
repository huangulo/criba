"""initial schema

Revision ID: 304d667e2a96
Revises:
Create Date: 2026-05-10 22:20:38.516704

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "304d667e2a96"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("author_id", sa.String(255), nullable=False),
        sa.Column("author_handle", sa.String(255)),
        sa.Column("author_created", sa.TIMESTAMP(timezone=True)),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("language", sa.String(10)),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("url", sa.Text),
        sa.Column("engagement", postgresql.JSONB, server_default="{}"),
        sa.Column("hashtags", postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("mentions", postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("reply_to", sa.String(255)),
        sa.Column("raw_metadata", postgresql.JSONB, server_default="{}"),
        sa.Column(
            "ingested_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("source", "source_id"),
    )

    op.create_table(
        "heuristic_scores",
        sa.Column(
            "post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("posts.id"),
            primary_key=True,
        ),
        sa.Column("copypasta_score", sa.Float, server_default="0"),
        sa.Column("temporal_anomaly", sa.Float, server_default="0"),
        sa.Column("account_age_flag", sa.Float, server_default="0"),
        sa.Column("composite_score", sa.Float, server_default="0"),
        sa.Column("sent_to_llm", sa.Boolean, server_default=sa.text("false")),
        sa.Column(
            "scored_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "llm_analysis",
        sa.Column(
            "post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("posts.id"),
            primary_key=True,
        ),
        sa.Column("coordination_probability", sa.Float),
        sa.Column("reasoning", sa.Text),
        sa.Column("narrative_category", sa.String(50)),
        sa.Column("talking_points", postgresql.ARRAY(sa.Text)),
        sa.Column("recommended_action", sa.String(50)),
        sa.Column("model_used", sa.String(100)),
        sa.Column(
            "analyzed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "narratives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("label", sa.String(255)),
        sa.Column("first_seen", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_seen", sa.TIMESTAMP(timezone=True)),
        sa.Column("post_count", sa.Integer, server_default="0"),
        sa.Column("platform_spread", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(50), server_default="active"),
        sa.Column("embedding", sa.Text, nullable=True),
    )

    op.create_table(
        "narrative_posts",
        sa.Column(
            "narrative_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("narratives.id"),
            primary_key=True,
        ),
        sa.Column(
            "post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("posts.id"),
            primary_key=True,
        ),
    )

    op.create_table(
        "author_graph",
        sa.Column("source_author", sa.String(255), primary_key=True),
        sa.Column("target_author", sa.String(255), primary_key=True),
        sa.Column("interaction", sa.String(50), primary_key=True),
        sa.Column("weight", sa.Integer, server_default="1"),
        sa.Column(
            "last_seen",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("label", sa.String(255)),
        sa.Column("description", sa.Text),
        sa.Column(
            "detected_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("confidence", sa.Float),
        sa.Column("account_count", sa.Integer),
        sa.Column("post_count", sa.Integer),
        sa.Column("platforms", postgresql.ARRAY(sa.Text)),
        sa.Column("status", sa.String(50), server_default="active"),
    )


def downgrade() -> None:
    op.drop_table("campaigns")
    op.drop_table("author_graph")
    op.drop_table("narrative_posts")
    op.drop_table("narratives")
    op.drop_table("llm_analysis")
    op.drop_table("heuristic_scores")
    op.drop_table("posts")
