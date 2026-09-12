"""add source_roots.is_enabled (LAN-M6 gap: disable a misconfigured source)

Closes the runbook's "no disable this source endpoint" gap — additive,
non-null with a `true` server default so every existing SourceRoot row
stays enabled exactly as it behaved before this column existed.

Revision ID: b6e2f0a3c1d4
Revises: f4a1c8e2b9d6
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6e2f0a3c1d4'
down_revision: Union[str, Sequence[str], None] = 'f4a1c8e2b9d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'source_roots',
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('source_roots', 'is_enabled')
