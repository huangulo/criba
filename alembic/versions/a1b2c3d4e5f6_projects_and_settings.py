"""projects and system settings tables

Revision ID: a1b2c3d4e5f6
Revises: ddd11b49ff81
Create Date: 2026-05-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "ddd11b49ff81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "project_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
    )

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("value", sa.Text, server_default="", nullable=False),
    )

    # Seed default system settings
    op.execute("""
        INSERT INTO system_settings (key, value) VALUES
            ('heuristic_threshold', '0.6'),
            ('copypasta_threshold', '10'),
            ('temporal_cluster_min', '5'),
            ('new_account_days', '7'),
            ('confidence_threshold', '0.85'),
            ('slack_webhook_url', ''),
            ('discord_webhook_url', ''),
            ('telegram_bot_token', ''),
            ('telegram_chat_id', '')
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_table("project_targets")
    op.drop_table("projects")