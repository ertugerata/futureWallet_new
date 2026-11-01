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


from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from typing import Dict, List, Literal, Optional
from datetime import date

from config import API_TOKEN, ALLOWED_HOSTS, ALLOWED_ORIGINS
from db import get_session, init_db
from services.benchmark_service import compute_real_return, get_current_market_prices
from services.counterfactual_service import (
    compare_real_vs_shadow,
    create_shadow_position,
    get_shadow_positions,
    what_if_scenario,
)
from services.decision_service import (
    check_decision_target as svc_check_decision_target,
    close_decision as svc_close_decision,
    create_decision as svc_create_decision,
    decision_to_dict,
    generate_ai_retrospective as svc_generate_ai_retrospective,
    get_decision as svc_get_decision,
    list_decisions as svc_list_decisions,
    update_decision as svc_update_decision,
)
from services.ledger_service import (
    get_portfolio_snapshot,
    time_travel_portfolio,
)
from services.simulation_service import (
    generate_risk_narrative,
    monte_carlo_simulation,
    stress_test,
)
from services.decision_service import _guess_asset_type


# ---------------------------------------------------------------------------
# Auth bağımlılığı (Prompt 1)
# ---------------------------------------------------------------------------

def verify_api_token(request: Request) -> None:
    if not API_TOKEN:
        raise HTTPException(
            status_code=500, detail="API_TOKEN ayarlanmamış. Yapılandırmayı kontrol edin."
        )
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Yetkisiz: token yok")
    token = auth_header[len("Bearer "):]
    if not token or token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Yetkisiz: geçersiz token")


def check_retrospective_rate_limit(request: Request) -> None:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    remote_ip = request.client.host if request.client else "unknown"
    key = (remote_ip, token)
    import time as _time
    now = int(_time.time())
    entry = _RETRO_RATE_LIMITS.get(key)
    if entry is None:
        _RETRO_RATE_LIMITS[key] = {"count": 1, "reset_at": now + 60, "last": now}
        return
    if now - entry["last"] < 60:
        raise HTTPException(status_code=429, detail="Çok fazla istek. Lütfen bekleyin.")
    if now >= entry["reset_at"]:
        entry["count"] = 0
        entry["reset_at"] = now + 60
    entry["count"] += 1
    entry["last"] = now
    if entry["count"] > 5:
        raise HTTPException(status_code=429, detail="Hız sınırı aşıldı. Lütfen bekleyin.")


_RETRO_RATE_LIMITS: Dict = {}


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Pydantic request / response model'leri
# ---------------------------------------------------------------------------

class DecisionCreateRequest(BaseModel):
    asset_symbol: str = Field(
        pattern=r"^[A-Z0-9.=^\-/]{1,20}$",
        max_length=20,
        description="Varlık sembolü (örn: BTC, GC=F, THYAO.IS)",
    )
    action: Literal["BUY", "SELL", "HOLD"]
    rationale: Optional[str] = Field(
        None, max_length=5000, description="Karar gerekçesi (max 5000 karakter)"
    )
    sentiment: Optional[str] = Field(
        None,
        description="FOMO | STRATEGIC | PANIC | DIVIDEND | RISK_REDUCTION",
    )
    target_price: Optional[float] = Field(
        None, gt=0, description="Hedef fiyat (pozitif)"
    )
    target_date: Optional[date] = Field(
        None, description="Hedef tarih (ISO YYYY-MM-DD)"
    )
    transaction_id: Optional[str] = Field(
        None, max_length=36, description="İşlem ID (opsiyonel)"
    )

    @field_validator("sentiment", mode="before")
    @classmethod
    def normalize_sentiment(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return v.upper()

    @field_validator("target_date", mode="before")
    @classmethod
    def empty_date_to_none(cls, v: Any) -> Optional[date]:
        if v is None or v == "":
            return None
        return v

DecisionCreateRequest.model_rebuild()
class DecisionUpdateRequest(BaseModel):
    rationale: Optional[str] = Field(
        None, max_length=5000, description="Yeni gerekçе (max 5000 karakter)"
    )
    sentiment: Optional[str] = Field(
        None, description="FOMO | STRATEGIC | PANIC | DIVIDEND | RISK_REDUCTION"
    )
    target_price: Optional[float] = Field(None, gt=0)
    target_date: Optional[date] = Field(None, description="Yeni hedef tarih")
    status: Optional[Literal["OPEN", "REVIEWED", "EXPIRED", "CLOSED"]] = Field(
        None, description="OPEN | REVIEWED | EXPIRED | CLOSED"
    )

    @field_validator("sentiment", mode="before")
    @classmethod
    def normalize_sentiment(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return v.upper()

    @field_validator("target_date", mode="before")
    @classmethod
    def empty_date_to_none(cls, v: Any) -> Optional[date]:
        if v is None or v == "":
            return None
DecisionUpdateRequest.model_rebuild()


class DecisionsListRequest(BaseModel):
    status: Optional[Literal["OPEN", "REVIEWED", "EXPIRED", "CLOSED"]] = None
    sentiment: Optional[str] = None
    asset_symbol: Optional[str] = None
    action: Optional[Literal["BUY", "SELL", "HOLD"]] = None
DecisionsListRequest.model_rebuild()
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
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()] if ALLOWED_ORIGINS else [],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in ALLOWED_HOSTS.split(",") if h.strip()] if ALLOWED_HOSTS else [])


