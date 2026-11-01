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
from db import init_db
from services.benchmark_service import (
    compare_to_benchmark as srv_compare_to_benchmark,
    compute_real_return,
    get_current_market_prices,
)
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
    add_transaction as srv_add_transaction,
    get_portfolio_snapshot as srv_get_portfolio_snapshot,
    get_transactions as srv_get_transactions,
    time_travel_portfolio,
    void_transaction as srv_void_transaction,
)
from services.simulation_service import (
    monte_carlo_simulation,
    stress_test as srv_stress_test,
    generate_risk_narrative as srv_generate_risk_narrative,
)


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
    dependencies=[Depends(verify_api_token)] if API_TOKEN else [],
)


@app.on_event("startup")
async def _check_api_token_on_startup():
    """Fail-closed: API_TOKEN boşsa ve DEBUG kapalıysa uygulamayı durdur (Prompt 1)."""
    if not API_TOKEN and not DEBUG:
        raise RuntimeError("API_TOKEN boş ve DEBUG=false — fail-closed. Lütfen API_TOKEN ayarlayın.")



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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()] if ALLOWED_ORIGINS else [],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in ALLOWED_HOSTS.split(",") if h.strip()] if ALLOWED_HOSTS else [])

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

@app.get("/api/portfolio/snapshot", dependencies=[Depends(verify_api_token)])
async def portfolio_snapshot(
    request: Request,
    as_of: Optional[date] = Query(None, alias="date", description="ISO YYYY-MM-DD. Yoksa bugün."),
):
    """Belirtilen tarihteki portföy snapshot'ı. PB transactions collection'undan hesaplanır."""
    user_id = request.headers.get("X-User-ID", "unknown")
    return srv_get_portfolio_snapshot(user_id=user_id, as_of=as_of)


@app.get("/api/portfolio/time-travel", dependencies=[Depends(verify_api_token)])
async def portfolio_time_travel(
    request: Request,
    t_start: date = Query(..., description="ISO YYYY-MM-DD başlangıç tarihi"),
    t_target: Optional[date] = Query(None, description="ISO YYYY-MM-DD hedef tarih. Yoksa bugün."),
):
    """T_start dağılımını T_target fiyatlarıyla değerlendirir. PB transactions collection'undan hesaplanır."""
    user_id = request.headers.get("X-User-ID", "unknown")
    target = t_target or date.today()
    return time_travel_portfolio(user_id=user_id, t_start=t_start, t_target=target)


@app.get("/api/portfolio/real-valuation", dependencies=[Depends(verify_api_token)])
async def portfolio_real_valuation(
    request: Request,
    date_from: date = Query(..., description="ISO YYYY-MM-DD başlangıç"),
    date_to: date = Query(..., description="ISO YYYY-MM-DD bitiş"),
    nominal_start: float = Query(..., description="T_start nominal portföy değeri"),
    nominal_end: Optional[float] = Query(None, description="T_end nominal portföy değeri. Yoksa snapshot'dan al."),
    cpi_type: str = Query("tr", description="tr | us"),
):
    """Nominal ve reel (enflasyondan arındırılmış) getiri hesaplama. PB macro_data'dan CPI okur."""
    user_id = request.headers.get("X-User-ID", "unknown")
    nominal_end_val: float = nominal_end if nominal_end is not None else nominal_start

    if nominal_end is None:
        snap = srv_get_portfolio_snapshot(user_id=user_id, as_of=date_from)
        nominal_end_val = snap["total_value"]

    result = compute_real_return(
        nominal_start, nominal_end_val, date_from, date_to, cpi_type=cpi_type,
    )
    result["current_market"] = get_current_market_prices()
    return result


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
    """Filtrelenmiş karar listesi. PB decisions collection'undan."""
    return svc_list_decisions(
        status=status,
        sentiment=sentiment,
        asset_symbol=asset_symbol,
        action=action,
        limit=limit,
    )


