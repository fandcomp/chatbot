import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import insert, select, text

from app.core.config import settings
from app.database import (
    async_session_factory,
    budgets,
    engine,
    pricing_rates,
    usage_ledger_entries,
)
from app.indexing.budget import (
    BudgetExceededError,
    get_current_rate,
    release_reservation,
    reserve_ingestion_budget,
    settle_usage,
)

# reserve_ingestion_budget always prices in "1k_tokens" (budget.py's private
# _TOKEN_PRICING_UNIT) — the rate fixture must match that unit exactly for
# reservation-based tests. get_current_rate itself is unit-agnostic, so the
# direct rate-lookup tests below exercise an arbitrary unit separately.
_TEST_PROVIDER = "test-provider"
_TEST_UNIT = "1k_tokens"


@pytest_asyncio.fixture
async def org_id() -> AsyncGenerator[uuid.UUID, None]:
    """A bare organizations row — budgets.organization_id is a real FK, so
    reservation tests need one to exist, but none of the document/version/
    job scaffolding conftest.py's seeded_document_version fixture builds.
    """
    new_org_id = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:id, 'Budget Test Org', :slug)"),
            {"id": new_org_id, "slug": f"budget-test-{new_org_id}"},
        )

    yield new_org_id

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM usage_ledger_entries WHERE organization_id = :id"), {"id": new_org_id}
        )
        await conn.execute(text("DELETE FROM budgets WHERE organization_id = :id"), {"id": new_org_id})
        await conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": new_org_id})


