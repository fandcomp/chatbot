"""add LAN-M5 budget control (pricing_rates, budgets, usage_ledger_entries)

Closes the addendum's "no budget/quota enforcement" gap (§8) — a real
admission-control gate in front of the only currently-paid ingestion call
(Voyage embedding). Additive: three new tables, one new
ProcessingJobStatus.PAUSED_BUDGET enum value, one seed pricing row (pilot
placeholder, not a benchmarked production rate — see .env.example).

Revision ID: f4a1c8e2b9d6
Revises: d3e8f1a4c6b2
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a1c8e2b9d6'
down_revision: Union[str, Sequence[str], None] = 'd3e8f1a4c6b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE processing_job_status ADD VALUE IF NOT EXISTS 'PAUSED_BUDGET'")

    lan_budget_type = sa.Enum('INGESTION', 'CHAT', name='lan_budget_type')
    lan_usage_ledger_entry_status = sa.Enum(
        'RESERVED', 'SETTLED', 'RELEASED', name='lan_usage_ledger_entry_status'
    )

    op.create_table(
        'pricing_rates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('unit', sa.String(length=50), nullable=False),
        sa.Column('price_usd', sa.Numeric(10, 6), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('effective_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'budgets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('budget_type', lan_budget_type, nullable=False),
        sa.Column('limit_usd', sa.Numeric(12, 2), nullable=False),
        sa.Column('spent_usd', sa.Numeric(12, 6), nullable=False),
        sa.Column('reserved_usd', sa.Numeric(12, 6), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'budget_type', name='uq_budget_org_type'),
    )

    op.create_table(
        'usage_ledger_entries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('budget_id', sa.UUID(), nullable=False),
        sa.Column('source_entry_id', sa.UUID(), nullable=True),
        sa.Column('job_id', sa.UUID(), nullable=True),
        sa.Column('stage', sa.String(length=50), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('quantity', sa.Numeric(14, 2), nullable=False),
        sa.Column('unit', sa.String(length=50), nullable=False),
        sa.Column('unit_price_usd', sa.Numeric(10, 6), nullable=False),
        sa.Column('amount_usd', sa.Numeric(12, 6), nullable=False),
        sa.Column('status', lan_usage_ledger_entry_status, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('settled_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.ForeignKeyConstraint(['budget_id'], ['budgets.id'], ),
        sa.ForeignKeyConstraint(['source_entry_id'], ['source_entries.id'], ),
        sa.ForeignKeyConstraint(['job_id'], ['processing_jobs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Pilot placeholder rate, not a benchmarked production price — an admin
    # UI to manage rates is deferred (LAN-M5's own follow-up), so ingestion
    # needs at least one active rate to function until then.
    op.execute(
        """
        INSERT INTO pricing_rates (id, provider, unit, price_usd, currency, effective_from, source, created_at)
        VALUES (gen_random_uuid(), 'voyage', '1k_tokens', 0.00012, 'USD', now(),
                'pilot placeholder — not a benchmarked production rate, see .env.example', now())
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('usage_ledger_entries')
    op.drop_table('budgets')
    op.drop_table('pricing_rates')
    sa.Enum(name='lan_usage_ledger_entry_status').drop(op.get_bind())
    sa.Enum(name='lan_budget_type').drop(op.get_bind())
    # PAUSED_BUDGET is not removed from processing_job_status — Postgres has
    # no ALTER TYPE ... DROP VALUE; same accepted limitation as any other
    # additive enum-value migration.
