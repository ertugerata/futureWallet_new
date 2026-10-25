"""
FutureWallet - Ledger & Time-Travel Servisi

Event-sourced transaction ledger üzerinden:
  - Belirli bir tarihteki portföy snapshot'ı (net pozisyonlar)
  - Time-Travel: T_start dagıtımını T_target fiyatlarıyla değerleme

MVP §3.1, TODO 1.3.
"""

from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from db import Transaction
from services.multi_asset_manager import AssetManager


# ---------------------------------------------------------------------------
# Tip aliases
# ---------------------------------------------------------------------------

AssetHolding = Dict  # {'asset_symbol': str, 'quantity': float, 'type': str}
PortfolioSnapshot = Dict  # {'holdings': List[AssetHolding], 'total_value': float, 'as_of_date': str}
TimeTravelResult = Dict  # {'holdings': List[AssetHolding], 'value_at_target': float,
                          #  'value_at_start': float, 'pnl': float, 'pnl_pct': float}


# ---------------------------------------------------------------------------
# Yardımcı: Transaction listesinden net pozisyonları hesapla
# ---------------------------------------------------------------------------

def _build_holdings_from_transactions(
    transactions: Sequence[Transaction],
) -> Dict[str, AssetHolding]:
    """
    Transaction listesini tek tek okuyup her asset için net quantity'yi
    hesaplar.

    Event türleri:
      BUY        → quantity ekle
      SELL       → quantity düşür
      DIVIDEND   → cash inflow (quantity değişmez)
      CASH_IN    → nakit eklenir (USDT/TRY gibi cash symbol'ları)
      CASH_OUT   → nakit düşer
    """

    net: Dict[str, float] = {}
    CASH_SYMBOLS = frozenset({"USDT", "USD", "TRY", "TL", "EUR", "GBP"})

    for tx in transactions:
        sym = tx.asset_symbol
        evt = tx.type.upper()

        if evt == "BUY":
            net[sym] = net.get(sym, 0.0) + tx.quantity
        elif evt == "SELL":
            net[sym] = net.get(sym, 0.0) - tx.quantity
        elif evt in ("DIVIDEND", "CASH_IN"):
            # Nakit/inflow — sadece cash symbol'ları için quantity olarak carrier
            if sym.upper() in CASH_SYMBOLS:
                net[sym] = net.get(sym, 0.0) + tx.quantity
            # Diğer asset'ler için dividend'ler MVP'de ayrı değerleme ile handled
        elif evt == "CASH_OUT":
            if sym.upper() in CASH_SYMBOLS:
                net[sym] = net.get(sym, 0.0) - tx.quantity
        # Tanımsız event türü: carrier etme (logla ilerde)

    holdings: Dict[str, AssetHolding] = {}
    for sym, qty in net.items():
        if qty == 0.0:
            continue
        holdings[sym] = {
            "asset_symbol": sym,
            "quantity": qty,
            "type": _guess_asset_type(sym),
        }

    return holdings


def _guess_asset_type(symbol: str) -> str:
    """
    Placeholder: sembolden asset türünü tahmin et.
    Gerçek implementation'da AssetManager veya explicit mapping kullanılır.
    """
    cash = frozenset({"USDT", "USD", "TRY", "TL", "EUR", "GBP"})
    gold = frozenset({"GC=F", "XAU", "GOLD"})

    up = symbol.upper()
    if up in cash:
        return "cash"
    if up in gold or "GOLD" in up or "ALTIN" in up:
        return "commodity"
    if ".IS" in up or up in ("THYAO", "GARAN", "ASELS", "TUPRS", "SISE"):
        return "stock_tr"
    if "^GSPC" in up:
        return "stock_us"
    return "crypto"  # conservative default


# ---------------------------------------------------------------------------
# Fiyat çekme abstraction'ı
# ---------------------------------------------------------------------------

def _default_price_fn(symbol: str, asset_type: str) -> Optional[float]:
    """
    Default price fonksiyonu: AssetManager kullanarak güncel fiyat çeker.
    Time-Travel MVP'sinde T_target fiyatı approximation olarak güncel fiyat
    kullanılır. Gerçek historical price source (benchmark_service) gelince
    bu fonksiyon değiştirilecek / inject edilecek.
    """
    mgr = AssetManager()
    return mgr.get_price(symbol, asset_type)


# ---------------------------------------------------------------------------
# 1. get_portfolio_snapshot
# ---------------------------------------------------------------------------

def get_portfolio_snapshot(
    session: Session,
    as_of: Optional[date] = None,
    price_fn: Optional[Callable[[str, str], Optional[float]]] = None,
) -> PortfolioSnapshot:
    """
    Belirtilen tarihteki portföy snapshot'ını döndürür.

    Tabele OLGU:
      - as_of'daki net pozisyonlar (event log'lar kadar)
      - her pozisyonun as_of'taki (veya güncel) fiyatla değeri
      - toplam portföy değeri

    Args:
        session: SQLAlchemy Session
        as_of: Snapshot tarihi. None → bugün (today).
        price_fn: (symbol, type) → price. None → default AssetManager.

    Returns:
        {
            "holdings": [
                {"asset_symbol": "BTC", "quantity": 0.5,  "type": "crypto", "value": 15000.0},
                {"asset_symbol": "USDT", "quantity": 1000.0, "type": "cash", "value": 1000.0},
            ],
            "total_value": 16000.0,
            "as_of_date": "2024-01-15",
        }
    """
    if price_fn is None:
        price_fn = _default_price_fn

    if as_of is None:
        as_of = date.today()

    as_of_dt = datetime.combine(as_of, datetime.min.time())

    # as_of'a kadar olan tüm transaction'lar (timestamp <= as_of)
    stmt = select(Transaction).where(Transaction.timestamp <= as_of_dt).order_by(Transaction.timestamp)
    txs = session.execute(stmt).scalars().all()

    holdings_map = _build_holdings_from_transactions(txs)

    holdings: List[AssetHolding] = []
    total = 0.0

    for sym, h in holdings_map.items():
        atype = h["type"]
        qty = h["quantity"]

        if atype == "cash":
            value = qty  # cash symbol'ları face value
        else:
            p = price_fn(sym, atype)
            value = qty * (p if p is not None else 0.0)

        holdings.append({
            "asset_symbol": sym,
            "quantity": qty,
            "type": atype,
            "value": round(value, 2),
        })
        total += value

    return {
        "holdings": holdings,
        "total_value": round(total, 2),
        "as_of_date": as_of.isoformat(),
    }


