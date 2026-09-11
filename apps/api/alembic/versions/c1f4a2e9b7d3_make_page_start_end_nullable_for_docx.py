"""make page_start/page_end nullable for DOCX support (LAN-M3)

DOCX has no Docling page provenance at all (addendum §5, ADDENDUM_LAN_
ARCHIVE_4TB_COST_CONTROL.md) — a DOCX-derived region/node/chunk/citation
snapshot has no real page number to report, and must never fabricate one.
Widening NOT NULL -> nullable is additive and safe: no existing row's value
changes, only new DOCX-sourced rows will ever actually store NULL here.

Revision ID: c1f4a2e9b7d3
Revises: a7057580f523
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1f4a2e9b7d3'
down_revision: Union[str, Sequence[str], None] = 'a7057580f523'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("document_regions", "document_nodes", "document_chunks", "message_sources")


def upgrade() -> None:
    """Upgrade schema."""
    for table in _TABLES:
        op.alter_column(table, "page_start", existing_type=sa.Integer(), nullable=True)
        op.alter_column(table, "page_end", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    for table in _TABLES:
        op.alter_column(table, "page_end", existing_type=sa.Integer(), nullable=False)
        op.alter_column(table, "page_start", existing_type=sa.Integer(), nullable=False)
