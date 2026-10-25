"""
FutureWallet - FastAPI Uygulama Çekirdeği (Endpoint Implementasyonları)

Endpoint'ler:
  /api/portfolio/snapshot       → ledger_service.get_portfolio_snapshot
  /api/portfolio/time-travel    → ledger_service.time_travel_portfolio
  /api/portfolio/real-valuation → benchmark_service.compute_real_return
  /api/decisions                → decision_service CRUD
  /api/decisions/{id}/close     → decision_service.close_decision
  /api/decisions/{id}/target-check → decision_service.check_decision_target
  /api/counterfactual           → placeholder (counterfactual_service henüz yok)
  /api/simulation/monte-carlo   → placeholder (simulation_service henüz yok)

TODO.md 4.1.
"""

import os
import sys


from contextlib import asynccontextmanager

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)


from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from datetime import date as _date

from db import init_db, get_session, Decision, Transaction
from services.ledger_service import get_portfolio_snapshot, time_travel_portfolio
from services.benchmark_service import compute_real_return, get_current_market_prices
from services.decision_service import (
    create_decision as svc_create_decision,
    get_decision as svc_get_decision,
    list_decisions as svc_list_decisions,
    update_decision as svc_update_decision,
    close_decision as svc_close_decision,
    check_decision_target as svc_check_decision_target,
)


from services.counterfactual_service import (
    what_if_scenario,
    create_shadow_position,
    get_shadow_positions,
    compare_real_vs_shadow,
)
from services.simulation_service import (
    monte_carlo_simulation,
    stress_test,
    generate_risk_narrative,
)

# ---------------------------------------------------------------------------
# Pydantic request / response model'leri
# ---------------------------------------------------------------------------

class DecisionCreateRequest(BaseModel):
    asset_symbol: str
    action: str                     # BUY | SELL | HOLD
    rationale: Optional[str] = None
    sentiment: Optional[str] = None  # FOMO | STRATEGIC | PANIC | DIVIDEND | RISK_REDUCTION
    target_price: Optional[float] = None
    target_date: Optional[str] = None  # ISO YYYY-MM-DD
    transaction_id: Optional[str] = None


class DecisionUpdateRequest(BaseModel):
    rationale: Optional[str] = None
    sentiment: Optional[str] = None
    target_price: Optional[float] = None
    target_date: Optional[str] = None
    status: Optional[str] = None


class DecisionsListRequest(BaseModel):
    status: Optional[str] = None
    sentiment: Optional[str] = None
    asset_symbol: Optional[str] = None
    action: Optional[str] = None


DecisionCreateRequest.model_rebuild()
DecisionUpdateRequest.model_rebuild()
DecisionsListRequest.model_rebuild()


def _guess_asset_type(symbol: str) -> str:
    """Sembol'dan varlık türünü tahmin et."""
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
    return "crypto"


def _parse_assets_param(assets_str: str) -> List[Dict]:
    """
    'BTC,ETH,GC=F' → [
        {'symbol': 'BTC', 'type': 'crypto', 'amount': 1.0},
        {'symbol': 'ETH', 'type': 'crypto', 'amount': 1.0},
        {'symbol': 'GC=F', 'type': 'commodity', 'amount': 1.0},
    ]
    """
    assets = []
    for sym in assets_str.split(","):
        sym = sym.strip().upper()
        if not sym:
            continue
        atype = _guess_asset_type(sym)
        assets.append({"symbol": sym, "type": atype, "amount": 1.0})
    return assets


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="FutureWallet API",
    description="Event-Sourcing portföy, karar günlüğü ve makro simülasyon API'si",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health & root
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {
        "name": "FutureWallet",
        "version": "0.1.0",
        "docs": "/docs",
    }

from web_app import mount_web
mount_web(app)

# ---------------------------------------------------------------------------
# Helper: session lifecycle (try/commit/except/rollback/finally/close)
# ---------------------------------------------------------------------------

def with_session(func):
    """
    Wrapper: session aç → func(session) → commit / rollback / close.
    """
    def wrapper(*args, **kwargs):
        session = get_session()
        try:
            result = func(session, *args, **kwargs)
            session.commit()
            return result
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    return wrapper


# ---------------------------------------------------------------------------
# Portfolio endpoints
# ---------------------------------------------------------------------------

@app.get("/api/portfolio/snapshot")
async def portfolio_snapshot(
    date: Optional[str] = Query(None, description="ISO YYYY-MM-DD. Yoksa bugün."),
):
    """
    Belirtilen tarihteki portföy snapshot'ı.
    Event log'tan net pozisyonlar + toplam değer.

    Response:
        {
            "holdings": [{"asset_symbol","quantity","type","value"}, ...],
            "total_value": float,
            "as_of_date": "YYYY-MM-DD"
        }
    """
    as_of = None
    if date is not None:
        try:
            parts = date.split("-")
            as_of = date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            raise HTTPException(400, f"Geçersiz date formatı: {date}. ISO YYYY-MM-DD kullanın.")

    session = get_session()
    try:
        result = get_portfolio_snapshot(session, as_of=as_of)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.get("/api/portfolio/time-travel")
