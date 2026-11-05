"""
FutureWallet - Database Models & Session (SQLAlchemy)

Kullanım:
- Production: PocketBase (services/pocketbase.py) kullanılır
- Testler: SQLAlchemy + SQLite in-memory (tests/conftest.py)

NOT: Production kodda bu modeller kullanılmıyor, sadece test 인프라 için.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

import config

logger = __import__("logging").getLogger(__name__)

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

    id: Any = Column(String(36), primary_key=True)
    user: Any = Column(String(255), nullable=False)
    asset_symbol: Any = Column(String(20), nullable=False)
    type: Any = Column(String(20), nullable=False)  # BUY, SELL, DIVIDEND, CASH_IN, CASH_OUT
    quantity: Any = Column(Float, nullable=False)
    price: Any = Column(Float, nullable=False)
    fee: Any = Column(Float, nullable=True)
    timestamp: Any = Column(DateTime, nullable=False, server_default=func.now())
    voided: Any = Column(Boolean, nullable=False, default=False)


# ---------------------------------------------------------------------------
# 5.2 decisions (Karar Günlüğü)
# ---------------------------------------------------------------------------


class Decision(Base):
    __tablename__ = "decisions"

    id: Any = Column(String(36), primary_key=True)
    user: Any = Column(String(255), nullable=False)
    asset_symbol: Any = Column(String(20), nullable=False)
    action: Any = Column(String(10), nullable=False)  # BUY, SELL, HOLD
    sentiment: Any = Column(String(20), nullable=True)
    rationale: Any = Column(Text, nullable=True)
    target_price: Any = Column(Float, nullable=True)
    target_date: Any = Column(Date, nullable=True)
    status: Any = Column(String(20), nullable=False, default="OPEN")  # OPEN, EXPIRED, REVIEWED, CLOSED
    decision_date: Any = Column(Date, nullable=False, default=func.current_date())
    ai_retrospective: Any = Column(Text, nullable=True)


# ---------------------------------------------------------------------------
# 5.3 shadow_portfolios (Gölge Portföy / What-If)
# ---------------------------------------------------------------------------


class ShadowPortfolio(Base):
    __tablename__ = "shadow_portfolios"

    id: Any = Column(String(36), primary_key=True)
    decision_id: Any = Column(String(36), nullable=False)
    user: Any = Column(String(255), nullable=False)
    asset_symbol: Any = Column(String(20), nullable=False)
    shadow_type: Any = Column(String(20), nullable=False)  # HELD_INSTEAD, BOUGHT_INSTEAD
    entry_price: Any = Column(Float, nullable=False)
    quantity: Any = Column(Float, nullable=False)
    entry_date: Any = Column(Date, nullable=False)
    exit_date: Any = Column(Date, nullable=True)
    asset_type: Any = Column(String(20), nullable=True)


# ---------------------------------------------------------------------------
# 5.4 macro_data (Benchmark & Enflasyon Önbelleği)
# ---------------------------------------------------------------------------


class MacroData(Base):
    __tablename__ = "macro_data"

    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    date: Any = Column(DateTime, nullable=False)
    user: Any = Column(String(255), nullable=True)
    gold_usd: Any = Column(Float, nullable=True)
    gold_try_gram: Any = Column(Float, nullable=True)
    sp500: Any = Column(Float, nullable=True)
    tr_cpi: Any = Column(Float, nullable=True)
    us_cpi: Any = Column(Float, nullable=True)
    source: Any = Column(String(50), nullable=True)
    is_estimate: Any = Column(Boolean, nullable=True, default=False)


# ---------------------------------------------------------------------------
# Engine & session
# ---------------------------------------------------------------------------

_engine: Any = None
_SessionFactory: Any = None


def _set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
    """SQLite connection oluşturulduğunda PRAGMA foreign_keys ve WAL uygula."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def get_engine() -> Any:
    """Global engine oluştur (lazy singleton)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            config.DATABASE_URL,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
        _engine.raw_connection().connection.add_callback(_set_sqlite_pragma)
    return _engine


def get_session() -> Any:
    """Yeni bir session döndürür (her çağrı yeni session)."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory()


def init_db() -> None:
    """Uygulama başlangıcında çağrılır (lifespan içinde)."""
    get_engine()
    logger.info("Database ready (DATABASE_URL: %s)", config.DATABASE_URL)
