"""
FutureWallet - Gölge Portföy / What-If Motoru (Counterfactual Engine)

MVP §3.3, TODO 2.3.

Gerçek portföy ile "gölge portföy" (alınmayan/satılan pozisyonların
parallel takibi) kıyaslaması. Fırsat maliyeti hesaplama.
"""

from datetime import date, datetime
from typing import Callable, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db import Decision, ShadowPortfolio
from services.multi_asset_manager import AssetManager


# --------------------------------------------------------------------
# Tip tanımları
# --------------------------------------------------------------------

ShadowPosition = Dict  # {'id': str, 'decision_id': str, 'asset_symbol': str,
                       #  'simulated_action': str, 'entry_date': str, 'entry_price': float,
                       #  'quantity': float, 'current_price': float, 'current_value': float}

ComparisonResult = Dict  # {'real_portfolio_value': float, 'shadow_portfolio_value': float,
                          #  'opportunity_cost': float, 'opportunity_cost_pct': float,
                          #  'real_holdings': List[Dict], 'shadow_holdings': List[Dict]}


# --------------------------------------------------------------------
# Yardımcı: fiyat çekme
# --------------------------------------------------------------------

def _default_price_fn(symbol: str, asset_type: str) -> Optional[float]:
    """AssetManager ile güncel fiyat."""
    mgr = AssetManager()
    return mgr.get_price(symbol, asset_type)


# --------------------------------------------------------------------
# 1. ShadowPosition oluştur
# --------------------------------------------------------------------

def create_shadow_position(
    session: Session,
    decision_id: str,
    asset_symbol: str,
    simulated_action: str,   # HELD_INSTEAD | BOUGHT_INSTEAD | ...
    entry_date: Optional[date] = None,
    entry_price: Optional[float] = None,
    quantity: Optional[float] = None,
) -> ShadowPortfolio:
    """
    Bir karar için gölge pozisyon oluştur.

    Args:
        session: SQLAlchemy Session
        decision_id: İlgili karar ID (Foreign Key)
        asset_symbol: Varlık sembolü
        simulated_action: Ne yapılması durumunun simüle edileceği
                          (örn: HELD_INSTEAD — satılmayan, BOUGHT_INSTEAD — alınmayan)
        entry_date: Giriş tarihi. None → bugün.
        entry_price: Giriş fiyatı. None → güncel fiyat.
        quantity: Miktar. None → 0.

    Returns:
        Yeni ShadowPortfolio nesnesi.
    """
    if entry_date is None:
        entry_date = date.today()
    if entry_price is None:
        mgr = AssetManager()
        entry_price = mgr.get_price(asset_symbol, "crypto")
        if entry_price is None:
            entry_price = 0.0
    if quantity is None:
        quantity = 0.0

    sp = ShadowPortfolio(
        decision_id=decision_id,
        asset_symbol=asset_symbol.upper(),
        simulated_action=simulated_action,
        entry_date=entry_date,
        entry_price=entry_price,
        quantity=quantity,
    )
    session.add(sp)
    return sp


# --------------------------------------------------------------------
# 2. Gölge pozisyon sorgulama
# --------------------------------------------------------------------

