"""
FutureWallet - Gölge Portföy / What-If Motoru (Counterfactual Engine)
======================================================================

MVP §3.3, TODO 2.3.

Gerçek portföy ile "gölge portföy" (alınmayan/satılan pozisyonların
parallel takibi) kıyaslaması. Fırsat maliyeti hesaplama.

PocketBase `shadow_portfolios` koleksiyonu üzerinde çalışır.
Prompt 12 düzeltmeleri: PB geçişi, shadow_type field, exit_date, asset_type.
"""

from collections.abc import Callable
from datetime import date

from services.decision_service import get_decision
from services.multi_asset_manager import AssetManager
from services.pocketbase import get_client

# --------------------------------------------------------------------
# Tip tanımları
# --------------------------------------------------------------------

ShadowPosition = dict  # {'id': str, 'decision_id': str, 'asset_symbol': str,
#  'shadow_type': str, 'entry_date': str, 'entry_price': float,
#  'quantity': float, 'current_price': float, 'current_value': float,
#  'exit_date': Optional[str], 'asset_type': Optional[str]}

ComparisonResult = dict  # {'as_of': str, 'real_portfolio_value': float,
#  'shadow_portfolio_value': float, 'opportunity_cost': float,
#  'opportunity_cost_pct': float, 'real_holdings': List[Dict],
#  'shadow_holdings': List[Dict]}


# --------------------------------------------------------------------
# Yardımcı: fiyat çekme
# --------------------------------------------------------------------


def _default_price_fn(symbol: str, asset_type: str | None = None) -> float | None:
    """AssetManager ile güncel fiyat."""
    mgr = AssetManager()
    return mgr.get_price(symbol, asset_type or "crypto")


def _get_current_price(symbol: str, asset_type: str | None = None) -> float | None:
    """Gölge pozisyon için güncel fiyat. asset_type yoksa crypto default."""
    return _default_price_fn(symbol, asset_type)


# --------------------------------------------------------------------
# 1. ShadowPosition oluştur
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
) -> dict:
    """
    Bir karar için gölge pozisyon oluştur (Prompt 12: PB geçişi).

    Args:
        user_id:      PB auth kullanıcı ID'si (relation: users).
        decision_id:  İlgili karar ID (relation: decisions).
        asset_symbol: Varlık sembolü.
        shadow_type:  HELD_INSTEAD / BOUGHT_INSTEAD.
        entry_date:   Giriş tarihi. None → bugün.
        entry_price:  Giriş fiyatı. None → güncel fiyat.
        quantity:     Miktar. None → 0.
        exit_date:    Çıkış tarihi (opsiyonel).
        asset_type:   Varlık türü (opsiyonel).

    Returns:
        Yeni shadow portfolio dict.
    """
    if entry_date is None:
        entry_date = date.today()
    if entry_price is None:
        entry_price = _default_price_fn(asset_symbol, asset_type)
        if entry_price is None:
            entry_price = 0.0
    if quantity is None:
        quantity = 0.0

    if entry_price < 0 or quantity < 0:
        raise ValueError("entry_price ve quantity >= 0 olmalıdır")

    client = get_client()
    sp_coll = client.collection("shadow_portfolios")

    data = {
        "decision": decision_id,
        "user": user_id,
        "asset_symbol": asset_symbol.upper(),
        "shadow_type": shadow_type,
        "entry_price": entry_price,
        "quantity": quantity,
        "entry_date": entry_date.isoformat(),
        "exit_date": exit_date.isoformat() if exit_date else None,
        "asset_type": asset_type,
    }

    record = sp_coll.create(data)
    return _shadow_record_to_dict(record)


def _shadow_record_to_dict(record) -> dict:
    """PB ShadowPortfolio record → dict."""
    return {
        "id": record.id,
        "decision_id": record["decision"],
        "asset_symbol": record["asset_symbol"],
        "shadow_type": record["shadow_type"],
        "entry_date": record["entry_date"],
        "entry_price": record["entry_price"],
        "quantity": record["quantity"],
        "exit_date": record.get("exit_date"),
        "asset_type": record.get("asset_type"),
    }


# --------------------------------------------------------------------
# 2. Gölge pozisyon sorgulama
# --------------------------------------------------------------------


