"""
FutureWallet - SQLAlchemy 2.0 Veritabanı Modelleri

Event-Sourcing üzerinden tüm işlemler zaman damgalı olarak saklanır.
"""

from datetime import datetime, date
from uuid import uuid4
from sqlalchemy import (
    create_engine,
    String,
    Float,
    DateTime,
    Date,
    ForeignKey,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.sql import functions as sql_functions


DB_NAME = "futurewallet.db"


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# 5.1 transactions (İşlem Defteri / Event Sourcing Ledger)
# ---------------------------------------------------------------------------

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=sql_functions.now(), nullable=False)
    asset_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY, SELL, DIVIDEND, CASH_IN, CASH_OUT
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, default=0.0)

    # Navigation
    decision = relationship("Decision", back_populates="transaction", uselist=False, cascade="delete")


# ---------------------------------------------------------------------------
# 5.2 decisions (Karar Günlüğü)
# ---------------------------------------------------------------------------

class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    transaction_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("transactions.id"), nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime, server_default=sql_functions.now(), nullable=False)
    asset_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)        # BUY, SELL, HOLD
    rationale: Mapped[str] = mapped_column(String(5000), nullable=True)   # Metin alanı
    sentiment: Mapped[str] = mapped_column(String(30), nullable=True)     # FOMO, STRATEGIC, PANIC, DIVIDEND
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")       # OPEN, REVIEWED, EXPIRED
    ai_retrospective: Mapped[str | None] = mapped_column(String(5000), nullable=True)

    transaction: Mapped[Transaction | None] = relationship("Transaction", back_populates="decision")
    shadow_portfolios: Mapped[list["ShadowPortfolio"]] = relationship(
        "ShadowPortfolio", back_populates="decision", cascade="delete"
    )


# ---------------------------------------------------------------------------
# 5.3 shadow_portfolios (Gölge Portföy / What-If)
# ---------------------------------------------------------------------------

class ShadowPortfolio(Base):
    __tablename__ = "shadow_portfolios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    decision_id: Mapped[str] = mapped_column(String(36), ForeignKey("decisions.id"), nullable=False)
    asset_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    simulated_action: Mapped[str] = mapped_column(String(20), nullable=False)  # HELD_INSTEAD, BOUGHT_INSTEAD
    entry_date: Mapped[datetime] = mapped_column(DateTime, server_default=sql_functions.now(), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)

    decision: Mapped[Decision] = relationship("Decision", back_populates="shadow_portfolios")


# ---------------------------------------------------------------------------
# 5.4 macro_data (Benchmark & Enflasyon Önbelleği)
# ---------------------------------------------------------------------------

class MacroData(Base):
    __tablename__ = "macro_data"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    gold_try: Mapped[float | None] = mapped_column(Float, nullable=True)
    gold_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    sp500: Mapped[float | None] = mapped_column(Float, nullable=True)
    tr_cpi: Mapped[float | None] = mapped_column(Float, nullable=True)   # TÜİK TÜFE Endeksi
    us_cpi: Mapped[float | None] = mapped_column(Float, nullable=True)   # US CPI Endeksi


# ---------------------------------------------------------------------------
# Engine & session
# ---------------------------------------------------------------------------

_engine = None
_SessionFactory = None


def get_engine():
    """Lazy engine; tek instance boyunca same engine used."""
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{DB_NAME}", echo=False)
        Base.metadata.create_all(_engine)
    return _engine


def get_session():
    """Yeni bir session döndürür."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory()


def init_db():
    """DB dosyasını oluşturur (zorunlu değil — get_engine() otomatik yapar)."""
    get_engine()
    print(f"[db] Database ready: {DB_NAME}")