@pytest_asyncio.fixture
async def rate() -> AsyncGenerator[None, None]:
    """A known-good current rate for _TEST_PROVIDER/_TEST_UNIT — $1.00 per
    test-unit, chosen so reservation amounts are easy to reason about.
    """
    rate_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            insert(pricing_rates).values(
                id=rate_id,
                provider=_TEST_PROVIDER,
                unit=_TEST_UNIT,
                price_usd=1.0,
                currency="USD",
                effective_from=datetime.now(UTC) - timedelta(days=1),
                effective_until=None,
                source="test fixture",
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    yield

    async with async_session_factory() as session:
        await session.execute(
            pricing_rates.delete().where(pricing_rates.c.id == rate_id)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_get_current_rate_finds_an_active_rate(rate) -> None:
    async with async_session_factory() as session:
        found = await get_current_rate(session, _TEST_PROVIDER, _TEST_UNIT)
    assert found is not None
    assert float(found["price_usd"]) == 1.0


@pytest.mark.asyncio
async def test_get_current_rate_returns_none_for_unknown_provider() -> None:
    async with async_session_factory() as session:
        found = await get_current_rate(session, "nonexistent-provider", "nonexistent-unit")
    assert found is None


@pytest.mark.asyncio
async def test_get_current_rate_excludes_an_expired_rate(org_id) -> None:
    rate_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            insert(pricing_rates).values(
                id=rate_id,
                provider="expired-provider",
                unit=_TEST_UNIT,
                price_usd=1.0,
                currency="USD",
                effective_from=datetime.now(UTC) - timedelta(days=10),
                effective_until=datetime.now(UTC) - timedelta(days=1),
                source="test fixture — expired",
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    try:
        async with async_session_factory() as session:
            found = await get_current_rate(session, "expired-provider", _TEST_UNIT)
        assert found is None
    finally:
        async with async_session_factory() as session:
            await session.execute(pricing_rates.delete().where(pricing_rates.c.id == rate_id))
            await session.commit()


@pytest.mark.asyncio
async def test_reserve_ingestion_budget_succeeds_within_limit(org_id, rate, monkeypatch) -> None:
    monkeypatch.setattr(settings, "INGESTION_BUDGET_DEFAULT_USD", 100.0)

    async with async_session_factory() as session:
        entry_id = await reserve_ingestion_budget(
            session,
            organization_id=org_id,
            source_entry_id=None,
            job_id=None,
            stage="EMBEDDING",
            provider=_TEST_PROVIDER,
            token_count=1000,  # 1 test-unit * $1.00 = $1.00
        )

    async with async_session_factory() as session:
        budget_row = (
            await session.execute(select(budgets).where(budgets.c.organization_id == org_id))
        ).mappings().one()
        entry_row = (
            await session.execute(
                select(usage_ledger_entries).where(usage_ledger_entries.c.id == entry_id)
            )
        ).mappings().one()

    assert float(budget_row["reserved_usd"]) == 1.0
    assert float(budget_row["spent_usd"]) == 0.0
    assert entry_row["status"] == "RESERVED"
    assert float(entry_row["amount_usd"]) == 1.0


@pytest.mark.asyncio
async def test_reserve_ingestion_budget_raises_when_over_the_limit(org_id, rate, monkeypatch) -> None:
    monkeypatch.setattr(settings, "INGESTION_BUDGET_DEFAULT_USD", 0.50)

    async with async_session_factory() as session:
        with pytest.raises(BudgetExceededError):
            await reserve_ingestion_budget(
                session,
                organization_id=org_id,
                source_entry_id=None,
                job_id=None,
                stage="EMBEDDING",
                provider=_TEST_PROVIDER,
                token_count=1000,  # $1.00 > the $0.50 limit
            )

    # The budget row is still lazily created (at the configured limit) even
    # though this reservation failed — the next attempt shouldn't need to
    # recreate it, and reserved_usd must be untouched by the failed attempt.
    async with async_session_factory() as session:
        budget_row = (
            await session.execute(select(budgets).where(budgets.c.organization_id == org_id))
        ).mappings().one()
    assert float(budget_row["limit_usd"]) == 0.50
    assert float(budget_row["reserved_usd"]) == 0.0


@pytest.mark.asyncio
async def test_reserve_ingestion_budget_never_treats_an_unknown_price_as_free(org_id) -> None:
    # No `rate` fixture here — _TEST_PROVIDER/_TEST_UNIT has no active rate.
    async with async_session_factory() as session:
        with pytest.raises(BudgetExceededError):
            await reserve_ingestion_budget(
                session,
                organization_id=org_id,
                source_entry_id=None,
                job_id=None,
                stage="EMBEDDING",
                provider=_TEST_PROVIDER,
                token_count=1000,
            )


@pytest.mark.asyncio
async def test_settle_usage_moves_reserved_to_spent(org_id, rate, monkeypatch) -> None:
    monkeypatch.setattr(settings, "INGESTION_BUDGET_DEFAULT_USD", 100.0)

    async with async_session_factory() as session:
        entry_id = await reserve_ingestion_budget(
            session,
            organization_id=org_id,
            source_entry_id=None,
            job_id=None,
            stage="EMBEDDING",
            provider=_TEST_PROVIDER,
            token_count=1000,
        )

    async with async_session_factory() as session:
        await settle_usage(session, entry_id)

    async with async_session_factory() as session:
        budget_row = (
            await session.execute(select(budgets).where(budgets.c.organization_id == org_id))
        ).mappings().one()
        entry_row = (
            await session.execute(
                select(usage_ledger_entries).where(usage_ledger_entries.c.id == entry_id)
            )
        ).mappings().one()

    assert float(budget_row["reserved_usd"]) == 0.0
    assert float(budget_row["spent_usd"]) == 1.0
    assert entry_row["status"] == "SETTLED"
    assert entry_row["settled_at"] is not None


@pytest.mark.asyncio
async def test_release_reservation_gives_back_reserved_without_charging_spent(
    org_id, rate, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "INGESTION_BUDGET_DEFAULT_USD", 100.0)

    async with async_session_factory() as session:
        entry_id = await reserve_ingestion_budget(
            session,
            organization_id=org_id,
            source_entry_id=None,
            job_id=None,
            stage="EMBEDDING",
            provider=_TEST_PROVIDER,
            token_count=1000,
        )

    async with async_session_factory() as session:
        await release_reservation(session, entry_id)

    async with async_session_factory() as session:
        budget_row = (
            await session.execute(select(budgets).where(budgets.c.organization_id == org_id))
        ).mappings().one()
        entry_row = (
            await session.execute(
                select(usage_ledger_entries).where(usage_ledger_entries.c.id == entry_id)
            )
        ).mappings().one()

    assert float(budget_row["reserved_usd"]) == 0.0
    assert float(budget_row["spent_usd"]) == 0.0
    assert entry_row["status"] == "RELEASED"


@pytest.mark.asyncio
async def test_concurrent_reservations_near_the_ceiling_never_oversubscribe(
    org_id, rate, monkeypatch
) -> None:
    # Exactly one $1.00 reservation fits in a $1.00 budget — two racing to
    # reserve it at once must never both succeed (the atomic conditional
    # UPDATE, not an application-level lock, is what prevents this).
    monkeypatch.setattr(settings, "INGESTION_BUDGET_DEFAULT_USD", 1.0)

    async def _try_reserve() -> uuid.UUID | None:
        async with async_session_factory() as session:
            try:
                return await reserve_ingestion_budget(
                    session,
                    organization_id=org_id,
                    source_entry_id=None,
                    job_id=None,
                    stage="EMBEDDING",
                    provider=_TEST_PROVIDER,
                    token_count=1000,
                )
            except BudgetExceededError:
                return None

    results = await asyncio.gather(_try_reserve(), _try_reserve())
    succeeded = [r for r in results if r is not None]
    assert len(succeeded) == 1

    async with async_session_factory() as session:
        budget_row = (
            await session.execute(select(budgets).where(budgets.c.organization_id == org_id))
        ).mappings().one()
    assert float(budget_row["reserved_usd"]) == 1.0
