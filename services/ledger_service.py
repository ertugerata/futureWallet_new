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
from collections import OrderedDict
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, Optional

from services.asset_types import _guess_asset_type
from services.enums import TransactionType
from services.multi_asset_manager import AssetManager
from services.pb import admin_create, admin_update, get_client

logger = logging.getLogger(__name__)


# Kullanıcı bazlı concurrency kilidi (LRU cache - P6: sınırlı boyut)
_MAX_USER_LOCKS = 1024
_user_locks: OrderedDict[str, threading.Lock] = OrderedDict()
_user_locks_lock = threading.Lock()


def _get_user_lock(user_id: str) -> threading.Lock:
    """Kullanıcı kilidini al (LRU eviction)."""
    with _user_locks_lock:
        if user_id in _user_locks:
            # Move to end (most recently used)
            _user_locks.move_to_end(user_id)
            return _user_locks[user_id]

        if len(_user_locks) >= _MAX_USER_LOCKS:
            # Evict least recently used
            _user_locks.popitem(last=False)

        lock = threading.Lock()
        _user_locks[user_id] = lock
        return lock


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

        elif tx_type in ("DIVIDEND", "CASH_IN"):
            # Nakit girişleri sembolden bağımsız tek CASH kovasında toplanır;
            # temettü tutarı hisse adedine eklenmez (review #5)
            cash = holdings.setdefault(
                "CASH",
                {
                    "asset_symbol": "CASH",
                    "quantity": 0.0,
                    "type": "cash",
                    "total_cost": 0.0,
                    "average_cost": 0.0,
                },
            )
            cash["quantity"] += quantity

        elif tx_type == "CASH_OUT":
            cash = holdings.setdefault(
                "CASH",
                {
                    "asset_symbol": "CASH",
                    "quantity": 0.0,
                    "type": "cash",
                    "total_cost": 0.0,
                    "average_cost": 0.0,
                },
            )
            cash["quantity"] = max(0.0, cash["quantity"] - quantity)

    return holdings


def _get_holdings_at_date(user_id: str, as_of: date) -> dict[str, AssetHolding]:
    """Belirtilen tarihteki holdings'leri PB transactions collection'undan hesapla."""
    as_of_end = as_of + timedelta(days=1)
    as_of_str = as_of_end.isoformat() + " 00:00:00.000Z"

    client = get_client()
    transactions = client.collection("transactions")
    filter_expr = client.filter(
        "user = {:user_id} && timestamp <= {:as_of} && voided = false",
        {"user_id": user_id, "as_of": as_of_str},
    )

    try:
        records = transactions.get_full_list(query_params={"filter": filter_expr})
    except Exception as exc:
        logger.warning("Transactions okunurken hata (filtre: %s): %s", filter_expr, exc)
        # Eğer datetime formatı uyuşmazsa yedek sorgu
        records = transactions.get_full_list(
            query_params={
                "filter": client.filter("user = {:user_id} && voided = false", {"user_id": user_id})
            }
        )
        # Python tarafında tarih filtresi uygula
        filtered = []
        for r in records:
            ts_str = str(getattr(r, "timestamp", ""))
            try:
                ts_date = date.fromisoformat(
                    ts_str.split("T", maxsplit=1)[0].split(" ", maxsplit=1)[0]
                )
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

    # cash_received yalnız DIVIDEND girişlerinin toplamıdır; CASH_IN nakit kovasına girer ama
    # temettü sayılmaz (review #4/#5)
    client = get_client()
    as_of_div = (as_of + timedelta(days=1)).isoformat() + " 00:00:00.000Z"
    div_filter = client.filter(
        "user = {:user_id} && type = {:tx_type} && voided = false && timestamp <= {:as_of}",
        {"user_id": user_id, "tx_type": "DIVIDEND", "as_of": as_of_div},
    )
    dividend_records = client.collection("transactions").get_full_list(
        query_params={"filter": div_filter}
    )
    cash_received = float(sum(_tx_get(r, "quantity", 0) or 0 for r in dividend_records))

    total_value = 0.0
    total_cost = 0.0
    holdings_list = []

    for sym, h in holdings.items():
        qty = h["quantity"]
        if qty <= 0:
            continue
        atype = h.get("type", _guess_asset_type(sym))
        if atype == "cash":
            # Nakit kovası nominal 1.0'dan değerlenir; fiyat araması yapılmaz (Prompt 7)
            current_price = 1.0
        else:
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
        "cash_received": cash_received,
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

    with _get_user_lock(user_id):
        if tx_type_upper in ("SELL", "CASH_OUT"):
            current_holdings = _get_holdings_at_date(user_id, timestamp)
            if tx_type_upper == "SELL":
                current_qty = current_holdings.get(asset_symbol_upper, {}).get("quantity", 0.0)
                if quantity > current_qty:
                    raise InsufficientBalanceError(
                        f"Yetersiz stok: {asset_symbol_upper} eldeki miktar={current_qty}, satılmak istenen={quantity}"
                    )
            else:
                balance = current_holdings.get("CASH", {}).get("quantity", 0.0)
                if quantity > balance:
                    raise InsufficientBalanceError(
                        f"Yetersiz bakiye: nakit={balance}, çekilmek istenen={quantity}"
                    )

        # ISO format tarih
        ts_str = f"{timestamp.isoformat()} 00:00:00.000Z"

        data = {
            "asset_symbol": asset_symbol_upper,
            "type": tx_type_upper,
            "quantity": quantity,
            "price": price,
            "fee": fee,
            "timestamp": ts_str,
            "voided": False,
        }

        record = admin_create("transactions", data, user_id)

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

    filter_parts = ["user = {:user_id}"]
    filter_params: dict[str, Any] = {"user_id": user_id}
    if asset_symbol is not None:
        filter_parts.append("asset_symbol = {:asset_symbol}")
        filter_params["asset_symbol"] = asset_symbol.upper()
    if tx_type is not None:
        filter_parts.append("type = {:tx_type}")
        filter_params["tx_type"] = tx_type.upper()

    filter_str = client.filter(" && ".join(filter_parts), filter_params)
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
    try:
        admin_update("transactions", transaction_id, {"voided": True}, user_id)
    except PermissionError:
        raise PermissionError("Yetkisiz: bu işlem size ait değil")
    except Exception:
        raise ValueError("İşlem bulunamadı")

    return {"status": "voided", "transaction_id": transaction_id}


