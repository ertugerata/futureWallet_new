"""
FutureWallet – Event-Sourcing İşlem ve Snapshot Motoru (PocketBase)
====================================================================
Kullanıcının tüm alım, satım, temettü ve nakit akışı işlemlerini PocketBase
`transactions` koleksiyonunda saklar ve tarihsel portföy snapshot'larını
hesaplar.

Prompt 5, 7, 9 ile uyumlu hale getirilmiştir.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from services.enums import TransactionType
from services.multi_asset_manager import AssetManager
from services.pb import get_client

logger = logging.getLogger(__name__)

# Kullanıcı bazlı concurrency kilidi
_user_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


class InsufficientBalanceError(Exception):
    """Yetersiz bakiye veya stok hatası (HTTP 409 Conflict)."""


# ---------------------------------------------------------------------------
# Tip tanımları
# ---------------------------------------------------------------------------

AssetHolding = dict  # {'asset_symbol': str, 'quantity': float, 'type': str, 'average_cost': float}
PortfolioSnapshot = dict  # {'as_of': str, 'holdings': List[Dict], 'total_value': float, 'total_cost': float, 'pnl': float, 'pnl_pct': float}
TimeTravelResult = dict  # {'t_start': str, 't_target': str, 'holdings': List[Dict], 'value_at_start': float, 'value_at_target': float, 'pnl': float, 'pnl_pct': float}


def _tx_get(tx: Any, key: str, default: Any = None) -> Any:
    """PB Record veya dict nesnesinden alan okur."""
    if isinstance(tx, dict):
        return tx.get(key, default)
    return getattr(tx, key, default)


def _guess_asset_type(symbol: str) -> str:
    """Sembol adına göre varlık türü tahmini."""
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


def _build_holdings_from_transactions(
    transactions: list[Any],
) -> dict[str, AssetHolding]:
    """PB transactions kayıtları → net pozisyonlar."""
    holdings: dict[str, AssetHolding] = {}

    for tx in transactions:
        if _tx_get(tx, "voided", False):
            continue

        sym = str(_tx_get(tx, "asset_symbol", "")).upper()
        tx_type = str(_tx_get(tx, "type", "BUY")).upper()
        quantity = float(_tx_get(tx, "quantity", 0) or 0)
        price = float(_tx_get(tx, "price", 0) or 0)
        fee = float(_tx_get(tx, "fee", 0) or 0)

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
            cost_basis = quantity * price + fee
            h["total_cost"] += cost_basis
            h["quantity"] += quantity
            if h["quantity"] > 0:
                h["average_cost"] = h["total_cost"] / h["quantity"]

        elif tx_type == "SELL":
            if sym in holdings:
                holdings[sym]["quantity"] = max(0.0, holdings[sym]["quantity"] - quantity)
                holdings[sym]["total_cost"] = (
                    holdings[sym]["quantity"] * holdings[sym]["average_cost"]
                )

        elif tx_type == "DIVIDEND":
            # Temettü: nakit akışı veya gelir
            if sym not in holdings:
                holdings[sym] = {
                    "asset_symbol": sym,
                    "quantity": 0.0,
                    "type": "cash",
                    "total_cost": 0.0,
                    "average_cost": 0.0,
                }
            holdings[sym]["quantity"] += quantity

    return holdings


def _get_holdings_at_date(user_id: str, as_of: date) -> dict[str, AssetHolding]:
    """Belirtilen tarihteki holdings'leri PB transactions collection'undan hesapla."""
    as_of_end = as_of + timedelta(days=1)
    as_of_str = as_of_end.isoformat() + " 00:00:00.000Z"

    client = get_client()
    transactions = client.collection("transactions")
    filter_expr = f'user = "{user_id}" && timestamp <= "{as_of_str}" && voided = false'

    try:
        records = transactions.get_full_list(query_params={"filter": filter_expr})
    except Exception as exc:
        logger.warning("Transactions okunurken hata (filtre: %s): %s", filter_expr, exc)
        # Eğer datetime formatı uyuşmazsa yedek sorgu
        records = transactions.get_full_list(query_params={"filter": f'user = "{user_id}" && voided = false'})
        # Python tarafında tarih filtresi uygula
        filtered = []
        for r in records:
            ts_str = str(getattr(r, "timestamp", ""))
            try:
                ts_date = date.fromisoformat(ts_str.split("T", maxsplit=1)[0].split(" ", maxsplit=1)[0])
                if ts_date <= as_of:
                    filtered.append(r)
            except Exception:
                pass
        records = filtered

    return _build_holdings_from_transactions(records)


# ---------------------------------------------------------------------------
# 1. get_portfolio_snapshot
# ---------------------------------------------------------------------------


def get_portfolio_snapshot(
    user_id: str,
    as_of: date | None = None,
    price_fn: Callable[[str, str], float | None] | None = None,
) -> PortfolioSnapshot:
    """Kullanıcının portföy snapshot'ı."""
    if as_of is None:
        as_of = date.today()

    holdings = _get_holdings_at_date(user_id, as_of)

    if price_fn is None:
        mgr = AssetManager()
        price_fn = lambda sym, atype: mgr.get_price(sym, atype)

    total_value = 0.0
    total_cost = 0.0
    holdings_list = []

    for sym, h in holdings.items():
        qty = h["quantity"]
        if qty <= 0:
            continue
        atype = h.get("type", _guess_asset_type(sym))
        current_price = price_fn(sym, atype) or 0.0
        val = qty * current_price
        cost = h.get("total_cost", 0.0)
        unrealized_pnl = val - cost
        unrealized_pnl_pct = (unrealized_pnl / cost * 100.0) if cost > 0 else 0.0

        total_value += val
        total_cost += cost
        holdings_list.append(
            {
                "asset_symbol": sym,
                "quantity": qty,
                "current_price": current_price,
                "current_value": val,
                "average_cost": h.get("average_cost", 0.0),
                "total_cost": cost,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "type": atype,
            }
        )

    pnl = total_value - total_cost
    pnl_pct = (pnl / total_cost * 100.0) if total_cost > 0 else 0.0

    return {
        "as_of": as_of.isoformat(),
        "holdings": holdings_list,
        "total_value": total_value,
        "total_cost": total_cost,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
    }


