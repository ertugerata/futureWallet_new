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

import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

logger = logging.getLogger("futurewallet")
from config import ALLOWED_HOSTS, ALLOWED_ORIGINS, API_TOKEN, DEBUG
from services.benchmark_service import (
    compare_to_benchmark as srv_compare_to_benchmark,
)
from services.benchmark_service import (
    compute_real_return,
    get_current_market_prices,
)
from services.counterfactual_service import (
    create_shadow_position,
    get_shadow_positions,
    what_if_scenario,
)
from services.decision_service import (
    check_decision_target as svc_check_decision_target,
)
from services.decision_service import (
    close_decision as svc_close_decision,
)
from services.decision_service import (
    create_decision as svc_create_decision,
)
from services.decision_service import (
    decision_to_dict,
    get_sentiment_summary,
    get_status_summary,
)
from services.decision_service import (
    generate_ai_retrospective as svc_generate_ai_retrospective,
)
from services.decision_service import (
    get_decision as svc_get_decision,
)
from services.decision_service import (
    list_decisions as svc_list_decisions,
)
from services.decision_service import (
    update_decision as svc_update_decision,
)
from services.ledger_service import (
    InsufficientBalanceError,
    _guess_asset_type,
    time_travel_portfolio,
)
from services.ledger_service import (
    add_transaction as srv_add_transaction,
)
from services.ledger_service import (
    get_portfolio_snapshot as srv_get_portfolio_snapshot,
)
from services.ledger_service import (
    get_transactions as srv_get_transactions,
)
from services.ledger_service import (
    void_transaction as srv_void_transaction,
)
from services.pocketbase import get_client
from services.simulation_service import (
    generate_risk_narrative as srv_generate_risk_narrative,
)
from services.simulation_service import (
    monte_carlo_simulation,
)
from services.simulation_service import (
    stress_test as srv_stress_test,
)

# ---------------------------------------------------------------------------
# Auth bağımlılığı (Prompt 1)
# ---------------------------------------------------------------------------


_default_user_cache: dict[str, str] = {}


def _get_or_create_default_user() -> str:
    """API_TOKEN veya test amaçlı varsayılan PB kullanıcısı."""
    try:
        from services.pb import get_admin_client

        client = get_admin_client()
        cache_key = client.base_url
        if cache_key in _default_user_cache:
            cached_id = _default_user_cache[cache_key]
            try:
                client.collection("users").get_one(cached_id)
                return cached_id
            except Exception:
                pass

        email = "test_default@futurewallet.test"
        users = client.collection("users").get_full_list(query_params={"filter": f'email = "{email}"'})
        if users:
            uid = str(users[0].id)
        else:
            rec = client.collection("users").create(
                {
                    "email": email,
                    "password": "TestPass123!@Pass",
                    "passwordConfirm": "TestPass123!@Pass",
                }
            )
            uid = str(rec.id)
        _default_user_cache[cache_key] = uid
        return uid
    except Exception as exc:
        logger.error("Default test kullanıcısı oluşturulamadı: %s", exc)
        return "unknown"


def _extract_user_id(request: Request) -> str:
    """İstekten doğrulanmış user_id'yi alır (Prompt 6)."""
    return getattr(request.state, "user_id", None) or request.headers.get("X-User-ID") or _get_or_create_default_user()