# ---------------------------------------------------------------------------
# 6. get_portfolio_snapshots (bulk - P5: N+1 elimination)
# ---------------------------------------------------------------------------


def get_portfolio_snapshots(
    user_id: str,
    dates: list[date],
    price_fn: Callable[[str, str, date], Optional[float]] | None = None,
) -> dict[date, PortfolioSnapshot]:
    """
    Birden fazla tarih için portföy snapshot'larını toplu hesaplar (N+1 elimination).
    
    Args:
        user_id: Kullanıcı ID
        dates: Hesaplanacak tarihler (sıralı olmalı)
        price_fn: Fiyat fonksiyonu (symbol, asset_type, on_date) -> price
                  None ise get_price_on kullanılır
    
    Returns:
        Dict[date -> PortfolioSnapshot]
    """
    if not dates:
        return {}

    # Ensure dates are sorted
    dates = sorted(dates)
    start_date = dates[0]
    end_date = dates[-1]

    # Tüm işlemleri BİR KEZ çek (as_of en büyük tarih için)
    from services.pb import get_admin_client
    admin = get_admin_client()

    filter_expr = admin.filter(
        "user = {:user_id} && voided = false && timestamp <= {:end}",
        {"user_id": user_id, "end": (end_date + timedelta(days=1)).isoformat() + " 00:00:00.000Z"}
    )
    records = admin.collection("transactions").get_full_list(
        query_params={"filter": filter_expr, "sort": "timestamp"}
    )

    # İşlemleri tarihe göre grupla
    from collections import defaultdict
    txs_by_date: dict[date, list[Any]] = defaultdict(list)
    for r in records:
        ts_str = str(getattr(r, "timestamp", ""))
        try:
            ts_date = date.fromisoformat(
                ts_str.split("T", maxsplit=1)[0].split(" ", maxsplit=1)[0]
            )
            txs_by_date[ts_date].append(r)
        except Exception:
            pass

    # Dividend records for cash_received (toplu çek)
    div_filter = admin.filter(
        "user = {:user_id} && type = {:tx_type} && voided = false && timestamp <= {:end}",
        {"user_id": user_id, "tx_type": "DIVIDEND", "end": (end_date + timedelta(days=1)).isoformat() + " 00:00:00.000Z"}
    )
    div_records = admin.collection("transactions").get_full_list(query_params={"filter": div_filter})
    div_by_date: dict[date, list[Any]] = defaultdict(list)
    for r in div_records:
        ts_str = str(getattr(r, "timestamp", ""))
        try:
            ts_date = date.fromisoformat(
                ts_str.split("T", maxsplit=1)[0].split(" ", maxsplit=1)[0]
            )
            div_by_date[ts_date].append(r)
        except Exception:
            pass

    # Fiyat fonksiyonu
    if price_fn is None:
        from services.asset_types import _guess_asset_type
        from services.price_service import get_price_on as _get_price_on

        # Sembolleri topla (tüm tarihler için)
        all_symbols: set[str] = set()
        temp_holdings = _build_holdings_from_transactions(records)
        for sym, h in temp_holdings.items():
            if h.get("type") != "cash":
                all_symbols.add(sym)

        # Bulk price fetch
        asset_types = {s: h.get("type", _guess_asset_type(s)) for s, h in temp_holdings.items() if h.get("type") != "cash"}
        if all_symbols:
            from services.price_service import get_prices_bulk
            bulk_prices = get_prices_bulk(
                symbols=sorted(all_symbols),
                asset_types=asset_types,
                start_date=dates[0],
                end_date=dates[-1],
            )
        else:
            bulk_prices = {}

        def price_fn(sym: str, atype: str, on_date: date) -> Optional[float]:
            # Önce bulk cache'den dene
            if sym in bulk_prices and on_date in bulk_prices[sym]:
                return bulk_prices[sym][on_date]
            # Sonra get_price_on
            return _get_price_on(sym, atype, on_date)
    else:
        # Custom price_fn verilmişse wrapper
        def price_fn(sym: str, atype: str, on_date: date) -> Optional[float]:
            return price_fn(sym, atype, on_date)

    # CASH dividend toplamları tarihlerine göre
    cash_received_by_date: dict[date, float] = {}
    for d, divs in div_by_date.items():
        cash_received_by_date[d] = float(sum(_tx_get(r, "quantity", 0) or 0 for r in divs))

    # Cumulative cash_received
    cum_cash_received = 0.0
    sorted_div_dates = sorted(cash_received_by_date.keys())
    div_idx = 0

    # Snapshot'ları hesapla
    results: dict[date, PortfolioSnapshot] = {}
    current_holdings: dict[str, AssetHolding] = {}

    # Incremental approach: process dates in order, applying txs between dates
    tx_dates_sorted = sorted(txs_by_date.keys())
    tx_idx = 0

    for target_date in dates:
        # Apply transactions between previous date and target_date
        while tx_idx < len(tx_dates_sorted) and tx_dates_sorted[tx_idx] <= target_date:
            tx_date = tx_dates_sorted[tx_idx]
            for tx in txs_by_date[tx_date]:
                _apply_transaction(current_holdings, tx)
            tx_idx += 1

        # Snapshot için holdings kopyala
        holdings_copy = {}
        for sym, h in current_holdings.items():
            if h["quantity"] > 0:
                holdings_copy[sym] = h.copy()

        # Cash received up to this date
        cum_cash = sum(cash_received_by_date[d] for d in cash_received_by_date if d <= target_date)

        # Snapshot hesapla
        total_value = 0.0
        total_cost = 0.0
        holdings_list = []

        for sym, h in holdings_copy.items():
            qty = h["quantity"]
            if qty <= 0:
                continue
            atype = h.get("type", _guess_asset_type(sym))
            if atype == "cash":
                current_price = 1.0
            else:
                current_price = price_fn(sym, atype, target_date) or 0.0
            val = qty * current_price
            cost = h.get("total_cost", 0.0)
            unrealized_pnl = val - cost
            unrealized_pnl_pct = (unrealized_pnl / cost * 100.0) if cost > 0 else 0.0

            total_value += val
            total_cost += cost
            holdings_list.append({
                "asset_symbol": sym,
                "quantity": qty,
                "current_price": current_price,
                "current_value": val,
                "average_cost": h.get("average_cost", 0.0),
                "total_cost": cost,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "type": atype,
            })

        pnl = total_value - total_cost
        pnl_pct = (pnl / total_cost * 100.0) if total_cost > 0 else 0.0

        results[target_date] = {
            "as_of": target_date.isoformat(),
            "holdings": holdings_list,
            "total_value": total_value,
            "total_cost": total_cost,
            "cash_received": cum_cash,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        }

    return results


def _apply_transaction(holdings: dict[str, AssetHolding], tx: Any) -> None:
    """Tek bir işlemi holdings'a uygula."""
    if _tx_get(tx, "voided", False):
        return

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

    elif tx_type in ("DIVIDEND", "CASH_IN"):
        cash = holdings.setdefault(
            "CASH",
            {
                "asset_symbol": "CASH",
                "quantity": 0.0,
                "type": "cash",
                "total_cost": 0.0,
                "average_cost": 0.0,
            },
        )
        cash["quantity"] += quantity

    elif tx_type == "CASH_OUT":
        cash = holdings.setdefault(
            "CASH",
            {
                "asset_symbol": "CASH",
                "quantity": 0.0,
                "type": "cash",
                "total_cost": 0.0,
                "average_cost": 0.0,
            },
        )
        cash["quantity"] = max(0.0, cash["quantity"] - quantity)