# ---------------------------------------------------------------------------
# 2. time_travel_portfolio
# ---------------------------------------------------------------------------


def time_travel_portfolio(
    user_id: str,
    t_start: date,
    t_target: date,
    price_fn: Callable[[str, str, date], float | None] | None = None,
) -> TimeTravelResult:
    """T_start pozisyonlarını T_target fiyatlarıyla değerler."""
    start_holdings = _get_holdings_at_date(user_id, t_start)

    if price_fn is None:
        from services.price_service import get_price_on
        price_fn = lambda sym, atype, dt: get_price_on(sym, atype, dt)

    value_at_start = 0.0
    value_at_target = 0.0
    result_holdings = []

    for sym, h in start_holdings.items():
        qty = h["quantity"]
        if qty <= 0:
            continue
        atype = h.get("type", _guess_asset_type(sym))
        p_start = price_fn(sym, atype, t_start) or 0.0
        p_target = price_fn(sym, atype, t_target) or 0.0

        v_start = qty * p_start
        v_target = qty * p_target

        value_at_start += v_start
        value_at_target += v_target

        result_holdings.append(
            {
                "asset_symbol": sym,
                "quantity": qty,
                "price_at_start": p_start,
                "price_at_target": p_target,
                "value_at_start": v_start,
                "value_at_target": v_target,
                "pnl": v_target - v_start,
                "pnl_pct": ((v_target - v_start) / v_start * 100.0) if v_start > 0 else 0.0,
            }
        )

    pnl = value_at_target - value_at_start
    pnl_pct = (pnl / value_at_start * 100.0) if value_at_start > 0 else 0.0

    return {
        "t_start": t_start.isoformat(),
        "t_target": t_target.isoformat(),
        "holdings": result_holdings,
        "value_at_start": value_at_start,
        "value_at_target": value_at_target,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
    }


