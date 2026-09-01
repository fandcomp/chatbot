"""baseline

Revision ID: d20b62a94abd
Revises: 
Create Date: 2026-09-01 13:20:26.196815

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = 'd20b62a94abd'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