def get_shadow_positions(
    decision_id: str | None = None,
    asset_symbol: str | None = None,
) -> list[ShadowPosition]:
    """
    Gölge pozisyon listesi (Prompt 12: PB geçişi).

    Args:
        decision_id:  Belirli bir karar'ın gölge pozisyonları (PB relation filter).
        asset_symbol: Belirli bir varlık'taki gölge pozisyonları.

    Returns:
        List[ShadowPosition] — her pozisyon için güncel fiyat ve değer.
    """
    client = get_client()
    sp_coll = client.collection("shadow_portfolios")

    filters: list[str] = []
    if decision_id is not None:
        filters.append(f"decision='{decision_id}'")
    if asset_symbol is not None:
        filters.append(f"asset_symbol='{asset_symbol.upper()}'")

    filter_str = " AND ".join(filters) if filters else ""
    params = f"filter={filter_str}&per_page=1000" if filter_str else "per_page=1000"

    records = sp_coll.get_list(params=params)
    result: list[ShadowPosition] = []

    for rec in records:
        current_price = _get_current_price(rec["asset_symbol"], rec.get("asset_type"))
        current_value = rec["quantity"] * (current_price or 0.0)

        result.append(
            {
                "id": rec.id,
                "decision_id": rec["decision"],
                "asset_symbol": rec["asset_symbol"],
                "shadow_type": rec["shadow_type"],
                "entry_date": rec["entry_date"],
                "entry_price": rec["entry_price"],
                "quantity": rec["quantity"],
                "current_price": current_price,
                "current_value": current_value,
                "exit_date": rec.get("exit_date"),
                "asset_type": rec.get("asset_type"),
            }
        )

    return result


# --------------------------------------------------------------------
# 3. Gerçek vs. Gölge kıyaslama (Fırsat Maliyeti)
# --------------------------------------------------------------------


def compare_real_vs_shadow(
    as_of: date,
    real_holdings: list[dict],
    shadow_positions: list[ShadowPosition] | None = None,
    price_fn: Callable[[str], float | None] | None = None,
) -> ComparisonResult:
    """
    Belirtilen tarihte gerçek portföy ile gölge portföy değerlerini kıyaslar
    (Prompt 12: session parametresi kaldırıldı, PB'ye geçiş).

    Args:
        as_of:             Karşılaştırma tarihi.
        real_holdings:     Gerçek portföy holdings.
        shadow_positions:  Gölge pozisyon listesi. None → get_shadow_positions().
        price_fn:          (symbol) → fiyat. None → _default_price_fn.

    Returns:
        Karşılaştırma sonucu dict.
    """
    if price_fn is None:
        price_fn = _default_price_fn

    if shadow_positions is None:
        shadow_positions = get_shadow_positions()

    # Gerçek portföy değeri
    real_value = 0.0
    real_holdings_out = []
    for h in real_holdings:
        sym = h["asset_symbol"]
        qty = h.get("quantity", 0.0)
        p = price_fn(sym)
        val = qty * (p if p is not None else 0.0)
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
        qty = sp.get("quantity", 0.0)
        p = price_fn(sym)
        val = qty * (p if p is not None else 0.0)
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

    # Fırsat maliyeti: gerçek - gölge
    # Pozitif → gerçek daha iyi; Negatif → gölge daha iyi (gerçek seçim fırsat maliyeti yarattı)
    opportunity_cost = real_value - shadow_value
    opportunity_cost_pct = (opportunity_cost / shadow_value) if shadow_value != 0 else 0.0

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
# 4. What-If Senaryo (tek karar için)
# --------------------------------------------------------------------


def what_if_scenario(
    decision_id: str,
    as_of: date | None = None,
    price_fn: Callable[[str], float | None] | None = None,
) -> dict:
    """
    Bir karar için "ne olurdu?" senaryosu (Prompt 12: session kaldır, PB geçiş).

    Gerçek portföy (kararın gerçekleştiği pozisyon) vs.
    gölge portföy (kararın alternatifi) kıyaslaması.

    Args:
        decision_id: Karar ID.
        as_of:       Karşılaştırma tarihi. None → bugün.
        price_fn:    (symbol) → fiyat. None → default.

    Returns:
        What-If senaryosu sonucu dict.
    """
    if as_of is None:
        as_of = date.today()

    # Karar bilgisi — PB dict (get_decision → decision_to_dict formatı)
    dec = get_decision(decision_id)
    if dec is None:
        return {"error": "decision not found"}

    # Gerçek holdings: kararın asset_symbol'undaki miktarı baz alır
    # (Bu basitleştirilmiş: gerçek miktar ledger'dan çekilebilir)
    real_holdings = [
        {
            "asset_symbol": dec["asset_symbol"],
            "quantity": 1.0,  # placeholder — gerçek miktar ledger'dan
            "type": "crypto",
        }
    ]

    # Gölge pozisyon: bu karar'a bağlı shadow_portfolios (PB relation filter)
    shadow_positions = get_shadow_positions(decision_id=decision_id)

    # Karşılaştırma
    comp = compare_real_vs_shadow(as_of, real_holdings, shadow_positions, price_fn)

    return {
        "decision_id": dec["id"],
        "decision": {
            "id": dec["id"],
            "date": dec["date"].isoformat() if dec["date"] else None,
            "asset_symbol": dec["asset_symbol"],
            "action": dec["action"],
            "rationale": dec["rationale"],
            "sentiment": dec["sentiment"],
            "target_price": dec["target_price"],
            "target_date": dec["target_date"].isoformat() if dec["target_date"] else None,
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
