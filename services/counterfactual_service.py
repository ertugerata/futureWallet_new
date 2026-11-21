"""
FutureWallet - Gölge Portföy / What-If Motoru (Counterfactual Engine)
======================================================================
Gerçek portföy ile "gölge portföy" (alınmayan/satılan pozisyonların
paralel takibi) kıyaslaması ve fırsat maliyeti hesabı.

PocketBase `shadow_portfolios` koleksiyonu üzerinde çalışır.
Prompt 10 ile uyumludur.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

from services.asset_types import guess_asset_type
from services.decision_service import get_decision
from services.multi_asset_manager import AssetManager
from services.pb import admin_create, get_client
from services.price_service import get_price_on

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------
# Tip tanımları
# --------------------------------------------------------------------

ShadowPosition = dict[str, Any]
ComparisonResult = dict[str, Any]


# --------------------------------------------------------------------
# Fiyat çekme yardımcıları
# --------------------------------------------------------------------


def _default_price_fn(symbol: str, asset_type: str | None = None) -> float | None:
    """AssetManager veya price_service ile güncel fiyat."""
    atype = asset_type or guess_asset_type(symbol)
    price = get_price_on(symbol, atype, date.today())
    if price is not None:
        return price
    mgr = AssetManager()
    return mgr.get_price(symbol, atype)


# --------------------------------------------------------------------
# 1. Gölge Pozisyon Oluşturma
# --------------------------------------------------------------------


def create_shadow_position(
    user_id: str,
    decision_id: str,
    asset_symbol: str,
    shadow_type: str,  # HELD_INSTEAD | BOUGHT_INSTEAD
    entry_date: date | None = None,
    entry_price: float | None = None,
    quantity: float | None = None,
    exit_date: date | None = None,
    asset_type: str | None = None,
) -> dict[str, Any]:
    """Bir karar için gölge pozisyon oluşturur (PB shadow_portfolios)."""
    # Sahiplik: karar yoksa ya da bu kullanıcıya ait değilse reddedilir (review minörü #1);
    # aksi halde PB relation'ı sessiz düşürüp yetkisiz bağ kurabiliyordu.
    dec = get_decision(decision_id)
    if dec is None or dec.get("user") != user_id:
        raise ValueError("decision geçersiz veya bu kullanıcıya ait değil")

    if entry_date is None:
        entry_date = date.today()
    if asset_type is None:
        asset_type = guess_asset_type(asset_symbol)
    if entry_price is None:
        entry_price = _default_price_fn(asset_symbol, asset_type) or 0.0
    if quantity is None:
        quantity = 0.0

    if entry_price < 0 or quantity < 0:
        raise ValueError("entry_price ve quantity >= 0 olmalıdır")

    data = {
        "decision": decision_id,
        "asset_symbol": asset_symbol.upper(),
        "shadow_type": shadow_type,
        "entry_date": f"{entry_date.isoformat()} 00:00:00.000Z",
        "entry_price": float(entry_price),
        "quantity": float(quantity),
        "asset_type": asset_type,
    }
    if exit_date:
        data["exit_date"] = f"{exit_date.isoformat()} 00:00:00.000Z"

    rec = admin_create("shadow_portfolios", data, user_id)
    return {
        "id": rec.id,
        "user": getattr(rec, "user", user_id),
        "decision_id": decision_id,
        "asset_symbol": rec.asset_symbol,
        "shadow_type": rec.shadow_type,
        "entry_date": str(rec.entry_date)[:10],
        "entry_price": float(rec.entry_price),
        "quantity": float(rec.quantity),
        "asset_type": getattr(rec, "asset_type", asset_type),
    }


# --------------------------------------------------------------------
# 2. Gölge Pozisyon Listeleme
# --------------------------------------------------------------------


def get_shadow_positions(
    user_id: str | None = None,
    decision_id: str | None = None,
    asset_symbol: str | None = None,
) -> list[ShadowPosition]:
    """Filtrelere göre gölge pozisyonları PocketBase'den listeler."""
    client = get_client()
    sp_coll = client.collection("shadow_portfolios")

    filters: list[str] = []
    filter_params: dict[str, Any] = {}
    if user_id:
        filters.append("user = {:user_id}")
        filter_params["user_id"] = user_id
    if decision_id:
        filters.append("decision = {:decision_id}")
        filter_params["decision_id"] = decision_id
    if asset_symbol:
        filters.append("asset_symbol = {:asset_symbol}")
        filter_params["asset_symbol"] = asset_symbol.upper()

    query_params: dict[str, Any] = {}
    if filters:
        query_params["filter"] = client.filter(" && ".join(filters), filter_params)

    try:
        records = sp_coll.get_full_list(query_params=query_params)
    except Exception as exc:
        logger.error("Gölge pozisyonlar listelenemedi: %s", exc)
        return []

    result: list[ShadowPosition] = []
    for rec in records:
        sym = rec.asset_symbol
        atype = getattr(rec, "asset_type", None) or guess_asset_type(sym)
        current_price = _default_price_fn(sym, atype)
        qty = float(rec.quantity or 0.0)
        current_value = qty * (current_price or 0.0)

        result.append(
            {
                "id": rec.id,
                "user": getattr(rec, "user", ""),
                "decision_id": rec.decision,
                "asset_symbol": sym,
                "shadow_type": rec.shadow_type,
                "entry_date": str(rec.entry_date)[:10],
                "entry_price": float(rec.entry_price or 0.0),
                "quantity": qty,
                "current_price": current_price,
                "current_value": current_value,
                "exit_date": getattr(rec, "exit_date", None),
                "asset_type": atype,
            }
        )
    return result