def get_shadow_positions(
    session: Session,
    decision_id: Optional[str] = None,
    asset_symbol: Optional[str] = None,
) -> List[ShadowPosition]:
    """
    Gölge pozisyon listesi.

    Args:
        session: SQLAlchemy Session
        decision_id: Belirli bir karar'ın gölge pozisyonları.
        asset_symbol: Belirli bir varlık'taki gölge pozisyonları.

    Returns:
        List[ShadowPosition] — her pozisyon için güncel fiyat ve değer.
    """
    stmt = select(ShadowPortfolio)

    if decision_id is not None:
        stmt = stmt.where(ShadowPortfolio.decision_id == decision_id)
    if asset_symbol is not None:
        stmt = stmt.where(ShadowPortfolio.asset_symbol == asset_symbol.upper())

    positions = session.execute(stmt).scalars().all()
    result: List[ShadowPosition] = []

    for sp in positions:
        mgr = AssetManager()
        current_price = mgr.get_price(sp.asset_symbol, "crypto")
        if current_price is None:
            current_price = 0.0

        result.append({
            "id":                 sp.id,
            "decision_id":        sp.decision_id,
            "asset_symbol":       sp.asset_symbol,
            "simulated_action":   sp.simulated_action,
            "entry_date":         sp.entry_date.isoformat()
                                  if sp.entry_date else None,
            "entry_price":        sp.entry_price,
            "quantity":           sp.quantity,
            "current_price":      current_price,
            "current_value":      sp.quantity * current_price,
        })

    return result


# --------------------------------------------------------------------
# 3. Gerçek vs. Gölge kıyaslama (Fırsat Maliyeti)
# --------------------------------------------------------------------

def compare_real_vs_shadow(
    session: Session,
    as_of: date,
    real_holdings: List[Dict],       # [{'asset_symbol': 'BTC', 'quantity': 0.5, ...}, ...]
    shadow_positions: Optional[List[ShadowPosition]] = None,
    price_fn: Optional[Callable[[str], Optional[float]]] = None,
) -> ComparisonResult:
    """
    Belirtilen tarihte gerçek portföy ile gölge portföy değerlerini kıyaslar.

    Args:
        session: SQLAlchemy Session
        as_of: Karşılaştırma tarihi
        real_holdings: Gerçek portföy holdings (ledger_service.get_portfolio_snapshot'dan)
        shadow_positions: Gölge pozisyon listesi. None → get_shadow_positions(session) çağrılır.
        price_fn: (symbol) → fiyat. None → AssetManager default.

    Returns:
        {
            "as_of":                     "YYYY-MM-DD",
            "real_portfolio_value":      float,
            "shadow_portfolio_value":    float,
            "opportunity_cost":          float,   # gerçek - gölge (pozitif → gerçek daha iyi)
            "opportunity_cost_pct":      float,   # (gerçek - gölge) / |gölge|
            "real_holdings":             List[Dict],
            "shadow_holdings":           List[Dict],
        }
    """
    if price_fn is None:
        price_fn = _default_price_fn

    if shadow_positions is None:
        shadow_positions = get_shadow_positions(session)

    # Gerçek portföy değeri
    real_value = 0.0
    real_holdings_out = []
    for h in real_holdings:
        sym = h["asset_symbol"]
        qty = h.get("quantity", 0.0)
        p = price_fn(sym)
        val = qty * (p if p is not None else 0.0)
        real_value += val
        real_holdings_out.append({
            "asset_symbol": sym,
            "quantity":    qty,
            "price":       p,
            "value":       val,
        })

    # Gölge portföy değeri
    shadow_value = 0.0
    shadow_holdings_out = []
    for sp in shadow_positions:
        sym = sp["asset_symbol"]
        qty = sp.get("quantity", 0.0)
        p = price_fn(sym)
        val = qty * (p if p is not None else 0.0)
        shadow_value += val
        shadow_holdings_out.append({
            "asset_symbol":     sym,
            "quantity":         qty,
            "entry_price":      sp.get("entry_price", 0.0),
            "current_price":    p,
            "current_value":    val,
            "simulated_action": sp.get("simulated_action", ""),
        })

    # Fırsat maliyeti: gerçek - gölge
    # Pozitif → gerçek daha iyi (gölge seçimi fırsat maliyeti yaratmadı)
    # Negatif → gölge daha iyi (gerçek seçim fırsat maliyeti yarattı)
    opportunity_cost = real_value - shadow_value
    opportunity_cost_pct = (
        (opportunity_cost / shadow_value) if shadow_value != 0 else 0.0
    )

    return {
        "as_of":                   as_of.isoformat(),
        "real_portfolio_value":    round(real_value, 2),
        "shadow_portfolio_value":  round(shadow_value, 2),
        "opportunity_cost":        round(opportunity_cost, 2),
        "opportunity_cost_pct":    round(opportunity_cost_pct, 6),
        "real_holdings":           real_holdings_out,
        "shadow_holdings":         shadow_holdings_out,
    }