async def portfolio_time_travel(
    t_start: str = Query(..., description="ISO YYYY-MM-DD başlangıç tarihi"),
    t_target: Optional[str] = Query(None, description="ISO YYYY-MM-DD hedef tarih. Yoksa bugün."),
):
    """
    T_start dagıtımını T_target fiyatlarıyla değerlendirir.
    Nominal P&L ve varlık bazlı detay return eder.

    Response:
        {
            "holdings": [{"asset_symbol","quantity","type",
                          "value_at_start","value_at_target"}, ...],
            "value_at_start":   float,
            "value_at_target":  float,
            "pnl":              float,
            "pnl_pct":          float,
        }
    """
    def parse_date(s: Optional[str]) -> Optional[_date]:
        if s is None:
            return None
        try:
            parts = s.split("-")
            return _date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            raise HTTPException(400, f"Geçersiz tarih: {s}")

    start = parse_date(t_start)
    target = parse_date(t_target) or _date.today()

    session = get_session()
    try:
        result = time_travel_portfolio(session, start, target)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.get("/api/portfolio/real-valuation")
async def portfolio_real_valuation(
    date_from: str = Query(..., description="ISO YYYY-MM-DD başlangıç"),
    date_to: str = Query(..., description="ISO YYYY-MM-DD bitiş"),
    nominal_start: float = Query(..., description="T_start nominal portföy değeri"),
    nominal_end: Optional[float] = Query(None, description="T_end nominal portföy değeri. Yoksa snapshot'dan al."),
    cpi_type: str = Query("tr", description="tr | us"),
):
    """
    Nominal ve reel (enflasyondan arındırılmış) getiri hesaplama.

    Response:
        {
            "nominal_return_pct": float,
            "real_return_pct":    float | null,
            "cpi_type":           str,
            "cpi_from":           float | null,
            "cpi_to":             float | null,
            "current_market":     {"gold_usd": ..., "sp500": ...},
        }
    """
    try:
        df = date_from.split("-")
        dt_from = _date(int(df[0]), int(df[1]), int(df[2]))
        dt = date_to.split("-")
        dt_to = _date(int(dt[0]), int(dt[1]), int(dt[2]))
    except (ValueError, IndexError):
        raise HTTPException(400, "Geçersiz tarih formatı")

    if nominal_end is None:
        # endpoint kullanıcısından nominal_end gelmediyse, start snapshot'ını al
        # ve start'teki değerle aynı kabul et (yaklaşık)
        session = get_session()
        try:
            snap = get_portfolio_snapshot(session, as_of=dt_from)
            nominal_end_val = snap["total_value"]
            session.close()
        except Exception:
            session.close()
            nominal_end_val = nominal_start
    else:
        nominal_end_val = nominal_end

    session = get_session()
    try:
        result = compute_real_return(
            session, nominal_start, nominal_end_val, dt_from, dt_to, cpi_type=cpi_type,
        )
        session.commit()
        # current market prices ekleyerek response'ü zenginleştir
        result["current_market"] = get_current_market_prices()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Decisions endpoints
# ---------------------------------------------------------------------------

