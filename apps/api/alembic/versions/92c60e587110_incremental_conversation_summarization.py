"""incremental conversation summarization

Gap audit 2026-09-15 (performance/latency pass, finding #5): ConversationService
fetched a conversation's ENTIRE message history every turn and, whenever any
message aged out of the recent-message window, resummarized the whole
older-than-window transcript from scratch — a query and an LLM call whose
cost both grow without bound as a conversation lengthens.

Replaces this with an incremental design: build_conversation_context now
fetches only a bounded recent-message window plus the small delta of
messages that aged out of it since the last turn, and folds just that delta
into the existing summary via one incremental LLM call. `messages`' index is
upgraded from conversation_id-only to a (conversation_id, created_at)
composite so both the windowed fetch and the delta range query are index
range scans, not full per-conversation scans.

Revision ID: 92c60e587110
Revises: c581b68ccd7c
Create Date: 2026-09-15 15:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92c60e587110'
down_revision: Union[str, Sequence[str], None] = 'c581b68ccd7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "conversation_summaries",
        sa.Column("summarized_through_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.create_index(
        "ix_messages_conversation_id_created_at", "messages", ["conversation_id", "created_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.drop_column("conversation_summaries", "summarized_through_created_at")