# --------------------------------------------------------------------
# 4. What-If Senaryo (tek karar için)
# --------------------------------------------------------------------

def what_if_scenario(
    session: Session,
    decision_id: str,
    as_of: Optional[date] = None,
    price_fn: Optional[Callable[[str], Optional[float]]] = None,
) -> Dict:
    """
    Bir karar için "ne olurdu?" senaryosu.

    Gerçek portföy (kararın gerçekleştiği pozisyon) vs.
    gölge portföy (kararın alternatifi) kıyaslaması.

    Args:
        session: SQLAlchemy Session
        decision_id: Karar ID
        as_of: Karşılaştırma tarihi. None → bugün.
        price_fn: (symbol) → fiyat. None → AssetManager default.

    Returns:
        {
            "decision_id":           str,
            "decision":              dict,          # karar detayları
            "as_of":                 "YYYY-MM-DD",
            "real_portfolio_value":  float,
            "shadow_portfolio_value": float,
            "opportunity_cost":      float,
            "opportunity_cost_pct":  float,
            "real_holdings":         List[Dict],
            "shadow_holdings":       List[Dict],
        }
    """
    if as_of is None:
        as_of = date.today()

    # Karar bilgisi
    stmt = select(Decision).where(Decision.id == decision_id)
    dec = session.execute(stmt).scalars().first()
    if dec is None:
        return {"error": "decision not found"}

    # Gerçek holdings: kararın asset_symbol'undaki miktarı baz alır
    # (Bu basitleştirilmiş: gerçek miktar ledger'dan çekilebilir)
    real_holdings = [{
        "asset_symbol": dec.asset_symbol,
        "quantity":     1.0,           # placeholder — gerçek miktar ledger'dan
        "type":         "crypto",
    }]

    # Gölge pozisyon: bu karar'a bağlı shadow_portfolios
    sp_stmt = select(ShadowPortfolio).where(ShadowPortfolio.decision_id == decision_id)
    shadow_pos = session.execute(sp_stmt).scalars().all()

    # Gölge pozisyonlarını dict formatına çevir
    shadow_positions = []
    for sp in shadow_pos:
        shadow_positions.append({
            "id":                 sp.id,
            "decision_id":        sp.decision_id,
            "asset_symbol":       sp.asset_symbol,
            "simulated_action":   sp.simulated_action,
            "entry_date":         sp.entry_date.isoformat()
                                  if sp.entry_date else None,
            "entry_price":        sp.entry_price,
            "quantity":           sp.quantity,
        })

    # Karşılaştırma
    comp = compare_real_vs_shadow(session, as_of, real_holdings, shadow_positions, price_fn)

    return {
        "decision_id":           dec.id,
        "decision":              {
            "id":             dec.id,
            "date":           dec.date.isoformat() if dec.date else None,
            "asset_symbol":   dec.asset_symbol,
            "action":         dec.action,
            "rationale":      dec.rationale,
            "sentiment":      dec.sentiment,
            "target_price":   dec.target_price,
            "target_date":    dec.target_date.isoformat()
                              if dec.target_date else None,
            "status":         dec.status,
        },
        "as_of":                 comp["as_of"],
        "real_portfolio_value":  comp["real_portfolio_value"],
        "shadow_portfolio_value": comp["shadow_portfolio_value"],
        "opportunity_cost":      comp["opportunity_cost"],
        "opportunity_cost_pct":  comp["opportunity_cost_pct"],
        "real_holdings":         comp["real_holdings"],
        "shadow_holdings":       comp["shadow_holdings"],
    }