async def _add_security_headers(request: Request, call_next):
    """Tüm yanıtlara güvenlik başlıkları ekle (Prompt 2)."""
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
app.add_middleware(BaseHTTPMiddleware, dispatch=_add_security_headers)

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
    as_of: Optional[date] = Query(None, alias="date", description="ISO YYYY-MM-DD. Yoksa bugün."),
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
    t_start: date = Query(..., description="ISO YYYY-MM-DD başlangıç tarihi"),
    t_target: Optional[date] = Query(None, description="ISO YYYY-MM-DD hedef tarih. Yoksa bugün."),
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
    target = t_target or date.today()

    session = get_session()
    try:
        result = time_travel_portfolio(session, t_start, target)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.get("/api/portfolio/real-valuation")
async def portfolio_real_valuation(
    date_from: date = Query(..., description="ISO YYYY-MM-DD başlangıç"),
    date_to: date = Query(..., description="ISO YYYY-MM-DD bitiş"),
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
    nominal_end_val: float = nominal_end if nominal_end is not None else nominal_start

    if nominal_end is None:
        session_tmp = get_session()
        try:
            snap = get_portfolio_snapshot(session_tmp, as_of=date_from)
            nominal_end_val = snap["total_value"]
        except Exception:
            nominal_end_val = nominal_start
        finally:
            session_tmp.close()

    session = get_session()
    try:
        result = compute_real_return(
            session, nominal_start, nominal_end_val, date_from, date_to, cpi_type=cpi_type,
        )
        session.commit()
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

@app.get("/api/decisions", dependencies=[Depends(verify_api_token)])
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


@app.post("/api/decisions", status_code=201, dependencies=[Depends(verify_api_token)])
async def create_decision_endpoint(body: DecisionCreateRequest):
    """
    Yeni karar oluştur.

    Response: decision_dict
    """
    session = get_session()

    try:
        dec = svc_create_decision(session,
            asset_symbol=body.asset_symbol,
            action=body.action,
            rationale=body.rationale,
            sentiment=body.sentiment,
            target_price=body.target_price,
            target_date=body.target_date,
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

@app.get("/api/decisions/{decision_id}", dependencies=[Depends(verify_api_token)])
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


@app.put("/api/decisions/{decision_id}", dependencies=[Depends(verify_api_token)])
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
            target_date=body.target_date,
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


@app.post("/api/decisions/{decision_id}/close", dependencies=[Depends(verify_api_token)])
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


@app.get("/api/decisions/{decision_id}/target-check", dependencies=[Depends(verify_api_token)])
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


@app.post("/api/decisions/{decision_id}/retrospective")
async def generate_retrospective_endpoint(decision_id: str):
    """
    Bir karar için AI post-mortem (retrospektif) oluşturur.

    GOOGLE_API_KEY tanımlıysa AI değerlendirme üretir ve
    kararın ai_retrospective alanına kaydeder. Status REVIEWED yapılır.

    Response:
        {
            "decision_id": ..., "retrospective": ...,
            "status": ..., "api_available": ...
        }
    """
    session = get_session()
    try:
        result = svc_generate_ai_retrospective(session, decision_id)
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
    as_of: Optional[date] = Query(None, description="ISO YYYY-MM-DD. Yoksa bugün."),
):
    """What-If senaryosu: decision_id ile gölge portföy kıyaslaması."""
    as_of_date = as_of or date.today()

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
    assets: str = Query(..., description="Virgülle ayrılmış semboller (örn: BTC,ETH,GC=F)"),
    days: int = Query(126, ge=1, le=756, description="Gün sayısı (varsayılan 126 = 6 ay, max 756 = 3 yıl)"),
    simulations: int = Query(10000, ge=100, le=20000, description="Patika sayısı (varsayılan 10,000, aralık 100-20000)"),
    percentiles: str = Query("5,50,95", description="Percentiller (örn: 5,50,95)"),
    seed: Optional[int] = Query(None, description="RNG seed (opsiyonel)"),
):
    """Monte Carlo simülasyonu: portfolio gelecek değer dağılımları."""
    asset_list: List[Dict] = []
    for sym in assets.split(","):
        sym = sym.strip().upper()
        if not sym:
            continue
        if len(asset_list) >= 15:
            raise HTTPException(422, "En fazla 15 varlık belirtebilirsiniz.")
        atype = _guess_asset_type(sym)
        asset_list.append({"symbol": sym, "type": atype, "amount": 1.0})
    try:
        pct_list = [int(p.strip()) for p in percentiles.split(",") if p.strip()]
    except ValueError:
        raise HTTPException(400, f"Geçersiz percentiles: {percentiles}")
    if not all(0 <= p <= 100 for p in pct_list):
        raise HTTPException(400, "Percentiller 0-100 aralığında olmalıdır.")
    if len(pct_list) > 7:
        raise HTTPException(400, "En fazla 7 percentil belirtebilirsiniz.")

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
