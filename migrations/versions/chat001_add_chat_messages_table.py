"""add_chat_messages_table

Revision ID: chat001
Revises: 4bd8cd1f8ec7
Create Date: 2026-02-03 18:08:27.525618

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "chat001"
down_revision: Union[str, None] = "4bd8cd1f8ec7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.session_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        "idx_chat_messages_session_id", "chat_messages", ["session_id"], unique=False
    )
    op.create_index(
        "idx_chat_messages_created_at", "chat_messages", ["created_at"], unique=False
    )
    op.create_index(
        "idx_chat_messages_status", "chat_messages", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_chat_messages_status", table_name="chat_messages")
    op.drop_index("idx_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("idx_chat_messages_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")
