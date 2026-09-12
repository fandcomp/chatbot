"""LAN-M5 (addendum §8) — admission-control gate in front of the only
currently-paid ingestion call (Voyage embedding). Reuses this repo's
existing atomic-claim idiom (LAN-M2's lease claim in sources_tasks.py: one
conditional UPDATE checked by rowcount) rather than introducing a
SELECT ... FOR UPDATE pattern that doesn't exist anywhere else in this
codebase.

"Unknown price is never treated as zero" (addendum §8) is unconditional
here, not a config toggle — no active pricing rate for a provider/unit
always raises BudgetExceededError, the same as a budget with no room left.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import budgets, pricing_rates, usage_ledger_entries

_TOKEN_PRICING_UNIT = "1k_tokens"


class BudgetExceededError(Exception):
    """Raised when an ingestion budget reservation cannot be made — either
    the organization's ingestion budget has no room, or no pricing rate is
    currently known for the provider/unit.
    """


async def get_current_rate(session: AsyncSession, provider: str, unit: str) -> dict | None:
    now = datetime.now(UTC)
    row = (
        await session.execute(
            select(pricing_rates)
            .where(
                pricing_rates.c.provider == provider,
                pricing_rates.c.unit == unit,
                pricing_rates.c.effective_from <= now,
                (pricing_rates.c.effective_until.is_(None))
                | (pricing_rates.c.effective_until > now),
            )
            .order_by(pricing_rates.c.effective_from.desc())
            .limit(1)
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _ensure_budget_row(
    session: AsyncSession, organization_id: uuid.UUID, budget_type: str
) -> None:
    stmt = (
        pg_insert(budgets)
        .values(
            id=uuid.uuid4(),
            organization_id=organization_id,
            budget_type=budget_type,
            limit_usd=settings.INGESTION_BUDGET_DEFAULT_USD,
            spent_usd=0,
            reserved_usd=0,
            updated_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=["organization_id", "budget_type"])
    )
    await session.execute(stmt)


async def reserve_ingestion_budget(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    source_entry_id: uuid.UUID | None,
    job_id: uuid.UUID | None,
    stage: str,
    provider: str,
    token_count: int,
) -> uuid.UUID:
    """Reserves budget for `token_count` tokens against the organization's
    INGESTION budget (lazily created with `settings.
    INGESTION_BUDGET_DEFAULT_USD` on first use). Returns the new RESERVED
    ledger entry's id on success; raises BudgetExceededError otherwise —
    caller decides how to pause/retry.
    """
    rate = await get_current_rate(session, provider, _TOKEN_PRICING_UNIT)
    if rate is None:
        raise BudgetExceededError(f"No active pricing rate for {provider}/{_TOKEN_PRICING_UNIT}.")

    quantity = token_count / 1000
    amount_usd = quantity * float(rate["price_usd"])

    await _ensure_budget_row(session, organization_id, "INGESTION")
    now = datetime.now(UTC)
    # Single conditional UPDATE: WHERE and SET are evaluated atomically per
    # row by Postgres, so a concurrent reservation against the same budget
    # row serializes correctly with no explicit lock statement needed —
    # zero rows affected means no room, not a race condition.
    result = await session.execute(
        update(budgets)
        .where(
            budgets.c.organization_id == organization_id,
            budgets.c.budget_type == "INGESTION",
            (budgets.c.spent_usd + budgets.c.reserved_usd + amount_usd) <= budgets.c.limit_usd,
        )
        .values(reserved_usd=budgets.c.reserved_usd + amount_usd, updated_at=now)
        .returning(budgets.c.id)
    )
    budget_row = result.mappings().one_or_none()
    if budget_row is None:
        # Persist the lazily-created budget row even though this particular
        # reservation failed, so the next attempt doesn't need to re-create it.
        await session.commit()
        raise BudgetExceededError(f"Ingestion budget exceeded for organization {organization_id}.")

    entry_id = uuid.uuid4()
    await session.execute(
        insert(usage_ledger_entries).values(
            id=entry_id,
            organization_id=organization_id,
            budget_id=budget_row["id"],
            source_entry_id=source_entry_id,
            job_id=job_id,
            stage=stage,
            provider=provider,
            quantity=quantity,
            unit=_TOKEN_PRICING_UNIT,
            unit_price_usd=rate["price_usd"],
            amount_usd=amount_usd,
            status="RESERVED",
            created_at=now,
        )
    )
    await session.commit()
    return entry_id


async def settle_usage(session: AsyncSession, ledger_entry_id: uuid.UUID) -> None:
    """Moves a RESERVED entry to SETTLED — reserved_usd -> spent_usd on the
    budget row, at the same amount that was reserved. This milestone does
    not reconcile against Voyage's real billed total_tokens (documented
    deferred precision improvement, see docs/LAN_ARCHIVE_PROGRESS.md).
    """
    entry = (
        await session.execute(
            select(usage_ledger_entries).where(usage_ledger_entries.c.id == ledger_entry_id)
        )
    ).mappings().one()

    now = datetime.now(UTC)
    await session.execute(
        update(budgets)
        .where(budgets.c.id == entry["budget_id"])
        .values(
            reserved_usd=budgets.c.reserved_usd - entry["amount_usd"],
            spent_usd=budgets.c.spent_usd + entry["amount_usd"],
            updated_at=now,
        )
    )
    await session.execute(
        update(usage_ledger_entries)
        .where(usage_ledger_entries.c.id == ledger_entry_id)
        .values(status="SETTLED", settled_at=now)
    )
    await session.commit()


async def release_reservation(session: AsyncSession, ledger_entry_id: uuid.UUID) -> None:
    """Moves a RESERVED entry to RELEASED — the stage never actually ran
    (e.g. the embedding call itself failed after budget was reserved).
    reserved_usd is given back in full; nothing is ever charged to
    spent_usd for work that never happened.
    """
    entry = (
        await session.execute(
            select(usage_ledger_entries).where(usage_ledger_entries.c.id == ledger_entry_id)
        )
    ).mappings().one()

    now = datetime.now(UTC)
    await session.execute(
        update(budgets)
        .where(budgets.c.id == entry["budget_id"])
        .values(reserved_usd=budgets.c.reserved_usd - entry["amount_usd"], updated_at=now)
    )
    await session.execute(
        update(usage_ledger_entries)
        .where(usage_ledger_entries.c.id == ledger_entry_id)
        .values(status="RELEASED")
    )
    await session.commit()


async def reconcile_stale_reservations(
    session: AsyncSession, *, stale_after_seconds: int
) -> list[uuid.UUID]:
    """LAN-M6 gap (found writing the pilot rollout guide): a worker process
    killed between `reserve_ingestion_budget` and `settle_usage`/
    `release_reservation` — not just a retried Celery task, the process
    itself lost — leaves a RESERVED ledger entry forever, permanently
    shrinking that org's real budget headroom for work that never happened.
    No normal call path takes anywhere near `stale_after_seconds` to go from
    reserve to settle/release, so any RESERVED entry older than that is
    dead, not merely slow.

    Meant to run periodically (see the `reconcile_stale_budget_reservations`
    Celery task and its beat schedule), not from the indexing pipeline
    itself. Reuses the same atomic-claim idiom as `reserve_ingestion_budget`:
    one conditional `UPDATE ... WHERE status = 'RESERVED'` per entry, so an
    entry that settles/releases through the normal path at the exact same
    moment can never be double-released — zero rows affected means "already
    handled elsewhere," not a race to correct.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
    stale_ids = (
        await session.execute(
            select(usage_ledger_entries.c.id).where(
                usage_ledger_entries.c.status == "RESERVED",
                usage_ledger_entries.c.created_at < cutoff,
            )
        )
    ).scalars().all()

    reconciled: list[uuid.UUID] = []
    for entry_id in stale_ids:
        claimed = (
            await session.execute(
                update(usage_ledger_entries)
                .where(
                    usage_ledger_entries.c.id == entry_id,
                    usage_ledger_entries.c.status == "RESERVED",
                )
                .values(status="RELEASED")
                .returning(usage_ledger_entries.c.budget_id, usage_ledger_entries.c.amount_usd)
            )
        ).mappings().one_or_none()
        if claimed is None:
            continue

        await session.execute(
            update(budgets)
            .where(budgets.c.id == claimed["budget_id"])
            .values(
                reserved_usd=budgets.c.reserved_usd - claimed["amount_usd"],
                updated_at=datetime.now(UTC),
            )
        )
        reconciled.append(entry_id)

    await session.commit()
    return reconciled
