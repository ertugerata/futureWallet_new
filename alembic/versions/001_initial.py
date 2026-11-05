"""
İlk Alembic migration (001_initial) — FutureWallet şeması.

Bu migration, db.py'deki mevcut SQLAlchemy modellerinin
(Basic Declarative Base) karşılığını oluşturur.

Models:
  - transactions  (İşlem Defteri / Event Sourcing Ledger)
  - decisions     (Karar Günlüğü)
  - shadow_portfolios (Gölge Portföy / What-If)
  - macro_data    (Benchmark & Enflasyon Önbelleği)

NOT: Bu dosya el yazısıyla oluşturulmuştur. Gerçek bir proyette
`alembic revision --autogenerate -m "initial"` ile models'dan
otomatik üretilmek gerekirdi. Yine de aşağıdaki table-level
tanımlar, Base.metadata.create_all() ile üretilen DB şemasıyla
veilingar betimler.

İleri migration'lar için:
  alembic revision --autogenerate -m "tanım_adı"
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    MetaData,
    String,
    Table,
    Text,
    func,
)

from alembic import op

# ---------------------------------------------------------------------------
# Metadata ve tabel tanımları
# ---------------------------------------------------------------------------


def _uuid_pk(name: str):
    """UUID text primary key column factory."""
    return Column(
        "id",
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )


def _uuid_fkey(col_name: str, ref_table: str):
    """UUID foreign key column."""
    return Column(
        col_name,
        String(36),
        # ForeignKey eklenmez demi; ileride migrate/relationship ile
        # ilişkisel kısıt eklenir. Şu an tablo yapısı yalnızca kolon.
    )


def _optional_date_col(col_name: str = "date"):
    return Column(col_name, DateTime, nullable=True)


def _default_now_col(col_name: str = "created_at"):
    return Column(col_name, DateTime, default=func.now())


# ============================================================================
# transactions
# ============================================================================

transactions = Table(
    "transactions",
    MetaData(),
    _uuid_pk("id"),
    Column("asset_symbol", String(20), nullable=False),
    Column(
        "type", String(20), nullable=False
    ),  # BUY, SELL, DIVIDEND, CASH_IN, CASH_OUT
    Column("quantity", Float, nullable=False),
    Column("price", Float, nullable=False),
    Column("fee", Float, nullable=True),
    Column("timestamp", DateTime, nullable=False),
    Column("voided", Boolean, nullable=False, server_default="0"),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column(
        "updated_at",
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
)


# ============================================================================
# decisions
# ============================================================================

decisions = Table(
    "decisions",
    MetaData(),
    _uuid_pk("id"),
    Column("asset_symbol", String(20), nullable=False),
    Column("action", String(10), nullable=False),  # BUY, SELL, HOLD
    Column(
        "rationale", Text, nullable=True
    ),  # max 5000 karakter (app katmanı validasyonu)
    Column(
        "sentiment", String(30), nullable=True
    ),  # FOMO, STRATEGIC, PANIC, DIVIDEND, RISK_REDUCTION
    Column("target_price", Float, nullable=True),
    Column("target_date", Date, nullable=True),
    Column(
        "status", String(20), nullable=False, server_default="OPEN"
    ),  # OPEN, REVIEWED, EXPIRED
    Column("ai_retrospective", Text, nullable=True),
    Column("transaction_id", String(36), nullable=True),
    Column("outcome_return_pct", Float, nullable=True),
    Column("outcome_price", Float, nullable=True),
    Column("decision_date", DateTime, nullable=True),
    Column("target_hit", Boolean, nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column(
        "updated_at",
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
)


# ============================================================================
# shadow_portfolios
# ============================================================================

shadow_portfolios = Table(
    "shadow_portfolios",
    MetaData(),
    _uuid_pk("id"),
    Column("decision_id", String(36), nullable=True),
    Column("asset_symbol", String(20), nullable=False),
    Column("shadow_type", String(20), nullable=False),  # HELD_INSTEAD, BOUGHT_INSTEAD
    Column("entry_date", DateTime, nullable=False),
    Column("entry_price", Float, nullable=False),
    Column("quantity", Float, nullable=False),
    Column("exit_date", DateTime, nullable=True),
    Column("asset_type", String(20), nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
)


# ============================================================================
# macro_data
# ============================================================================

macro_data = Table(
    "macro_data",
    MetaData(),
    Column("date", Date, primary_key=True),
    Column("gold_try", Float, nullable=True),
    Column("gold_usd", Float, nullable=True),
    Column("sp500", Float, nullable=True),
    Column("tr_cpi", Float, nullable=True),
    Column("us_cpi", Float, nullable=True),
    Column("source", String(50), nullable=True),
    Column("is_estimate", Boolean, nullable=False, server_default="0"),
    Column("updated_at", DateTime, nullable=False, server_default=func.now()),
)


# ============================================================================
# Migration işlevleri
# ============================================================================

# pylint: disable=missing-docstring
# pylint: disable=invalid-name


def upgrade() -> None:
    """Tüm tabloları oluştur (PRAGMA foreign_keys geleneksel DB kurtarıcısı
    tarafından administration seviyesinde işletilir; DB driver side którego
    açılır)."""
    op.create_table(
        transactions.name,
        *transactions.c,
        schema=None,
    )
    op.create_table(
        decisions.name,
        *decisions.c,
        schema=None,
    )
    op.create_table(
        shadow_portfolios.name,
        *shadow_portfolios.c,
        schema=None,
    )
    op.create_table(
        macro_data.name,
        *macro_data.c,
        schema=None,
    )


def downgrade() -> None:
    """Tabloları sırasıyla kaldır (şu an bağımsız tablolar böylece
    sırasız silinebilir; ileride FK ilişkileri eklense ters sıra
    gerekebilir)."""
    op.drop_table(shadow_portfolios)
    op.drop_table(decisions)
    op.drop_table(transactions)
    op.drop_table(macro_data)
