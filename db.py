"""
FutureWallet - SQLAlchemy 2.0 Veritabanı Modelleri

Event-Sourcing üzerinden tüm işlemler zaman damgalı olarak saklanır.

Prompt 6 düzeltmeleri ile senkronize:
  - config.DATABASE_URL kullanımı (DB_NAME kaldırıldı)
  - PRAGMA foreign_keys=ON, journal_mode=WAL (event listener)
  - check_same_thread=False (connect_args)
  - Transaction.decision cascade "delete" → kaldırıldı; ondelete="SET NULL"
  - logging kullanımı (print kaldırıldı)
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQLAlchemy taban class
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# 5.1 transactions (İşlem Defteri / Event Sourcing Ledger)
# ---------------------------------------------------------------------------


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    asset_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, default=0.0)

    # Decision ilişkisi: Transaction silinince Decision SILINMEMSİN
    # → ondelete="SET NULL" (Decision.transaction_id NULL olur)
    # → cascade="delete" KALDIRILDI (eski: decision cascade="delete")
    decision: Mapped[Decision | None] = relationship(
        "Decision",
        back_populates="transaction",
        uselist=False,
        cascade="",  # cascade kaldırıldı; ondelete="SET NULL" FK seviyesinde
    )


# ---------------------------------------------------------------------------
# 5.2 decisions (Karar Günlüğü)
# ---------------------------------------------------------------------------


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    # ondelete="SET NULL" — Transaction silinince NULL olur, Decision kalsın
    transaction_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    date: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    asset_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    rationale: Mapped[str] = mapped_column(String(5000), nullable=True)
    sentiment: Mapped[str] = mapped_column(String(30), nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    ai_retrospective: Mapped[str | None] = mapped_column(String(5000), nullable=True)

    # Navigation
    transaction: Mapped[Transaction | None] = relationship(
        "Transaction", back_populates="decision"
    )
    # Decision silinince ShadowPortfolio'lar da silinir (cascade="delete")
    shadow_portfolios: Mapped[list[ShadowPortfolio]] = relationship(
        "ShadowPortfolio",
        back_populates="decision",
        cascade="delete",
    )


# ---------------------------------------------------------------------------
# 5.3 shadow_portfolios (Gölge Portföy / What-If)
# ---------------------------------------------------------------------------


class ShadowPortfolio(Base):
    __tablename__ = "shadow_portfolios"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    decision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("decisions.id"), nullable=False
    )
    asset_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    simulated_action: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # HELD_INSTEAD, BOUGHT_INSTEAD
    entry_date: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)

    decision: Mapped[Decision] = relationship(
        "Decision", back_populates="shadow_portfolios"
    )


# ---------------------------------------------------------------------------
# 5.4 macro_data (Benchmark & Enflasyon Önbelleği)
# ---------------------------------------------------------------------------


class MacroData(Base):
    __tablename__ = "macro_data"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    gold_try: Mapped[float | None] = mapped_column(Float, nullable=True)
    gold_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    sp500: Mapped[float | None] = mapped_column(Float, nullable=True)
    tr_cpi: Mapped[float | None] = mapped_column(Float, nullable=True)
    us_cpi: Mapped[float | None] = mapped_column(Float, nullable=True)


# ---------------------------------------------------------------------------
# Engine & session
# ---------------------------------------------------------------------------

_engine: create_engine | None = None
_SessionFactory: sessionmaker | None = None


def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    """SQLite connection oluşturulduğunda PRAGMA foreign_keys ve WAL uygula."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
    finally:
        cursor.close()


def get_engine():
    """
    Lazy engine; tek instance boyunca aynı engine kullanılır.
    config.DATABASE_URL kullanılır (DB_NAME kaldırıldı — Prompt 6).
    SQLite için PRAGMA foreign_keys=ON + journal_mode=WAL + check_same_thread=False.
    """
    global _engine
    if _engine is None:
        _engine = create_engine(
            config.DATABASE_URL,
            echo=False,
            connect_args={"check_same_thread": False},
        )
        # SQLite PRAGMA'ları — her yeni connection'da otomatik uygulanır
        event.listen(_engine, "connect", _set_sqlite_pragma)
        # Tabloları oluştur (development; production'da Alembic yönetir)
        Base.metadata.create_all(_engine)
    return _engine


def get_session():
    """Yeni bir session döndürür (her çağrı yeni session)."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory()


def init_db() -> None:
    """
    Uygulama başlangıcında çağrılır (lifespan içinde).
    Engine ve tabloları ensures'ler; gelişmiş kullanımda Alembic
    upgrade head ileSubstitute edilebilir.
    """
    get_engine()
    logger.info("Database ready (DATABASE_URL: %s)", config.DATABASE_URL)