# ---------------------------------------------------------------------------
# 3. add_transaction (Yetersiz bakiye & Stok kilit kontrolü, Prompt 7)
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
    """Yeni bir işlem kaydı ekler (event log). SELL işleminde stok kontrolü yapar."""
    if timestamp is None:
        timestamp = date.today()

    tx_type_upper = tx_type.upper()
    allowed = {t.value for t in TransactionType}
    if tx_type_upper not in allowed:
        raise ValueError(f"tx_type: {tx_type!r} — allowed: {allowed}")

    asset_symbol_upper = asset_symbol.upper()

    with _user_locks[user_id]:
        if tx_type_upper == "SELL":
            current_holdings = _get_holdings_at_date(user_id, timestamp)
            current_qty = current_holdings.get(asset_symbol_upper, {}).get("quantity", 0.0)
            if quantity > current_qty:
                raise InsufficientBalanceError(
                    f"Yetersiz stok: {asset_symbol_upper} eldeki miktar={current_qty}, satılmak istenen={quantity}"
                )

        client = get_client()
        transactions = client.collection("transactions")

        # ISO format tarih
        ts_str = f"{timestamp.isoformat()} 00:00:00.000Z"

        data = {
            "user": user_id,
            "asset_symbol": asset_symbol_upper,
            "type": tx_type_upper,
            "quantity": quantity,
            "price": price,
            "fee": fee,
            "timestamp": ts_str,
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
            "timestamp": ts_str,
            "voided": False,
        }


# ---------------------------------------------------------------------------
# 4. get_transactions
# ---------------------------------------------------------------------------


def get_transactions(
    user_id: str,
    asset_symbol: str | None = None,
    tx_type: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Kullanıcının işlem listesi (filtrelenmiş)."""
    client = get_client()
    transactions = client.collection("transactions")

    filter_parts = [f'user = "{user_id}"']
    if asset_symbol is not None:
        filter_parts.append(f'asset_symbol = "{asset_symbol.upper()}"')
    if tx_type is not None:
        filter_parts.append(f'type = "{tx_type.upper()}"')

    filter_str = " && ".join(filter_parts)
    query_params: dict[str, Any] = {"filter": filter_str, "sort": "-timestamp"}

    if limit is not None:
        records = transactions.get_list(page=1, per_page=limit, query_params=query_params).items
    else:
        records = transactions.get_full_list(query_params=query_params)

    return [
        {
            "id": r.id,
            "user": getattr(r, "user", user_id),
            "asset_symbol": getattr(r, "asset_symbol", ""),
            "type": getattr(r, "type", ""),
            "quantity": getattr(r, "quantity", 0),
            "price": getattr(r, "price", 0),
            "fee": getattr(r, "fee", 0),
            "timestamp": getattr(r, "timestamp", ""),
            "voided": getattr(r, "voided", False),
        }
        for r in records
    ]


# ---------------------------------------------------------------------------
# 5. void_transaction
# ---------------------------------------------------------------------------


def void_transaction(
    user_id: str,
    transaction_id: str,
) -> dict:
    """İşlem kaydını voided yap (soft delete)."""
    client = get_client()
    transactions = client.collection("transactions")

    try:
        record = transactions.get_one(transaction_id)
    except Exception:
        raise ValueError("İşlem bulunamadı")

    if getattr(record, "user", None) != user_id:
        raise PermissionError("Yetkisiz: bu işlem size ait değil")

    transactions.update(transaction_id, {"voided": True})
    return {"status": "voided", "transaction_id": transaction_id}
