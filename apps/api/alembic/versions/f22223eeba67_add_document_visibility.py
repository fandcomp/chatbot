"""add document visibility (ADR-021: PUBLIC/INTERNAL/RESTRICTED)

Additive, non-null with a `PUBLIC` server default so every existing
Document row stays visible to every role exactly as it behaved before
this column existed — see ADR-021's Alternatives section for why
`RESTRICTED` would be an unsafe default here.

Revision ID: f22223eeba67
Revises: b6e2f0a3c1d4
Create Date: 2026-09-14 14:21:45.174311

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f22223eeba67'
down_revision: Union[str, Sequence[str], None] = 'b6e2f0a3c1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    document_visibility = sa.Enum('PUBLIC', 'INTERNAL', 'RESTRICTED', name='document_visibility')
    document_visibility.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'documents',
        sa.Column('visibility', document_visibility, nullable=False, server_default='PUBLIC'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'visibility')
    sa.Enum(name='document_visibility').drop(op.get_bind(), checkfirst=True)
