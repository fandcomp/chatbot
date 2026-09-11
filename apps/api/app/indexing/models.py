"""LAN-M3 (docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md §5) — closes the
"no embedding cache" gap: a chunk's dense embedding only ever depends on its
`contextual_text` plus the embedding config that produced it, never on which
tenant/document it came from, so this cache is deliberately global rather
than organization-scoped (mirrors the content-hash storage dedup already
used for LAN-M2 promotion).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
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


class BudgetType(str, enum.Enum):
    """LAN-M5 (addendum §8) — 'ingestion budget separate from chat budget' is
    modeled as a column, not two schemas. Only INGESTION is actually
    enforced this milestone; CHAT exists so a future milestone wiring chat
    enforcement needs no schema change.
    """

    INGESTION = "INGESTION"
    CHAT = "CHAT"


class UsageLedgerEntryStatus(str, enum.Enum):
    RESERVED = "RESERVED"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"


class PricingRate(Base):
    """Versioned+dated pricing (addendum §8): 'tarif configurable dengan
    currency, unit, tanggal berlaku, sumber — bukan angka yang di-hardcode'.
    Current rate for a provider/unit = the row with the latest
    effective_from where effective_from <= now and (effective_until is null
    or effective_until > now). No active row = no known price — reservation
    must never treat that as free (see budget.py).
    """

    __tablename__ = "pricing_rates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    price_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Free-text provenance for the rate (e.g. "voyage.ai pricing page,
    # 2026-09-11") — an audit trail, never parsed.
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Budget(Base):
    """One row per (organization, budget_type). `reserved_usd` is the sum of
    this org's currently-RESERVED ledger entries; `spent_usd` is the sum of
    SETTLED ones. Admission control checks spent_usd + reserved_usd against
    limit_usd atomically at reservation time (budget.py) — never here.
    """

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("organization_id", "budget_type", name="uq_budget_org_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    budget_type: Mapped[BudgetType] = mapped_column(
        SAEnum(BudgetType, name="lan_budget_type"), nullable=False
    )
    limit_usd: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    spent_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    reserved_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UsageLedgerEntry(Base):
    """Usage ledger per tenant/source/job/stage/provider (addendum §8). Each
    row is created RESERVED (an estimate, before dispatch), then moves to
    SETTLED (actual usage, after completion) or RELEASED (the stage never
    ran — e.g. the job failed before calling the provider).
    """

    __tablename__ = "usage_ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id"), nullable=False
    )
    # NULL for an ordinary upload, set for a LAN-promoted document — mirrors
    # DocumentVersion.source_entry_id exactly (LAN-M2), so no extra join is
    # needed at the reservation call site. Same nullable-provenance pattern
    # as LAN-M3's page_start/page_end.
    source_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_entries.id"), nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_jobs.id"), nullable=True
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    unit_price_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    status: Mapped[UsageLedgerEntryStatus] = mapped_column(
        SAEnum(UsageLedgerEntryStatus, name="lan_usage_ledger_entry_status"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
