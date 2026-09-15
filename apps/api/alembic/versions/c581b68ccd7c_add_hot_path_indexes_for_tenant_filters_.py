"""add hot-path indexes for tenant filters and joins

Gap audit 2026-09-15 (performance/latency pass): Postgres never
auto-indexes a ForeignKey column, and this codebase's models never
declared `index=True` on any of them — verified against every prior
migration (`grep -rin "index" alembic/versions/*.py`), which shows only
two indexes ever created (both unique login-lookup indexes on
organizations.slug/users.email, unrelated to these columns). Every
tenant-scoped lookup and join on the retrieval/chat hot path
(ADR-009's mandatory `organization_id` filter, citation building's
`document_id IN (...)`, the exact-match join on `source_node_id`, and
plain conversation/message lookups) has been a full sequential scan
since day one. Harmless at today's near-empty dev data volume; would
become a severe, compounding latency problem at real production row
counts. Purely additive — CREATE INDEX changes no query results, only
the plan Postgres chooses.

Revision ID: c581b68ccd7c
Revises: f22223eeba67
Create Date: 2026-09-15 14:02:21.668054

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c581b68ccd7c'
down_revision: Union[str, Sequence[str], None] = 'f22223eeba67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = [
    ("ix_documents_organization_id", "documents", ["organization_id"]),
    ("ix_document_versions_organization_id", "document_versions", ["organization_id"]),
    ("ix_document_versions_document_id", "document_versions", ["document_id"]),
    ("ix_document_chunks_organization_id", "document_chunks", ["organization_id"]),
    ("ix_document_chunks_document_id", "document_chunks", ["document_id"]),
    ("ix_document_chunks_document_version_id", "document_chunks", ["document_version_id"]),
    ("ix_document_chunks_source_node_id", "document_chunks", ["source_node_id"]),
    ("ix_document_nodes_organization_id", "document_nodes", ["organization_id"]),
    ("ix_document_nodes_document_version_id", "document_nodes", ["document_version_id"]),
    ("ix_document_regions_organization_id", "document_regions", ["organization_id"]),
    ("ix_document_regions_document_version_id", "document_regions", ["document_version_id"]),
    ("ix_conversations_organization_id", "conversations", ["organization_id"]),
    ("ix_messages_conversation_id", "messages", ["conversation_id"]),
    ("ix_message_sources_message_id", "message_sources", ["message_id"]),
    ("ix_message_sources_document_id", "message_sources", ["document_id"]),
]


def upgrade() -> None:
    """Upgrade schema."""
    for index_name, table_name, columns in _INDEXES:
        op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    """Downgrade schema."""
    for index_name, table_name, _columns in reversed(_INDEXES):
        op.drop_index(index_name, table_name=table_name)