# --------------------------------------------------------------------
# 3. Kıyaslama ve Fırsat Maliyeti
# --------------------------------------------------------------------


def compare_real_vs_shadow(
    as_of: date,
    real_holdings: list[dict[str, Any]],
    shadow_positions: list[ShadowPosition] | None = None,
    price_fn: Callable[[str], float | None] | None = None,
) -> ComparisonResult:
    """Gerçek portföy ile gölge pozisyonları kıyaslar ve fırsat maliyetini hesaplar."""
    if price_fn is None:
        price_fn = lambda sym: _default_price_fn(sym)

    if shadow_positions is None:
        shadow_positions = get_shadow_positions()

    # Gerçek portföy değeri
    real_value = 0.0
    real_holdings_out = []
    for h in real_holdings:
        sym = h["asset_symbol"]
        qty = float(h.get("quantity", 0.0))
        p = price_fn(sym) or 0.0
        val = qty * p
        real_value += val
        real_holdings_out.append(
            {
                "asset_symbol": sym,
                "quantity": qty,
                "price": p,
                "value": val,
            }
        )

    # Gölge portföy değeri
    shadow_value = 0.0
    shadow_holdings_out = []
    for sp in shadow_positions:
        sym = sp["asset_symbol"]
        qty = float(sp.get("quantity", 0.0))
        p = price_fn(sym) or 0.0
        val = qty * p
        shadow_value += val
        shadow_holdings_out.append(
            {
                "asset_symbol": sym,
                "quantity": qty,
                "entry_price": sp.get("entry_price", 0.0),
                "current_price": p,
                "current_value": val,
                "shadow_type": sp.get("shadow_type", ""),
            }
        )

    # Fırsat maliyeti = Gölge Değer - Gerçek Değer
    # (Gölge daha değerliyse fırsat maliyeti pozitiftir: kaçırılan kazanç)
    opportunity_cost = shadow_value - real_value
    opportunity_cost_pct = (opportunity_cost / real_value) if real_value != 0 else 0.0

    return {
        "as_of": as_of.isoformat(),
        "real_portfolio_value": round(real_value, 2),
        "shadow_portfolio_value": round(shadow_value, 2),
        "opportunity_cost": round(opportunity_cost, 2),
        "opportunity_cost_pct": round(opportunity_cost_pct, 6),
        "real_holdings": real_holdings_out,
        "shadow_holdings": shadow_holdings_out,
    }


# --------------------------------------------------------------------
# 4. What-If Senaryo
# --------------------------------------------------------------------


def what_if_scenario(
    decision_id: str,
    as_of: date | None = None,
    price_fn: Callable[[str], float | None] | None = None,
) -> dict[str, Any]:
    """Bir karar için 'Ne olurdu?' senaryosu."""
    if as_of is None:
        as_of = date.today()

    dec = get_decision(decision_id)
    if dec is None:
        return {"error": "decision not found"}

    shadow_positions = get_shadow_positions(decision_id=decision_id)

    # Eğer karara bağlı gölge pozisyon varsa gerçek miktarlarını ve fiyatlarını kullan
    real_holdings: list[dict[str, Any]] = []
    if shadow_positions:
        for sp in shadow_positions:
            stype = sp.get("shadow_type", "")
            qty = sp.get("quantity", 0.0)
            entry_p = sp.get("entry_price", 0.0)
            sym = sp.get("asset_symbol", dec["asset_symbol"])

            if stype == "HELD_INSTEAD":
                # Kararda satıldı, elde nakit var: gerçek değer = nakit gelir
                real_holdings.append(
                    {
                        "asset_symbol": "USDT",
                        "quantity": qty * entry_p,
                        "type": "cash",
                    }
                )
            else:
                real_holdings.append(
                    {
                        "asset_symbol": sym,
                        "quantity": qty,
                        "type": sp.get("asset_type", "crypto"),
                    }
                )
    else:
        # Bağlı gölge pozisyon henüz yoksa karar sembolünden örnek pozisyon
        real_holdings.append(
            {
                "asset_symbol": dec["asset_symbol"],
                "quantity": 1.0,
                "type": guess_asset_type(dec["asset_symbol"]),
            }
        )

    comp = compare_real_vs_shadow(as_of, real_holdings, shadow_positions, price_fn)

    return {
        "decision_id": dec["id"],
        "decision": {
            "id": dec["id"],
            "date": dec["date"].isoformat() if dec.get("date") else None,
            "asset_symbol": dec["asset_symbol"],
            "action": dec["action"],
            "rationale": dec["rationale"],
            "sentiment": dec["sentiment"],
            "target_price": dec["target_price"],
            "target_date": dec["target_date"].isoformat() if dec.get("target_date") else None,
            "status": dec["status"],
        },
        "as_of": comp["as_of"],
        "real_portfolio_value": comp["real_portfolio_value"],
        "shadow_portfolio_value": comp["shadow_portfolio_value"],
        "opportunity_cost": comp["opportunity_cost"],
        "opportunity_cost_pct": comp["opportunity_cost_pct"],
        "real_holdings": comp["real_holdings"],
        "shadow_holdings": comp["shadow_holdings"],
    }
