"""LAN-M3 (docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md §5) — closes the
"no embedding cache" gap: a chunk's dense embedding only ever depends on its
`contextual_text` plus the embedding config that produced it, never on which
tenant/document it came from, so this cache is deliberately global rather
than organization-scoped (mirrors the content-hash storage dedup already
used for LAN-M2 promotion).
"""

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmbeddingCacheEntry(Base):
    __tablename__ = "embedding_cache_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # sha256(contextual_text) + model + revision + dimension + normalized —
    # the addendum's exact cache key. Unique so a second worker racing to
    # cache the same text/config either inserts once or no-ops on conflict
    # (ON CONFLICT DO NOTHING at the call site), never duplicates.
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    revision: Mapped[str] = mapped_column(String(255), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized: Mapped[bool] = mapped_column(Boolean, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