def verify_api_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Yetkisiz: token yok")
    token = auth_header[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Yetkisiz: geçersiz token")

    # 1. API_TOKEN kontrolü (legacy / test uyumluluğu)
    if API_TOKEN and token == API_TOKEN:
        uid = _get_or_create_default_user()
        request.state.user_id = uid
        return uid

    # 2. PocketBase JWT token doğrulaması (Prompt 6)
    try:
        from services.pb import get_user_client

        user_client = get_user_client(token)
        auth_data = user_client.collection("users").auth_refresh()
        uid = str(auth_data.record.id)
        request.state.user_id = uid
        request.state.user_client = user_client
        return uid
    except Exception:
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
    # Time window reset
    if now >= entry["reset_at"]:
        entry["count"] = 0
        entry["reset_at"] = now + 60
    entry["count"] += 1
    entry["last"] = now
    if entry["count"] > 5:
        raise HTTPException(status_code=429, detail="Hız sınırı aşıldı. Lütfen bekleyin.")


_RETRO_RATE_LIMITS: dict = {}


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
    rationale: str | None = Field(
        None, max_length=5000, description="Karar gerekçesi (max 5000 karakter)"
    )
    sentiment: (
        Literal["FOMO", "STRATEGIC", "PANIC", "DIVIDEND", "OPPORTUNITY"] | None
    ) = Field(
        None,
        description="FOMO | STRATEGIC | PANIC | DIVIDEND | OPPORTUNITY",
    )
    target_price: float | None = Field(None, gt=0, description="Hedef fiyat (pozitif)")
    target_date: date | None = Field(None, description="Hedef tarih (ISO YYYY-MM-DD)")
    decision_date: date | None = Field(
        None, description="Karar tarihi (ISO YYYY-MM-DD; geçmiş olabilir, gelecek yok)"
    )
    track_shadow: bool = Field(
        False,
        description="True → SELL kararında HELD_INSTEAD gölge pozisyonu otomatik oluştur",
    )
    transaction_id: str | None = Field(None, max_length=36, description="İşlem ID (opsiyonel)")

    @field_validator("sentiment", mode="before")
    @classmethod
    def normalize_sentiment(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            v = v.upper()
            if v not in (
                "FOMO",
                "STRATEGIC",
                "PANIC",
                "DIVIDEND",
                "OPPORTUNITY",
            ):
                raise ValueError(
                    f"Geçersiz sentiment: {v}. Kabul: FOMO, STRATEGIC, PANIC, DIVIDEND, OPPORTUNITY"
                )
            return v
        return v


DecisionCreateRequest.model_rebuild()


# ShadowPositionCreateRequest (Prompt 12: gölge pozisyon oluşturma)
class ShadowPositionCreateRequest(BaseModel):
    decision_id: str = Field(..., description="İlgili karar ID")
    asset_symbol: str = Field(
        pattern=r"^[A-Z0-9.=^\-/]{1,20}$",
        max_length=20,
        description="Varlık sembolü",
    )
    shadow_type: Literal["HELD_INSTEAD", "BOUGHT_INSTEAD"] = Field(
        ..., description="HELD_INSTEAD | BOUGHT_INSTEAD"
    )
    entry_date: date | None = Field(None, description="Giriş tarihí (ISO YYYY-MM-DD; yoksa bugün)")
    entry_price: float | None = Field(
        None, ge=0, description="Giriş fiyatı (pozitif); yoksa güncel fiyat"
    )
    quantity: float | None = Field(None, ge=0, description="Miktar (pozitif); yoksa 0")
    exit_date: date | None = Field(None, description="Çıkış tarihi (opsiyonel)")
    asset_type: str | None = Field(
        None,
        max_length=50,
        description="Varlık türü (crypto, stock_tr, stock_us, commodity, forex, cash)",
    )

    @field_validator("entry_date", "exit_date", mode="before")
    @classmethod
    def empty_date_to_none(cls, v: Any) -> date | None:
        if v is None or v == "":
            return None
        return v


ShadowPositionCreateRequest.model_rebuild()


class DecisionUpdateRequest(BaseModel):
    rationale: str | None = Field(
        None, max_length=5000, description="Yeni gerekçе (max 5000 karakter)"
    )
    sentiment: (
        Literal["FOMO", "STRATEGIC", "PANIC", "DIVIDEND", "OPPORTUNITY"] | None
    ) = Field(None, description="FOMO | STRATEGIC | PANIC | DIVIDEND | OPPORTUNITY")
    target_price: float | None = Field(None, gt=0)
    target_date: date | None = Field(None, description="Yeni hedef tarih")
    status: Literal["OPEN", "REVIEWED", "EXPIRED", "CLOSED"] | None = Field(
        None, description="OPEN | REVIEWED | EXPIRED | CLOSED"
    )

    @field_validator("sentiment", mode="before")
    @classmethod
    def normalize_sentiment(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            v = v.upper()
            if v not in (
                "FOMO",
                "STRATEGIC",
                "PANIC",
                "DIVIDEND",
                "OPPORTUNITY",
            ):
                raise ValueError(f"Geçersiz sentiment: {v}")
            return v
        return v

    @field_validator("target_date", mode="before")
    @classmethod
    def empty_date_to_none(cls, v: Any) -> date | None:
        if v is None or v == "":
            return None
        return v


DecisionUpdateRequest.model_rebuild()


class DecisionsListRequest(BaseModel):
    status: Literal["OPEN", "REVIEWED", "EXPIRED", "CLOSED"] | None = None
    sentiment: str | None = None
    asset_symbol: str | None = None
    action: Literal["BUY", "SELL", "HOLD"] | None = None


DecisionsListRequest.model_rebuild()
# App
# ---------------------------------------------------------------------------

async def _init_pocketbase() -> None:
    """PocketBase collections validation and migration runner.
    Uses the admin client to verify required collections exist and, if missing,
    runs the migration scripts located in ``pb_migrations``.
    """
    try:
        from services.pb import get_admin_client, verify_collections
        client = get_admin_client()
        try:
            verify_collections(client)
        except Exception:
            # Run migrations via PocketBase binary.
            import os
            import subprocess
            # Resolve binary path relative to project root.
            pb_bin = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pb_bin", "pocketbase"))
            if not os.path.isfile(pb_bin):
                raise RuntimeError("PocketBase binary not found for migrations")
            # Ensure PocketBase server is running (checked later in lifecycle).
            # Execute migration command.
            subprocess.run([pb_bin, "migrate"], check=True)
            # Re‑verify after migration.
            verify_collections(client)
    except Exception as exc:
        logger.error("PocketBase initialization failed: %s", exc)
        raise


async def _check_pb_connection() -> bool:
    """PocketBase bağlantısını kontrol et."""
    try:
        from services.pb import get_admin_client

        client = get_admin_client()
        return bool(client.auth_store.is_valid)
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail-closed: API_TOKEN kontrolü
    if not API_TOKEN and not DEBUG:
        raise RuntimeError(
            "API_TOKEN boş ve DEBUG=false — fail-closed. Lütfen API_TOKEN ayarlayın."
        )
    # PocketBase koleksiyonlarını başlat
    await _init_pocketbase()
    yield

app = FastAPI(
    title="FutureWallet API",
    description="Event-Sourcing portföy, karar günlüğü ve makro simülasyon API'si",
    version="0.1.0",
    lifespan=lifespan,
)

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
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]
    if ALLOWED_ORIGINS
    else [],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[h.strip() for h in ALLOWED_HOSTS.split(",") if h.strip()]
    if ALLOWED_HOSTS
    else [],
)

# ---------------------------------------------------------------------------
# Health & root
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    pb_ok = await _check_pb_connection()
    return {"status": "ok", "pb": "ok" if pb_ok else "down"}

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




# ---------------------------------------------------------------------------
# Portfolio endpoints
# ---------------------------------------------------------------------------


@app.get("/api/portfolio/snapshot", dependencies=[Depends(verify_api_token)])
async def portfolio_snapshot(
    request: Request,
    as_of: date | None = Query(None, alias="date", description="ISO YYYY-MM-DD. Yoksa bugün."),
):
    """Belirtilen tarihteki portföy snapshot'ı. PB transactions collection'undan hesaplanır."""
    user_id = _extract_user_id(request)
    return srv_get_portfolio_snapshot(user_id=user_id, as_of=as_of)


@app.get("/api/portfolio/time-travel", dependencies=[Depends(verify_api_token)])
async def portfolio_time_travel(
    request: Request,
    t_start: date = Query(..., description="ISO YYYY-MM-DD başlangıç tarihi"),
    t_target: date | None = Query(None, description="ISO YYYY-MM-DD hedef tarih. Yoksa bugün."),
):
    """T_start dağılımını T_target fiyatlarıyla değerlendirir. PB transactions collection'undan hesaplanır."""
    user_id = _extract_user_id(request)
    target = t_target or date.today()
    return time_travel_portfolio(user_id=user_id, t_start=t_start, t_target=target)


@app.get("/api/portfolio/real-valuation", dependencies=[Depends(verify_api_token)])
async def portfolio_real_valuation(
    request: Request,
    date_from: date = Query(..., description="ISO YYYY-MM-DD başlangıç"),
    date_to: date = Query(..., description="ISO YYYY-MM-DD bitiş"),
    nominal_start: float = Query(..., description="T_start nominal portföy değeri"),
    nominal_end: float | None = Query(
        None, description="T_end nominal portföy değeri. Yoksa snapshot'dan al."
    ),
    cpi_type: str = Query("tr", description="tr | us"),
):
    """Nominal ve reel (enflasyondan arındırılmış) getiri hesaplama. PB macro_data'dan CPI okur."""
    user_id = _extract_user_id(request)
    nominal_end_val: float = nominal_end if nominal_end is not None else nominal_start

    if nominal_end is None:
        snap = srv_get_portfolio_snapshot(user_id=user_id, as_of=date_to)
        nominal_end_val = snap["total_value"]

    result = compute_real_return(
        nominal_start,
        nominal_end_val,
        date_from,
        date_to,
        cpi_type=cpi_type,
    )
    result["current_market"] = get_current_market_prices()
    return result


@app.get("/api/portfolio/value-series", dependencies=[Depends(verify_api_token)])
async def portfolio_value_series(
    request: Request,
    start_date: date = Query(..., description="Başlangıç tarihi (ISO YYYY-MM-DD)"),
    end_date: date = Query(..., description="Bitiş tarihi (ISO YYYY-MM-DD)"),
    step: str = Query("daily", description="daily | weekly | monthly"),
):
    """Belirtilen tarih aralığında portföy değerleri serisi (Prompt 9).

    Returns:
        {
            "series": [{"date": "YYYY-MM-DD", "value": float}, ...],
            "start_value": float,
            "end_value": float,
            "min_value": float,
            "max_value": float,
            "currency": "TRY"
        }
    """
    user_id = _extract_user_id(request)

    if start_date > end_date:
        raise HTTPException(400, "start_date end_date'ten büyük olamaz")

    # Tarih aralığını step'e göre filtrele
    dates = []
    current = start_date
    if step == "weekly":
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=7)
    elif step == "monthly":
        while current <= end_date:
            dates.append(current)
            # Bir sonraki ayın ilk günü veya ~30 gün
            if current.month == 12:
                current = date(current.year + 1, 1, min(current.day, 28))
            else:
                current = date(current.year, current.month + 1, min(current.day, 28))
    else:  # daily
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)

    if len(dates) > 400:
        raise HTTPException(422, f"Nokta sayısı ({len(dates)}) sınırı aştı (maksimum 400). Lütfen step parametresini büyütün veya aralığı daraltın.")

    # Her tarihte snapshot al
    series = []
    for d in dates:
        snap = srv_get_portfolio_snapshot(user_id=user_id, as_of=d)
        series.append({"date": d.isoformat(), "value": snap["total_value"]})

    if not series:
        return {
            "series": [],
            "start_value": 0,
            "end_value": 0,
            "min_value": 0,
            "max_value": 0,
            "currency": "TRY",
        }

    values = [s["value"] for s in series]
    return {
        "series": series,
        "start_value": values[0],
        "end_value": values[-1],
        "min_value": min(values),
        "max_value": max(values),
        "currency": "TRY",
    }