@app.get("/api/decisions")
async def list_decisions_endpoint(
    status: Optional[str] = Query(None),
    sentiment: Optional[str] = Query(None),
    asset_symbol: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
):
    """
    Filtrelenmiş karar listesi.

    Response: List[decision_dict]
    """
    session = get_session()
    try:
        result = svc_list_decisions(
            session,
            status=status,
            sentiment=sentiment,
            asset_symbol=asset_symbol,
            action=action,
            limit=limit,
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.post("/api/decisions", status_code=201)
async def create_decision_endpoint(body: DecisionCreateRequest):
    """
    Yeni karar oluştur.

    Response: decision_dict
    """
    from datetime import date as _date
    target_date = None
    if body.target_date is not None:
        try:
            parts = body.target_date.split("-")
            target_date = _date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            raise HTTPException(400, f"Geçersiz target_date: {body.target_date}")

    session = get_session()
    try:
        dec = svc_create_decision(
            session,
            asset_symbol=body.asset_symbol,
            action=body.action,
            rationale=body.rationale,
            sentiment=body.sentiment,
            target_price=body.target_price,
            target_date=target_date,
            transaction_id=body.transaction_id,
        )
        session.commit()
        return decision_to_dict(dec)
    except ValueError as e:
        session.rollback()
        raise HTTPException(400, str(e))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.get("/api/decisions/{decision_id}")
async def get_decision_endpoint(decision_id: str):
    """ID ile tek karar."""
    session = get_session()
    try:
        dec = svc_get_decision(session, decision_id)
        session.commit()
        if dec is None:
            return JSONResponse(status_code=404, content={"error": "decision not found"})
        return decision_to_dict(dec)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.put("/api/decisions/{decision_id}")
async def update_decision_endpoint(
    decision_id: str,
    body: DecisionUpdateRequest,
):
    """Karar alanlarını güncelle (None → değiştirme)."""
    from datetime import date as _date
    target_date = None
    if body.target_date is not None:
        try:
            parts = body.target_date.split("-")
            target_date = _date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            raise HTTPException(400, f"Geçersiz target_date: {body.target_date}")

    session = get_session()
    try:
        dec = svc_update_decision(
            session,
            decision_id,
            rationale=body.rationale,
            sentiment=body.sentiment,
            target_price=body.target_price,
            target_date=target_date,
            status=body.status,
        )
        session.commit()
        if dec is None:
            return JSONResponse(status_code=404, content={"error": "decision not found"})
        return decision_to_dict(dec)
    except ValueError as e:
        session.rollback()
        raise HTTPException(400, str(e))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.post("/api/decisions/{decision_id}/close")
async def close_decision_endpoint(decision_id: str):
    """Kararı REVIEWED yap."""
    session = get_session()
    try:
        dec = svc_close_decision(session, decision_id)
        session.commit()
        if dec is None:
            return JSONResponse(status_code=404, content={"error": "decision not found"})
        return decision_to_dict(dec)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.get("/api/decisions/{decision_id}/target-check")
async def decision_target_check_endpoint(decision_id: str):
    """
    Kararın hedef fiyat/vade gerçekleşme kontrolü.

    Response:
        {
            "decision_id": ..., "asset_symbol": ..., "action": ...,
            "target_price": ..., "target_date": ...,
            "current_price": ..., "target_hit": ...,
            "target_date_passed": ..., "status_suggestion": ...,
        }
    """
    session = get_session()
    try:
        result = svc_check_decision_target(session, decision_id)
        session.commit()
        if "error" in result:
            return JSONResponse(status_code=404, content=result)
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Placeholder endpoint'ler (henüz implement edilmemiş service'ler)
# ---------------------------------------------------------------------------

@app.get("/api/counterfactual")
async def counterfactual_endpoint(
    decision_id: str = Query(..., description="Karar ID"),
    as_of: Optional[str] = Query(None, description="ISO YYYY-MM-DD. Yoksa bugün."),
):
    """What-If senaryosu: decision_id ile gölge portföy kıyaslaması."""
    def _parse_date(s: Optional[str]) -> Optional[_date]:
        if s is None:
            return None
        try:
            p = s.split("-")
            return _date(int(p[0]), int(p[1]), int(p[2]))
        except (ValueError, IndexError):
            raise HTTPException(400, f"Geçersiz tarih: {s}")

    as_of_date = _parse_date(as_of)

    session = get_session()
    try:
        result = what_if_scenario(session, decision_id, as_of=as_of_date)
        session.commit()
        if "error" in result:
            return JSONResponse(status_code=404, content=result)
        return result
    except ValueError as e:
        session.rollback()
        raise HTTPException(400, str(e))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.get("/api/simulation/monte-carlo")
async def monte_carlo_endpoint(
    assets: str = Query(..., description="Virgülle ayırılmış semboller (örn: BTC,ETH,GC=F)"),
    days: int = Query(126, description="Gün sayısı (varsayılan 126 = 6 ay)"),
    simulations: int = Query(10000, description="Patika sayısı (varsayılan 10,000)"),
    percentiles: str = Query("5,50,95", description="Percentiller (örn: 5,50,95)"),
    seed: Optional[int] = Query(None, description="RNG seed (opsiyonel)"),
):
    """Monte Carlo simülasyonu: portfolio gelecek değer dağılımları."""
    try:
        pct_list = [int(p.strip()) for p in percentiles.split(",") if p.strip()]
    except ValueError:
        raise HTTPException(400, f"Geçersiz percentiles: {percentiles}")

    asset_list = _parse_assets_param(assets)

    session = get_session()
    try:
        result = monte_carlo_simulation(
            session,
            asset_list=asset_list,
            days=days,
            n_simulations=simulations,
            percentiles=pct_list,
            seed=seed,
        )
        session.commit()
        return result
    except ValueError as e:
        session.rollback()
        raise HTTPException(400, str(e))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helper: decision → dict (aynı logic decision_service.decision_to_dict)
# ---------------------------------------------------------------------------

def decision_to_dict(decision: Decision) -> dict:
    return {
        "id":                 decision.id,
        "date":               decision.date.isoformat()
                              if decision.date else None,
        "asset_symbol":       decision.asset_symbol,
        "action":             decision.action,
        "rationale":          decision.rationale,
        "sentiment":          decision.sentiment,
        "target_price":       decision.target_price,
        "target_date":        decision.target_date.isoformat()
                              if decision.target_date else None,
        "status":             decision.status,
        "ai_retrospective":   decision.ai_retrospective,
        "transaction_id":     decision.transaction_id,
    }
