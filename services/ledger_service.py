"""
FutureWallet – Ledger Servisi (PocketBase)
===========================================
Event-sourced işlem defteri ve portföy snapshot motoru.
PB `transactions` koleksiyonu üzerinde çalışır.
db.py (SQLAlchemy) → pocketbase.py geçişi ile senkronize.

MVP §3.1, TODO 1.3, Prompt 4 (snapshot date), Prompt 8 (ledger düzeltmeleri),
Prompt 9 (time-travel fiyat düzeltmesi).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from services.multi_asset_manager import AssetManager
from services.pocketbase import get_client

# ---------------------------------------------------------------------------
# Tip tanımları
# ---------------------------------------------------------------------------

AssetHolding = dict  # {'asset_symbol': str, 'quantity': float, 'type': str,
#  'average_cost': float, 'total_cost': float, 'value': float}

PortfolioSnapshot = (
    dict  # {'holdings': List[AssetHolding], 'total_value': float, 'as_of_date': str}
)

TimeTravelResult = dict  # {'holdings': List[AssetHolding], 'value_at_start': float,
#  'value_at_target': float, 'pnl': float, 'pnl_pct': float}


# ---------------------------------------------------------------------------
# Yardımcı: PB timestamp string → date
# ---------------------------------------------------------------------------


def _parse_pb_date(value: str | None) -> date | None:
    """PB DateTime string → datetime.date."""
    if not value:
        return None
    try:
        if "T" in value:
            return date.fromisoformat(value.split("T")[0])
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Yardımcı: asset türü tahmini (tek tanım – Prompt 15)
# ---------------------------------------------------------------------------


def _guess_asset_type(symbol: str) -> str:
    """Price fetch için asset türü tahmini."""
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
    if up.endswith("=X") or up.endswith("USD=X"):
        return "forex"
    return "crypto"


# ---------------------------------------------------------------------------
# Yardımcı: Transaction listesinden net pozisyonları hesapla
# ---------------------------------------------------------------------------


def _build_holdings_from_transactions(
    transactions: list[dict],
) -> dict[str, AssetHolding]:
    """PB transactions kayıtları → net pozisyonlar.

    - BUY: quantity × price + fee → average_cost Güncelleme
    - SELL: quantity azaltılır (stok sıfırını aşamaz, aksi takdirde clipped)
    - DIVIDEND: quantity artar (cash received)
    - voided işlemler hariç tutulur.
    """
    holdings: dict[str, AssetHolding] = {}

    for tx in transactions:
        if tx.get("voided", False):
            continue

        sym = tx.get("asset_symbol", "").upper()
        tx_type = tx.get("type", "BUY").upper()
        quantity = float(tx.get("quantity", 0))
        price = float(tx.get("price", 0))
        fee = float(tx.get("fee", 0))

        if tx_type == "BUY":
            if sym not in holdings:
                holdings[sym] = {
                    "asset_symbol": sym,
                    "quantity": 0.0,
                    "type": _guess_asset_type(sym),
                    "average_cost": 0.0,
                    "total_cost": 0.0,
                }
            h = holdings[sym]
            total_cost = quantity * price + fee
            h["total_cost"] += total_cost
            h["quantity"] += quantity
            if h["quantity"] > 0:
                h["average_cost"] = h["total_cost"] / h["quantity"]

        elif tx_type == "SELL":
            if sym in holdings:
                holdings[sym]["quantity"] = max(
                    0.0, holdings[sym]["quantity"] - quantity
                )
                holdings[sym]["total_cost"] = (
                    holdings[sym]["quantity"] * holdings[sym]["average_cost"]
                )

        elif tx_type == "DIVIDEND":
            if sym not in holdings:
                holdings[sym] = {
                    "asset_symbol": sym,
                    "quantity": 0.0,
                    "type": "cash",
                    "total_cost": 0.0,
                }
            holdings[sym]["quantity"] += quantity

        # CASH_IN / CASH_OUT → portfolio tutarını etkiler ama holding yapısı ayrı

    return holdings


# ---------------------------------------------------------------------------
# Yardımcı: belirtilen tarihteki holdings'leri PB transactions'dan hesapla
# ---------------------------------------------------------------------------


def _get_holdings_at_date(user_id: str, as_of: date) -> dict[str, AssetHolding]:
    """Belirtilen tarihteki holdings'leri PB transactions collection'undan hesapla.

    as_of + 1 gün (00:00) → o günün işlemleri dahil (Prompt 8 düzeltmesi).
    """
    as_of_end = as_of + timedelta(days=1)

    client = get_client()
    try:
        transactions = client.collection("transactions")
        records = transactions.get_list(
            params=(
                f"filter="
                f"user='{user_id}'"
                f" AND timestamp<='{as_of_end.isoformat()}'"
                f"&per_page=1000"
            )
        )
    except Exception:
        records = []

    return _build_holdings_from_transactions(records)


# ---------------------------------------------------------------------------
# 1. get_portfolio_snapshot (Prompt 4, 8)
# ---------------------------------------------------------------------------


def get_portfolio_snapshot(
    user_id: str,
    as_of: date | None = None,
    price_fn: Callable[[str, str], float | None] | None = None,
) -> PortfolioSnapshot:
    """Kullanıcının portföy snapshot'ı.

    as_of: snapshot tarihi. None → bugün.
    price_fn: (symbol, asset_type) → Optional[float]. None → AssetManager default.

    Snapshot mantığı:
      - timestamp < as_of + 1 gün → o günün işlemleri dahil (Prompt 8).
      - voided işlemler hariç.
      - DIVIDEND → cash_received olarak görünür ( holdings['quantity'] ).
    """
    if as_of is None:
        as_of = date.today()

    holdings = _get_holdings_at_date(user_id, as_of)

    if price_fn is None:
        mgr = AssetManager()
        price_fn = lambda sym, atype: mgr.get_price(sym, atype)

    total_value = 0.0
    total_cost = 0.0
    for sym, h in holdings.items():
        atype = h.get("type", _guess_asset_type(sym))
        p = price_fn(sym, atype)
        if p is not None:
            h["value"] = h["quantity"] * p
            total_value += h["value"]
            # Unrealized P/L hesapla
            if h.get("average_cost", 0) > 0 and h["quantity"] > 0:
                h["unrealized_pnl"] = (p - h["average_cost"]) * h["quantity"]
                h["unrealized_pnl_pct"] = ((p - h["average_cost"]) / h["average_cost"]) * 100
            else:
                h["unrealized_pnl"] = 0.0
                h["unrealized_pnl_pct"] = 0.0
        else:
            h["value"] = 0.0
            h["unrealized_pnl"] = 0.0
            h["unrealized_pnl_pct"] = 0.0
        h.setdefault("average_cost", 0.0)
        h.setdefault("total_cost", 0.0)
        total_cost += h.get("total_cost", 0.0)

    # Toplam average cost
    total_avg_cost = total_cost / total_value if total_value > 0 else 0.0

    return {
        "holdings": list(holdings.values()),
        "total_value": total_value,
        "total_cost": total_cost,
        "average_cost": total_avg_cost,
        "unrealized_pnl": total_value - total_cost,
        "unrealized_pnl_pct": ((total_value - total_cost) / total_cost * 100) if total_cost > 0 else 0.0,
        "as_of_date": as_of.isoformat(),
    }


# ---------------------------------------------------------------------------
# 2. time_travel_portfolio (Prompt 9 – düzeltme: T_start ve T_target fiyat farkı)
# ---------------------------------------------------------------------------


def time_travel_portfolio(
    user_id: str,
    t_start: date,
    t_target: date,
    price_fn: Callable[[str, str, date], Optional[float]] | None = None,
) -> TimeTravelResult:
    """T_start dağılımını T_target fiyatlarıyla değerlendirir.

    Sabit dağılım ("satmasaydım" mantığı):
      - start_holdings = snapshot(t_start) miktarları
      - value_at_start = start_holdings × fiyat(t_start)  ← GARİŞİK fiyat
      - value_at_target = AYNI start_holdings × fiyat(t_target)  ← GARİŞİK fiyat
      - actual_value_at_target = snapshot(t_target) (işlemler dahil)

    Args:
        user_id: Kullanıcı ID
        t_start: Başlangıç tarihi
        t_target: Hedef tarih
        price_fn: (symbol, asset_type, date) -> Optional[float].
                  None ise price_service.get_price_on kullanılır.

    Returns:
        {
            "holdings": [...],
            "value_at_start": float,
            "value_at_target": float,
            "value_at_actual": float,
            "pnl": float,
            "pnl_pct": float,
            "missing_prices": [str,...],  # fiyat bulunamayan semboller
        }
    """
    # price_fn yoksa price_service kullan
    if price_fn is None:
        from services.price_service import get_price_on, guess_asset_type as ps_guess

        def _default_price_fn(sym: str, atype: str, ref_date: date) -> Optional[float]:
            return get_price_on(sym, atype or ps_guess(sym), ref_date)

        price_fn = _default_price_fn

    start_holdings = _get_holdings_at_date(user_id, t_start)

    missing_prices: list[str] = []

    def _value_at(holdings: dict[str, AssetHolding], ref_date: date) -> float:
        total = 0.0
        for sym, h in holdings.items():
            atype = h.get("type", _guess_asset_type(sym))
            p = price_fn(sym, atype, ref_date)
            if p is not None:
                total += h["quantity"] * p
            else:
                missing_prices.append(sym)
        return total

    value_at_start = _value_at(start_holdings, t_start)
    value_at_target = _value_at(start_holdings, t_target)

    # actual: t_target anındaki gerçek snapshot (işlemler dahil)
    actual_holdings = _get_holdings_at_date(user_id, t_target)
    actual_value = _value_at(actual_holdings, t_target)

    pnl = value_at_target - value_at_start
    pnl_pct = (pnl / value_at_start * 100) if value_at_start > 0 else 0

    return {
        "holdings": list(start_holdings.values()),
        "value_at_start": value_at_start,
        "value_at_target": value_at_target,
        "actual_value_at_target": actual_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
    }


# ---------------------------------------------------------------------------
# 3. add_transaction (Prompt 8 – event log kaydı)
# ---------------------------------------------------------------------------


def add_transaction(
    user_id: str,
    asset_symbol: str,
    tx_type: str,
    quantity: float,
    price: float,
    fee: float = 0.0,
    timestamp: date | None = None,
) -> dict:
    """Yeni bir işlem kaydı ekler (event log'a yaz).

    Returns:
        Yeni transaction dict.
    """
    if timestamp is None:
        timestamp = date.today()

    tx_type_upper = tx_type.upper()
    if tx_type_upper not in {"BUY", "SELL", "DIVIDEND", "CASH_IN", "CASH_OUT"}:
        raise ValueError(
            f"tx_type: {tx_type!r} — allowed: BUY, SELL, DIVIDEND, CASH_IN, CASH_OUT"
        )

    asset_symbol_upper = asset_symbol.upper()

    client = get_client()
    transactions = client.collection("transactions")

    data = {
        "user": user_id,
        "asset_symbol": asset_symbol_upper,
        "type": tx_type_upper,
        "quantity": quantity,
        "price": price,
        "fee": fee,
        "timestamp": timestamp.isoformat(),
        "voided": False,
    }

    record = transactions.create(data)

    return {
        "id": record.id,
        "user": user_id,
        "asset_symbol": asset_symbol_upper,
        "type": tx_type_upper,
        "quantity": quantity,
        "price": price,
        "fee": fee,
        "timestamp": timestamp.isoformat(),
        "voided": False,
    }


#
#
# ---------------------------------------------------------------------------
# 4. get_transactions (Prompt 8 – filtreli işlem listesi)
# ---------------------------------------------------------------------------


def get_transactions(
    user_id: str,
    asset_symbol: str | None = None,
    tx_type: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Kullanıcının işlem listesi (filtrelenmiş).

    PB transactions collection'undan okur; voided işlemler DÃ¡HIL'dÄ±r.
    """
    client = get_client()
    transactions = client.collection("transactions")
    filter_parts = [f'user = "{user_id}"']
    if asset_symbol is not None:
        filter_parts.append(f'asset_symbol = "{asset_symbol.upper()}"')
    if tx_type is not None:
        filter_parts.append(f'type = "{tx_type.upper()}"')
    filter_str = " AND ".join(filter_parts)
    params = (
        f"filter={filter_str}&sort=timestamp DESC&per_page={limit if limit else 100}"
    )
    records = transactions.get_list(params=params)
    return [
        {
            "id": r.id,
            "user": r.user,
            "asset_symbol": r.asset_symbol,
            "type": r.type,
            "quantity": r.quantity,
            "price": r.price,
            "fee": r.fee,
            "timestamp": r.timestamp,
            "voided": r.voided,
        }
        for r in records
    ]


def void_transaction(
    user_id: str,
    transaction_id: str,
) -> dict:
    """İşlem kaydını voided yap (soft delete).

    Sadece kendi kullanıcısının işlemini void edebilir.
    """
    client = get_client()
    transactions = client.collection("transactions")
    record = transactions.get(transaction_id)
    if record.user != user_id:
        raise ValueError("Yetkisiz: bu işlem pasaportunuzda değil")
    record.voided = True
    transactions.update(record)
    return {"status": "voided", "transaction_id": transaction_id}
