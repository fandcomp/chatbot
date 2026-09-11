"""add embedding cache entries (LAN-M3)

Closes the addendum's "no embedding cache" gap (§5) — dense embeddings keyed
on sha256(contextual_text) + model + revision + dimension + normalized, so
an unchanged chunk's text never gets re-embedded across document versions or
duplicate-content promotions. Additive: new table only, no existing table
touched.

Revision ID: d3e8f1a4c6b2
Revises: c1f4a2e9b7d3
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd3e8f1a4c6b2'
down_revision: Union[str, Sequence[str], None] = 'c1f4a2e9b7d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'embedding_cache_entries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('cache_key', sa.String(length=64), nullable=False),
        sa.Column('model', sa.String(length=255), nullable=False),
        sa.Column('revision', sa.String(length=255), nullable=False),
        sa.Column('dimension', sa.Integer(), nullable=False),
        sa.Column('normalized', sa.Boolean(), nullable=False),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cache_key', name='uq_embedding_cache_entry_cache_key'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('embedding_cache_entries')