# Decisions endpoints
# ---------------------------------------------------------------------------


@app.get("/api/decisions", dependencies=[Depends(verify_api_token)])
async def list_decisions_endpoint(
    status: str | None = Query(None),
    sentiment: str | None = Query(None),
    asset_symbol: str | None = Query(None),
    action: str | None = Query(None),
    limit: int | None = Query(None),
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
    """Yeni karar oluştur. user_id → X-User-ID header'ı veya 'unknown'.
    track_shadow=True ve action=SELL → HELD_INSTEAD gölge pozisyonu otomatik oluşturulur (Prompt 12)."""
    user_id = _extract_user_id(request)

    try:
        result = svc_create_decision(
            user_id=user_id,
            asset_symbol=body.asset_symbol,
            action=body.action,
            rationale=body.rationale,
            sentiment=body.sentiment,
            target_price=body.target_price,
            target_date=body.target_date,
            decision_date=body.decision_date,
            transaction_id=body.transaction_id,
        )

        # track_shadow: SELL kararında HELD_INSTEAD gölge pozisyonu oluştur
        if body.track_shadow and body.action.upper() == "SELL":
            create_shadow_position(
                user_id=user_id,
                decision_id=result["id"],
                asset_symbol=body.asset_symbol,
                shadow_type="HELD_INSTEAD",
                entry_price=body.target_price,
                quantity=1.0,
                entry_date=body.decision_date,
            )

        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/decisions/stats", dependencies=[Depends(verify_api_token)])
async def decisions_stats_endpoint(request: Request):
    """Sentiment ve action bazında karar istatistikleri (Prompt 13)."""
    uid = _extract_user_id(request)
    sentiment_summary = get_sentiment_summary(user_id=uid)
    status_summary = get_status_summary(user_id=uid)
    decisions = svc_list_decisions(limit=1000, user_id=uid)

    outcomes = [
        d["outcome_return_pct"] for d in decisions if d.get("outcome_return_pct") is not None
    ]
    N_OUTCOME_MIN = 3
    if len(outcomes) >= N_OUTCOME_MIN:
        outcomes_sorted = sorted(outcomes)
        n = len(outcomes_sorted)
        median_outcome = (
            outcomes_sorted[n // 2]
            if n % 2
            else ((outcomes_sorted[n // 2 - 1] + outcomes_sorted[n // 2]) / 2)
        )
        mean_outcome = sum(outcomes) / n
        stats = {
            "sentiment_counts": sentiment_summary,
            "status_counts": status_summary,
            "outcome": {
                "count": n,
                "mean": round(mean_outcome, 4),
                "median": round(median_outcome, 4),
                "min": round(min(outcomes), 4),
                "max": round(max(outcomes), 4),
            },
            "insufficient_data": False,
        }
    else:
        stats = {
            "sentiment_counts": sentiment_summary,
            "status_counts": status_summary,
            "outcome": {"count": len(outcomes)},
            "insufficient_data": True,
        }
    return stats


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


@app.get(
    "/api/decisions/{decision_id}/target-check",
    dependencies=[Depends(verify_api_token)],
)
async def decision_target_check_endpoint(decision_id: str):
    """Kararın hedef fiyat/vade gerçekleşme kontrolü. PB decisions collection'undan."""
    result = svc_check_decision_target(decision_id)
    if "error" in result:
        return JSONResponse(status_code=404, content=result)
    return result


@app.post(
    "/api/decisions/{decision_id}/retrospective",
    dependencies=[Depends(verify_api_token), Depends(check_retrospective_rate_limit)],
)
async def generate_retrospective_endpoint(decision_id: str):
    """Bir karar için AI post-mortem (retrospektif) oluşturur. PB decisions collection'unda kaydeder."""
    return svc_generate_ai_retrospective(decision_id)


# ---------------------------------------------------------------------------
# Counterfactual / What-If endpoint'ler (Prompt 12: PB geçişli service)
# ---------------------------------------------------------------------------


@app.get("/api/counterfactual", dependencies=[Depends(verify_api_token)])
async def counterfactual_endpoint(
    decision_id: str = Query(..., description="Karar ID"),
    as_of: date | None = Query(None, description="ISO YYYY-MM-DD. Yoksa bugün."),
):
    """What-If senaryosu: decision_id ile gölge portföy kıyaslaması (PB)."""
    as_of_date = as_of or date.today()
    result = what_if_scenario(decision_id, as_of=as_of_date)
    if "error" in result:
        return JSONResponse(status_code=404, content=result)
    return result


@app.post(
    "/api/counterfactual/shadow-positions",
    status_code=201,
    dependencies=[Depends(verify_api_token)],
)
async def create_shadow_position_endpoint(
    body: ShadowPositionCreateRequest,
    request: Request,
):
    """Yeni gölge pozisyon oluştur (Prompt 12)."""
    user_id = _extract_user_id(request)
    try:
        result = create_shadow_position(
            user_id=user_id,
            decision_id=body.decision_id,
            asset_symbol=body.asset_symbol,
            shadow_type=body.shadow_type,
            entry_date=body.entry_date,
            entry_price=body.entry_price,
            quantity=body.quantity,
            exit_date=body.exit_date,
            asset_type=body.asset_type,
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/counterfactual/shadow-positions", dependencies=[Depends(verify_api_token)])
async def list_shadow_positions_endpoint(
    decision_id: str | None = Query(None, description="Karar ID filter"),
    asset_symbol: str | None = Query(None, description="Varlık sembolü filter"),
):
    """Gölge pozisyon listesi (filter ile)."""
    return get_shadow_positions(
        decision_id=decision_id,
        asset_symbol=asset_symbol,
    )


@app.delete(
    "/api/counterfactual/shadow-positions/{position_id}",
    dependencies=[Depends(verify_api_token)],
)
async def delete_shadow_position_endpoint(position_id: str, request: Request):
    """Gölge pozisyonunu sil (PB shadow_portfolios)."""
    _ = _extract_user_id(request)
    try:
        client = get_client()
        sp_coll = client.collection("shadow_portfolios")
        sp_coll.delete(position_id)
        return {"status": "deleted", "position_id": position_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/decisions/{decision_id}", dependencies=[Depends(verify_api_token)])
async def delete_decision_endpoint(decision_id: str, request: Request):
    """Kararı sil (bağlı gölge pozisyonlar cascade silinir; transaction etkilenmez)."""
    _ = _extract_user_id(request)
    try:
        client = get_client()
        decisions_coll = client.collection("decisions")
        decisions_coll.delete(decision_id)
        return {"status": "deleted", "decision_id": decision_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/simulation/monte-carlo", dependencies=[Depends(verify_api_token)])
async def monte_carlo_endpoint(
    request: Request,
    assets: str = Query(..., description="Virgülle ayrılmış semboller (örn: BTC,ETH,GC=F)"),
    days: int = Query(
        126,
        ge=1,
        le=756,
        description="Gün sayısı (varsayılan 126 = 6 ay, max 756 = 3 yıl)",
    ),
    simulations: int = Query(
        10000,
        ge=100,
        le=20000,
        description="Patika sayısı (varsayılan 10,000, aralık 100-20000)",
    ),
    percentiles: str = Query("5,50,95", description="Percentiller (örn: 5,50,95)"),
    seed: int | None = Query(None, description="RNG seed (opsiyonel)"),
):
    """Monte Carlo simülasyonu: portfolio gelecek değer dağılımları."""
    asset_list: list[dict] = []
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

    user_id = _extract_user_id(request)
    result = monte_carlo_simulation(
        user_id=user_id,
        asset_list=asset_list,
        days=days,
        n_simulations=simulations,
        percentiles=pct_list,
        seed=seed,
    )
    return result


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
    timestamp: date | None = Field(None, description="İşlem tarihi (opsiyonel)")

    @field_validator("tx_type", mode="before")
    @classmethod
    def normalize_tx_type(cls, v: str) -> str:
        if v is None:
            return "BUY"
        return v.upper()


TransactionCreateRequest.model_rebuild()


@app.post("/api/transactions", status_code=201, dependencies=[Depends(verify_api_token)])
async def create_transaction_endpoint(
    body: TransactionCreateRequest,
    request: Request,
):
    """Yeni işlem kaydı ekler (event log'a yaz)."""
    user_id = _extract_user_id(request)

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
    except InsufficientBalanceError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/transactions", dependencies=[Depends(verify_api_token)])
async def list_transactions_endpoint(
    request: Request,
    asset_symbol: str | None = Query(None),
    tx_type: str | None = Query(None),
    limit: int | None = Query(None),
):
    """İşlem listesi (filter ile)."""
    user_id = _extract_user_id(request)

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
    user_id = _extract_user_id(request)

    try:
        srv_void_transaction(
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
    user_id = _extract_user_id(request)
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
    shocks: dict[str, float] | None = Field(
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
    simulation_result: dict | None = Field(
        None, description="Monte Carlo simülasyon sonucu (opsiyonel)"
    )
    portfolio_context: dict | None = Field(None, description="Portföy bağlamı (opsiyonel)")


NarrativeRequest.model_rebuild()


@app.post("/api/simulation/narrative", dependencies=[Depends(verify_api_token)])
async def narrative_endpoint(body: NarrativeRequest):
    """Monte Carlo / stres test sonucu için Türkçe risk anlatısı."""
    try:
        result = srv_generate_risk_narrative(
            simulation_result=body.simulation_result,
            context=body.portfolio_context,
        )
        return {"narrative": result}
    except Exception as e:
        raise HTTPException(500, str(e))
