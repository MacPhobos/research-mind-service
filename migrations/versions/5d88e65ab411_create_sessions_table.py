"""Create sessions table

Revision ID: 5d88e65ab411
Revises:
Create Date: 2026-02-01 16:23:36.108268

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5d88e65ab411"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column("workspace_path", sa.String(512), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column(
            "archived", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("ttl_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sessions")