# ---------------------------------------------------------------------------
# 2. time_travel_portfolio
# ---------------------------------------------------------------------------

def time_travel_portfolio(
    session: Session,
    t_start: date,
    t_target: date,
    price_fn: Optional[Callable[[str, str], Optional[float]]] = None,
) -> TimeTravelResult:
    """
    T_start tarihindeki portföy dagıtımını, T_target tarihindeki fiyatlarla
    değerlendirir ve P&L raporu döndürür.

    SENARYO:
      - "1 Ocak 2023'te ne almış olsaydım, bugün ne durumdaydım?"
      - "Son 6 ayda portföyümün nominal değişimi ne?"

    Args:
        session: SQLAlchemy Session
        t_start:   Başlangıç tarihi (dagıtım buradan snap'lenir)
        t_target:  Değerleme tarihi (fiyatlar buradan alınır)
        price_fn:  (symbol, type) → price. None → default AssetManager.

    Returns:
        {
            "holdings": [
                {"asset_symbol": "BTC", "quantity": 0.5, "type": "crypto",
                 "value_at_start": 12000.0, "value_at_target": 25000.0},
                ...
            ],
            "value_at_start":   15000.0,  # T_start fiyatlarıyla
            "value_at_target":  30000.0,  # T_target fiyatlarıyla
            "pnl":              15000.0,
            "pnl_pct":          1.0,      # +100%
        }
    """
    if price_fn is None:
        price_fn = _default_price_fn

    # T_start snapshot'ı (dagıtım)
    start_snapshot = get_portfolio_snapshot(session, as_of=t_start, price_fn=price_fn)
    # T_target snapshot'ı (fiyatlar için, dagıtım aynı)
    target_snapshot = get_portfolio_snapshot(session, as_of=t_target, price_fn=price_fn)

    # Her asset için T_start ve T_target değerlerini karşılaştır
    # Not: quantity aynı (snapshot'lar aynı dagıtımı temsil ediyor)
    start_by_sym = {h["asset_symbol"]: h["value"] for h in start_snapshot["holdings"]}
    target_by_sym = {h["asset_symbol"]: h["value"] for h in target_snapshot["holdings"]}

    # Tüm symbol'ları birleştir
    all_syms = set(start_by_sym.keys()) | set(target_by_sym.keys())

    holdings: List[AssetHolding] = []
    value_at_start = 0.0
    value_at_target = 0.0

    for sym in sorted(all_syms):
        v_start = start_by_sym.get(sym, 0.0)
        v_target = target_by_sym.get(sym, 0.0)

        # quantity'yi target snapshot'ından al (hemen tersi de çalışır)
        qty = next((h["quantity"] for h in target_snapshot["holdings"] if h["asset_symbol"] == sym), 0.0)
        atype = next((h["type"] for h in target_snapshot["holdings"] if h["asset_symbol"] == sym), "crypto")

        holdings.append({
            "asset_symbol": sym,
            "quantity": qty,
            "type": atype,
            "value_at_start": round(v_start, 2),
            "value_at_target": round(v_target, 2),
        })

        value_at_start += v_start
        value_at_target += v_target

    pnl = value_at_target - value_at_start
    pnl_pct = (pnl / value_at_start) if value_at_start > 0 else 0.0

    return {
        "holdings": holdings,
        "value_at_start": round(value_at_start, 2),
        "value_at_target": round(value_at_target, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 4),
    }


# ---------------------------------------------------------------------------
# Yardımcı: portföy için transaction eklemek (event log'a yaz)
# ---------------------------------------------------------------------------

def add_transaction(
    session: Session,
    asset_symbol: str,
    type: str,           # BUY | SELL | DIVIDEND | CASH_IN | CASH_OUT
    quantity: float,
    price: float,
    fee: float = 0.0,
    when: Optional[date] = None,
) -> Transaction:
    """
    Yeni bir event log kaydı ekler.

    Args:
        session: SQLAlchemy Session
        asset_symbol: Varlık sembolü
        type: Event türü (BUY, SELL, DIVIDEND, CASH_IN, CASH_OUT)
        quantity: Alınan/satılan miktarı (BUY/SELL'de pozitif)
        price: İşlem fiyatı (birim başına)
        fee: İşlem ücreti
        when: İşlem tarihi. None → şimdi (server_default).
              Test senaryolarında geçmiş tarih vererek time-travel testleri yapılır.

    Returns:
        Yeni Transaction nesnesi (session.commit() çağrılmamış — çağranan sorumlu)
    """
    tx = Transaction(
        asset_symbol=asset_symbol,
        type=type.upper(),
        quantity=quantity,
        price=price,
        fee=fee,
        timestamp=datetime.combine(when, datetime.min.time()) if when is not None else None,
    )
    session.add(tx)
    return tx