@app.post("/api/decisions", status_code=201, dependencies=[Depends(verify_api_token)])
async def create_decision_endpoint(
    body: DecisionCreateRequest,
    request: Request,
):
    """Yeni karar oluştur. user_id → X-User-ID header'ı veya 'unknown'."""
    user_id = request.headers.get("X-User-ID", "unknown")

    try:
        result = svc_create_decision(
            user_id=user_id,
            asset_symbol=body.asset_symbol,
            action=body.action,
            rationale=body.rationale,
            sentiment=body.sentiment,
            target_price=body.target_price,
            target_date=body.target_date,
            transaction_id=body.transaction_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/api/decisions/{decision_id}", dependencies=[Depends(verify_api_token)])
async def get_decision_endpoint(decision_id: str):
    """ID ile tek karar. PB decisions collection'undan."""
    dec = svc_get_decision(decision_id)
    if dec is None:
        return JSONResponse(status_code=404, content={"error": "decision not found"})
    return decision_to_dict(dec)


@app.put("/api/decisions/{decision_id}", dependencies=[Depends(verify_api_token)])
async def update_decision_endpoint(
    decision_id: str,
    body: DecisionUpdateRequest,
):
    """Karar alanlarını güncelle (None → değiştirme). PB decisions collection'unda."""
    dec = svc_update_decision(
        decision_id,
        rationale=body.rationale,
        sentiment=body.sentiment,
        target_price=body.target_price,
        target_date=body.target_date,
        status=body.status,
    )
    if dec is None:
        return JSONResponse(status_code=404, content={"error": "decision not found"})
    return decision_to_dict(dec)


@app.post("/api/decisions/{decision_id}/close", dependencies=[Depends(verify_api_token)])
async def close_decision_endpoint(decision_id: str):
    """Kararı REVIEWED yap. PB decisions collection'unda."""
    dec = svc_close_decision(decision_id)
    if dec is None:
        return JSONResponse(status_code=404, content={"error": "decision not found"})
    return decision_to_dict(dec)


@app.get("/api/decisions/{decision_id}/target-check", dependencies=[Depends(verify_api_token)])
async def decision_target_check_endpoint(decision_id: str):
    """Kararın hedef fiyat/vade gerçekleşme kontrolü. PB decisions collection'undan."""
    result = svc_check_decision_target(decision_id)
    if "error" in result:
        return JSONResponse(status_code=404, content=result)
    return result


@app.post("/api/decisions/{decision_id}/retrospective",
          dependencies=[Depends(verify_api_token), Depends(check_retrospective_rate_limit)])
async def generate_retrospective_endpoint(decision_id: str):
    """Bir karar için AI post-mortem (retrospektif) oluşturur. PB decisions collection'unda kaydeder."""
    return svc_generate_ai_retrospective(decision_id)


# ---------------------------------------------------------------------------
# Placeholder endpoint'ler (henüz implement edilmemiş service'ler)
# ---------------------------------------------------------------------------

@app.get("/api/counterfactual", dependencies=[Depends(verify_api_token)])
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


@app.get("/api/simulation/monte-carlo", dependencies=[Depends(verify_api_token)])
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
@app.post("/api/transactions", status_code=201, dependencies=[Depends(verify_api_token)])
async def create_transaction_endpoint(
    body: TransactionCreateRequest,
    request: Request,
):
    """Yeni işlem kaydı ekler (event log'a yaz)."""
    user_id = request.headers.get("X-User-ID", "unknown")

    try:
        result = srv_add_transaction(
            user_id=user_id,
            asset_symbol=body.asset_symbol,
            tx_type=body.tx_type,
            quantity=body.quantity,
            price=body.price,
            fee=body.fee,
            timestamp=body.timestamp,
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


class TransactionCreateRequest(BaseModel):
    asset_symbol: str = Field(
        pattern=r"^[A-Z0-9.=^\-/]{1,20}$",
        max_length=20,
        description="Varlık sembolü",
    )
    tx_type: Literal["BUY", "SELL", "DIVIDEND", "CASH_IN", "CASH_OUT"]
    quantity: float = Field(gt=0, description="Miktar")
    price: float = Field(ge=0, description="Birim fiyat")
    fee: float = Field(ge=0, default=0.0, description="İşlem ücreti")
    timestamp: Optional[date] = Field(None, description="İşlem tarihi (opsiyonel)")

    @field_validator("tx_type", mode="before")
    @classmethod
    def normalize_tx_type(cls, v: str) -> str:
        if v is None:
            return "BUY"
        return v.upper()

TransactionCreateRequest.model_rebuild()


@app.get("/api/transactions", dependencies=[Depends(verify_api_token)])
async def list_transactions_endpoint(
    request: Request,
    asset_symbol: Optional[str] = Query(None),
    tx_type: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
):
    """İşlem listesi (filter ile)."""
    user_id = request.headers.get("X-User-ID", "unknown")

    try:
        result = srv_get_transactions(
            user_id=user_id,
            asset_symbol=asset_symbol,
            tx_type=tx_type,
            limit=limit,
        )
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/transactions/{transaction_id}", dependencies=[Depends(verify_api_token)])
async def delete_transaction_endpoint(
    transaction_id: str,
    request: Request,
):
    """İşlem kaydını voided yap (soft delete)."""
    user_id = request.headers.get("X-User-ID", "unknown")

    try:
        result = srv_void_transaction(
            user_id=user_id,
            transaction_id=transaction_id,
        )
        return {"status": "voided", "transaction_id": transaction_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/portfolio/benchmarks", dependencies=[Depends(verify_api_token)])
async def portfolio_benchmarks_endpoint(
    request: Request,
    date_from: date = Query(..., description="Başlangıç tarihi (ISO YYYY-MM-DD)"),
    date_to: date = Query(..., description="Bitiş tarihi (ISO YYYY-MM-DD)"),
):
    """Portföy performansını benchmark ile kıyaslar. PB transactions ve macro_data'dan hesaplanır."""
    user_id = request.headers.get("X-User-ID", "unknown")
    try:
        snap_start = srv_get_portfolio_snapshot(user_id=user_id, as_of=date_from)
        snap_end = srv_get_portfolio_snapshot(user_id=user_id, as_of=date_to)
        result = srv_compare_to_benchmark(
            portfolio_value_start=snap_start["total_value"],
            portfolio_value_end=snap_end["total_value"],
            date_start=date_from,
            date_end=date_to,
        )
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


class StressTestRequest(BaseModel):
    portfolio_value: float = Field(gt=0, description="Portföy başlangıç değeri")
    shocks: Optional[Dict[str, float]] = Field(
        None, description="Özel şoklar (key=senaryo adı, value=şok büyüklüğü)"
    )
    days: int = Field(252, ge=1, le=756, description="Gün sayısı")
    n_simulations: int = Field(1000, ge=100, le=200000, description="Patika sayısı")

StressTestRequest.model_rebuild()


@app.post("/api/simulation/stress-test", dependencies=[Depends(verify_api_token)])
async def stress_test_endpoint(body: StressTestRequest):
    """Makro şok senaryoları altında portföy değerlerini simüle eder."""
    try:
        result = srv_stress_test(
            portfolio_value=body.portfolio_value,
            shocks=body.shocks,
            days=body.days,
            n_simulations=body.n_simulations,
        )
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


class NarrativeRequest(BaseModel):
    simulation_result: Optional[Dict] = Field(
        None, description="Monte Carlo simülasyon sonucu (opsiyonel)"
    )
    portfolio_context: Optional[Dict] = Field(
        None, description="Portföy bağlamı (opsiyonel)"
    )

NarrativeRequest.model_rebuild()


@app.post("/api/simulation/narrative", dependencies=[Depends(verify_api_token)])
async def narrative_endpoint(body: NarrativeRequest):
    """Monte Carlo / stres test sonucu için Türkçe risk anlatısı."""
    try:
        result = srv_generate_risk_narrative(
            simulation_result=body.simulation_result,
            portfolio_context=body.portfolio_context,
        )
        return {"narrative": result}
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# Helper: decision → dict (aynı logic decision_service.decision_to_dict)
def _parse_pb_date(value) -> Optional[date]:
    """PB DateTime string → datetime.date."""
    if value is None:
        return None
    s = str(value)
    try:
        if "T" in s:
            return date.fromisoformat(s.split("T")[0])
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def decision_to_dict(decision) -> dict:
    """PB decision record veya dict → flat dict."""
    if hasattr(decision, "id"):
        return {
            "id":               decision.id,
            "date":             _parse_pb_date(getattr(decision, "date", None)),
            "asset_symbol":     getattr(decision, "asset_symbol", ""),
            "action":           getattr(decision, "action", ""),
            "rationale":        getattr(decision, "rationale", None),
            "sentiment":        getattr(decision, "sentiment", None),
            "target_price":     getattr(decision, "target_price", None),
            "target_date":      _parse_pb_date(getattr(decision, "target_date", None)),
            "status":           getattr(decision, "status", "OPEN"),
            "ai_retrospective": getattr(decision, "ai_retrospective", None),
            "transaction_id":   getattr(decision, "transaction_id", None),
        }
    # dict (ordinal dict) ise doğrudan kullan
    return {
        "id":               decision.get("id"),
        "date":             decision.get("date"),
        "asset_symbol":     decision.get("asset_symbol", ""),
        "action":           decision.get("action", ""),
        "rationale":        decision.get("rationale"),
        "sentiment":        decision.get("sentiment"),
        "target_price":     decision.get("target_price"),
        "target_date":      decision.get("target_date"),
        "status":           decision.get("status", "OPEN"),
        "ai_retrospective": decision.get("ai_retrospective"),
        "transaction_id":   decision.get("transaction_id"),
    }
