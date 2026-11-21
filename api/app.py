"""
FutureWallet - FastAPI Uygulama Çekirdeği (Endpoint Implementasyonları)

Endpoint'ler:
  /api/portfolio/snapshot       → ledger_service.get_portfolio_snapshot
  /api/portfolio/time-travel    → ledger_service.time_travel_portfolio
  /api/portfolio/real-valuation → benchmark_service.compute_real_return
  /api/decisions                → decision_service CRUD
  /api/decisions/{id}/close     → decision_service.close_decision
  /api/decisions/{id}/target-check → decision_service.check_decision_target
  /api/counterfactual           → counterfactual_service (gölge portföy kıyaslaması)
  /api/simulation/monte-carlo   → simulation_service (Monte Carlo simülasyonu)

TODO.md 4.1.
"""

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated, Any, Literal

try:
    from apscheduler.schedulers.background import BackgroundScheduler

    _APSCHEDULER_AVAILABLE = True
except ImportError:
    _APSCHEDULER_AVAILABLE = False

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

logger = logging.getLogger("futurewallet")
from config import ALLOWED_HOSTS, ALLOWED_ORIGINS, DEBUG
from services.asset_types import _guess_asset_type, infer_portfolio_currency
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
    delete_decision as svc_delete_decision,
)
from services.decision_service import (
    evaluate_decision as svc_evaluate_decision,
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
from services.enums import (
    Action,
    DecisionStatus,
    Sentiment,
    ShadowType,
    TransactionType,
)
from services.ledger_service import (
    InsufficientBalanceError,
    get_portfolio_snapshots,
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
from services.pb import get_client
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
# Auth bağımlılığı (Prompt 6): PB JWT — API_TOKEN / X-User-ID yok
# ---------------------------------------------------------------------------


@dataclass
class CurrentUser:
    """Doğrulanmış PB kullanıcısı: id, e-posta, JWT ve kullanıcı bazlı PB istemcisi."""

    id: str
    email: str
    token: str
    pb: Any


def get_current_user(request: Request) -> CurrentUser:
    """Authorization: Bearer <PB_JWT> başlığını auth_refresh ile doğrular; geçersizse 401."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Yetkisiz: token yok")
    token = auth_header[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Yetkisiz: token yok")

    from services.pb import get_user_client

    user_client = get_user_client(token)
    try:
        auth_data = user_client.collection("users").auth_refresh()
        record = auth_data.record
    except Exception:
        raise HTTPException(status_code=401, detail="Yetkisiz: geçersiz token")

    request.state.user_id = str(record.id)
    request.state.user_client = user_client
    return CurrentUser(
        id=str(record.id),
        email=str(getattr(record, "email", "") or ""),
        token=auth_data.token,
        pb=user_client,
    )


def _extract_user_id(request: Request) -> str:
    """get_current_user tarafından doğrulanmış user_id."""
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Yetkisiz: kullanıcı doğrulanamadı")
    return str(uid)


_RETRO_RATE_LIMITS: dict = {}


def reset_rate_limits() -> None:
    """Testler için hız sınırı sayaçlarını sıfırlar (Prompt 6)."""
    _RETRO_RATE_LIMITS.clear()


def _prune_rate_limits(now: int | None = None) -> None:
    """Süresi dolmuş sayaç anahtarlarını atar — anahtar kullanıcı/karar ID'sinden türetilir,
    harita sınırsız büyümesin (review #6)."""
    now = int(time.time()) if now is None else now
    for k, entry in list(_RETRO_RATE_LIMITS.items()):
        if now >= entry["reset_at"]:
            _RETRO_RATE_LIMITS.pop(k, None)


def check_retrospective_rate_limit(
    request: Request, current: CurrentUser = Depends(get_current_user)
) -> None:
    """Retrospektif: kullanıcı + karar başına 60 sn'de 1 istek (Prompt 6)."""
    decision_id = request.path_params.get("decision_id", "")
    now = int(time.time())
    if len(_RETRO_RATE_LIMITS) > 1024:
        _prune_rate_limits(now)
    key = (current.id, decision_id)
    entry = _RETRO_RATE_LIMITS.get(key)
    if entry is not None and now < entry["reset_at"]:
        raise HTTPException(status_code=429, detail="Hız sınırı aşıldı. Lütfen bekleyin.")
    _RETRO_RATE_LIMITS[key] = {"count": 1, "reset_at": now + 60}


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Pydantic request / response model'leri
# ---------------------------------------------------------------------------

# PB autogenerate record ID biçimi ([a-z0-9]{15}); girdi doğrulaması uçlardan
# önce yapılır — servise/DB'ye biçimsiz ID inmez (review minörü #2).
PB_ID_PATTERN = r"^[a-z0-9]{15}$"
PbId = Annotated[str, Path(pattern=PB_ID_PATTERN)]


class DecisionCreateRequest(BaseModel):
    asset_symbol: str = Field(
        pattern=r"^[A-Z0-9.=^\-/]{1,20}$",
        max_length=20,
        description="Varlık sembolü (örn: BTC, GC=F, THYAO.IS)",
    )
    action: Literal[Action.BUY, Action.SELL, Action.HOLD]
    rationale: str | None = Field(
        None, max_length=5000, description="Karar gerekçesi (max 5000 karakter)"
    )
    sentiment: Literal[Sentiment.FOMO, Sentiment.STRATEGIC, Sentiment.PANIC, Sentiment.DIVIDEND, Sentiment.OPPORTUNITY] | None = Field(
        None,
        description="FOMO | STRATEGIC | PANIC | DIVIDEND | OPPORTUNITY",
    )
    target_price: float | None = Field(None, gt=0, description="Hedef fiyat (pozitif)")
    target_date: date | None = Field(None, description="Hedef tarih (ISO YYYY-MM-DD)")
    decision_date: date | None = Field(
        None, description="Karar tarihi (ISO YYYY-MM-DD; geçmiş olabilir, gelecek yok)"
    )

    @field_validator("decision_date")
    @classmethod
    def decision_date_not_future(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("decision_date gelecekte olamaz")
        return v

    track_shadow: bool = Field(
        False,
        description="True → SELL kararında HELD_INSTEAD gölge pozisyonu otomatik oluştur",
    )
    transaction_id: str | None = Field(
        None, pattern=PB_ID_PATTERN, description="İşlem ID (opsiyonel)"
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
                raise ValueError(
                    f"Geçersiz sentiment: {v}. Kabul: FOMO, STRATEGIC, PANIC, DIVIDEND, OPPORTUNITY"
                )
            return v
        return v


DecisionCreateRequest.model_rebuild()


# ShadowPositionCreateRequest (Prompt 12: gölge pozisyon oluşturma)
class ShadowPositionCreateRequest(BaseModel):
    decision_id: str = Field(..., pattern=PB_ID_PATTERN, description="İlgili karar ID")
    asset_symbol: str = Field(
        pattern=r"^[A-Z0-9.=^\-/]{1,20}$",
        max_length=20,
        description="Varlık sembolü",
    )
    shadow_type: Literal[ShadowType.HELD_INSTEAD, ShadowType.BOUGHT_INSTEAD] = Field(
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
    sentiment: Literal[Sentiment.FOMO, Sentiment.STRATEGIC, Sentiment.PANIC, Sentiment.DIVIDEND, Sentiment.OPPORTUNITY] | None = Field(
        None, description="FOMO | STRATEGIC | PANIC | DIVIDEND | OPPORTUNITY"
    )
    target_price: float | None = Field(None, gt=0)
    target_date: date | None = Field(None, description="Yeni hedef tarih")

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
    def normalize_target_date(cls, v: str | date | None) -> date | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                return datetime.strptime(v, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("target_date must be YYYY-MM-DD")
        return v


DecisionUpdateRequest.model_rebuild()


class DecisionsListRequest(BaseModel):
    status: Literal[DecisionStatus.OPEN, DecisionStatus.REVIEWED, DecisionStatus.EXPIRED, DecisionStatus.CLOSED] | None = None
    sentiment: str | None = None
    asset_symbol: str | None = None
    action: Literal[Action.BUY, Action.SELL, Action.HOLD] | None = None


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
            # Run migrations via PocketBase binary if available locally.
            import os
            import subprocess

            # Resolve binary path relative to project root.
            pb_bin = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "pb_bin", "pocketbase")
            )
            if os.path.isfile(pb_bin):
                subprocess.run([pb_bin, "migrate"], check=True)
                # Re‑verify after migration.
                verify_collections(client)
            else:
                raise
    except Exception as exc:
        logger.error("PocketBase initialization failed: %s", exc)
        raise


def _check_pb_connection() -> bool:
    """PocketBase bağlantısını kontrol et."""
    try:
        from services.pb import get_admin_client

        client = get_admin_client()
        return bool(client.auth_store.is_valid)
    except Exception:
        return False


import os
from datetime import datetime, timezone

import config

_scheduler: "BackgroundScheduler | None" = None


def _run_daily_macro_refresh() -> None:
    """Günlük macro_data yenileme job gövdesi (hatalar loglanır, scheduler'ı düşürmez)."""
    from services.benchmark_service import fetch_and_save_macro_data

    try:
        fetch_and_save_macro_data()
    except Exception as exc:
        logger.error("Günlük makro veri çekimi başarısız: %s", exc)


def _run_expire_decisions() -> None:
    """Vadesi geçmiş kararları EXPIRED yapma job'u (hatalar loglanır, scheduler'ı düşürmez)."""
    from services.decision_service import auto_close_expired_decisions

    try:
        closed = auto_close_expired_decisions()
        logger.info("expire_decisions job: %d karar EXPIRED yapıldı", len(closed))
    except Exception as exc:
        logger.error("expire_decisions job başarısız: %s", exc)

def _run_auto_retrospective() -> None:
    """EXPIRED ve retrospektifi olmayan kararlar için otomatik retrospektif üretir (P8)."""
    if not config.AUTO_RETROSPECTIVE:
        return

    from services.decision_service import generate_ai_retrospective
    from services.pb import get_admin_client

    try:
        admin = get_admin_client()
        # EXPIRED ve retrospektifi olmayan kararları bul
        records = admin.collection("decisions").get_full_list(
            query_params={
                "filter": "status = 'EXPIRED' && ai_retrospective = ''",
                "sort": "target_date",
            }
        )

        processed = 0
        for record in records:
            user_id = getattr(record, "user", None)
            if not user_id:
                continue

            # Kullanıcı başına günlük limit kontrolü
            from services.ai_service import _check_ai_rate_limit
            allowed, _ = _check_ai_rate_limit(user_id, "auto_retrospective")
            if not allowed:
                logger.warning("Kullanıcı %s: otomatik retrospektif günlük limiti aşıldı", user_id)
                continue

            decision_id = getattr(record, "id", None)
            if not decision_id:
                continue

            try:
                result = generate_ai_retrospective(
                    decision_id,
                    api_key=config.OPENROUTER_API_KEY,
                )
                if result:
                    processed += 1
                    logger.info("Otomatik retrospektif üretildi: decision=%s user=%s", decision_id, user_id)
                else:
                    logger.warning("Otomatik retrospektif üretilemedi: decision=%s", decision_id)
            except Exception as exc:
                logger.error("Otomatik retrospektif hatası (decision=%s): %s", decision_id, exc)

        logger.info("auto_retrospective job: %d retrospektif üretildi", processed)
    except Exception as exc:
        logger.error("auto_retrospective job başarısız: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):

    global _scheduler
    # Fail-closed: PB admin credential'ları config import'unda zorunlu (RuntimeError).
    # PocketBase koleksiyonlarını başlat
    await _init_pocketbase()
    # APScheduler: periyodik görevler (Prompt 11, 13)
    if config.ENABLE_SCHEDULER and _APSCHEDULER_AVAILABLE:
        # Çok worker koruması: yalnızca tek worker veya SCHEDULER_LEADER=true olan süreçte başlat
        web_concurrency = int(os.environ.get("WEB_CONCURRENCY", "1"))
        is_leader = os.environ.get("SCHEDULER_LEADER", "").lower() == "true"
        if web_concurrency > 1 and not is_leader:
            logger.warning(
                "WEB_CONCURRENCY=%d (>1) ve SCHEDULER_LEADER değil; APScheduler başlatılmıyor. "
                "Sadece bir süreçte SCHEDULER_LEADER=true ile çalıştırın.",
                web_concurrency,
            )
        else:
            _scheduler = BackgroundScheduler()
            first_run = datetime.now(timezone.utc) + timedelta(seconds=30)
            _scheduler.add_job(
                _run_expire_decisions,
                "interval",
                hours=24,
                id="expire_decisions",
                replace_existing=True,
                next_run_time=first_run,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=300,
            )
            # P11: günlük makro/benchmark veri çekimi (review #3)
            _scheduler.add_job(
                _run_daily_macro_refresh,
                "interval",
                hours=24,
                id="refresh_macro",
                replace_existing=True,
                next_run_time=first_run,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=300,
            )
            _scheduler.start()
            logger.info("APScheduler başlatıldı (ilk çalışma ~30 sn sonra).")
    yield
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler durduruldu.")


app = FastAPI(
    title="FutureWallet API",
    description="Event-Sourcing portföy, karar günlüğü ve makro simülasyon API'si",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
)


async def _add_security_headers(request: Request, call_next):
    """Tüm yanıtlara güvenlik başlıkları ekle (Prompt 2, 6).

    connect-src: PB JWT akışı için PocketBase origin'i zorunlu (P14); API çağrıları 'self'.
    script-src: Chart.js yerel olarak servis edilir (static/vendor/).
    """
    from urllib.parse import urlsplit

    pb = urlsplit(config.pb_browser_url())
    pb_origin = f"{pb.scheme}://{pb.netloc}" if pb.scheme and pb.netloc else ""
    connect_src = f"connect-src 'self' {pb_origin};" if pb_origin else "connect-src 'self';"
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        f"{connect_src} "
        "img-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # HTTPS arkasında HSTS (env kontrollü)
    if config.DEBUG is False:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # API yanıtlarında cache kontrol
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


MAX_BODY_SIZE = 64 * 1024  # 64 KB limit (Prompt 6 DoS protection)


async def _limit_request_size(request: Request, call_next):
    """64 KB istek gövdesi limiti middleware'i (Prompt 6).

    Content-Length varsa head-of-line kontrol; yoksa (chunked) gövde akıştan sayılır —
    başlık-trust tek başına bypass edilemez (review #2).
    """
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Payload Too Large: İstek gövdesi 64 KB sınırını aşıyor"},
                )
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "Geçersiz Content-Length başlığı"},
            )
    elif request.headers.get("transfer-encoding") == "chunked" and request.method in (
        "POST",
        "PUT",
        "PATCH",
    ):
        body = b""
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_BODY_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Payload Too Large: İstek gövdesi 64 KB sınırını aşıyor"},
                )
        request._body = body
    return await call_next(request)


app.add_middleware(BaseHTTPMiddleware, dispatch=_limit_request_size)
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
def health():
    pb_ok = _check_pb_connection()
    return {"status": "ok", "pb": "ok" if pb_ok else "down"}


@app.get("/")
def root():
    return {
        "name": "FutureWallet",
        "version": "0.1.0",
        "docs": "/docs" if DEBUG else None,
    }


from web_app import mount_web

mount_web(app)

# ---------------------------------------------------------------------------
# Helper: session lifecycle (try/commit/except/rollback/finally/close)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Portfolio endpoints
# ---------------------------------------------------------------------------


@app.get("/api/portfolio/snapshot", dependencies=[Depends(get_current_user)])
def portfolio_snapshot(
    request: Request,
    as_of: date | None = Query(None, alias="date", description="ISO YYYY-MM-DD. Yoksa bugün."),
):
    """Belirtilen tarihteki portföy snapshot'ı. PB transactions collection'undan hesaplanır."""
    user_id = _extract_user_id(request)
    return srv_get_portfolio_snapshot(user_id=user_id, as_of=as_of)


@app.get("/api/portfolio/time-travel", dependencies=[Depends(get_current_user)])
def portfolio_time_travel(
    request: Request,
    t_start: date = Query(..., description="ISO YYYY-MM-DD başlangıç tarihi"),
    t_target: date | None = Query(None, description="ISO YYYY-MM-DD hedef tarih. Yoksa bugün."),
):
    """T_start dağılımını T_target fiyatlarıyla değerlendirir. PB transactions collection'undan hesaplanır."""
    user_id = _extract_user_id(request)
    target = t_target or date.today()
    return time_travel_portfolio(user_id=user_id, t_start=t_start, t_target=target)


@app.get("/api/portfolio/real-valuation", dependencies=[Depends(get_current_user)])
def portfolio_real_valuation(
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

@app.get("/api/portfolio/value-series", dependencies=[Depends(get_current_user)])
def portfolio_value_series(
    request: Request,
    start_date: date = Query(..., description="Başlangıç tarihi (ISO YYYY-MM-DD)"),
    end_date: date = Query(..., description="Bitiş tarihi (ISO YYYY-MM-DD)"),
    step: str = Query("daily", description="daily | weekly | monthly"),
):
    """Belirtilen tarih aralığında portföy değerleri serisi (Prompt 9, P5: bulk snapshots).

    Returns:
        {
            "series": [{"date": "YYYY-MM-DD", "value": float}, ...],
            "start_value": float,
            "end_value": float,
            "min_value": float,
            "max_value": float,
            "currency": "TRY" | "USD" (varlık tabanına göre dinamik, P9)
        }
    """
    from services.ai_service import _check_ai_rate_limit

    user_id = _extract_user_id(request)

    if start_date > end_date:
        raise HTTPException(400, "start_date end_date'ten büyük olamaz")

    # Minimum start date (prevent year 1 dates)
    if start_date.year < 1900:
        raise HTTPException(422, "start_date 1900 veya sonrası olmalıdır")

    # Maximum range: 20 years
    max_end = date(start_date.year + 20, start_date.month, start_date.day)
    if end_date > max_end:
        raise HTTPException(422, "Tarih aralığı en fazla 20 yıl olabilir")

    # Nokta sayısını döngüden ÖNCE hesapla (P5: DoS koruması)
    day_delta = (end_date - start_date).days
    if step == "daily":
        point_count = day_delta + 1
    elif step == "weekly":
        point_count = day_delta // 7 + 1
    elif step == "monthly":
        point_count = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
    else:
        raise HTTPException(422, "step parametresi: daily | weekly | monthly olmalıdır")

    if point_count > 400:
        raise HTTPException(
            422,
            f"Nokta sayısı ({point_count}) sınırı aştı (maksimum 400). Lütfen step parametresini büyütün veya aralığı daraltın.",
        )

    # Value-series rate limit (P5: dk 10)
    allowed, retry_after = _check_ai_rate_limit(user_id, "value_series")
    if not allowed:
        raise HTTPException(status_code=429, detail="Value-series hız sınırı aşıldı", headers={"Retry-After": str(retry_after)})

    # Tarih aralığını step'e göre filtrele (artık güvenli)
    dates = []
    current = start_date
    if step == "weekly":
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=7)
    elif step == "monthly":
        while current <= end_date:
            dates.append(current)
            if current.month == 12:
                current = date(current.year + 1, 1, min(current.day, 28))
            else:
                current = date(current.year, current.month + 1, min(current.day, 28))
    else:  # daily
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)

    # Toplu snapshot hesapla (P5: N+1 elimination)
    snapshots = get_portfolio_snapshots(user_id=user_id, dates=dates)

    # Series oluştur; nakit kovası dışında tutulan sembolleri biriktir (P9 currency)
    series = []
    syms: set[str] = set()
    for d in dates:
        snap = snapshots.get(d)
        if snap:
            series.append({"date": d.isoformat(), "value": snap["total_value"]})
            syms.update(h["asset_symbol"] for h in snap["holdings"] if h.get("type") != "cash")

    currency = infer_portfolio_currency(sorted(syms))

    if not series:
        return {
            "series": [],
            "start_value": 0,
            "end_value": 0,
            "min_value": 0,
            "max_value": 0,
            "currency": currency,
        }

    values = [s["value"] for s in series]
    return {
        "series": series,
        "start_value": values[0],
        "end_value": values[-1],
        "min_value": min(values),
        "max_value": max(values),
        "currency": currency,
    }


# Decisions endpoints
# ---------------------------------------------------------------------------


@app.get("/api/decisions", dependencies=[Depends(get_current_user)])
def list_decisions_endpoint(
    request: Request,
    status: str | None = Query(None),
    sentiment: str | None = Query(None),
    asset_symbol: str | None = Query(None),
    action: str | None = Query(None),
    limit: int | None = Query(None),
):
    """Filtrelenmiş karar listesi — yalnızca çağıran kullanıcının kararları."""
    return svc_list_decisions(
        status=status,
        sentiment=sentiment,
        asset_symbol=asset_symbol,
        action=action,
        limit=limit,
        user_id=_extract_user_id(request),
    )


@app.post("/api/decisions", status_code=201, dependencies=[Depends(get_current_user)])
def create_decision_endpoint(
    body: DecisionCreateRequest,
    request: Request,
):
    """Yeni karar oluştur. user_id yalnızca doğrulanmış PB JWT'sinden alınır.
    track_shadow=True ve action=SELL → HELD_INSTEAD gölge pozisyonu otomatik oluşturulur (Prompt 12)."""
    user_id = _extract_user_id(request)

    shadow_qty: float | None = None
    shadow_price: float | None = None
    if body.track_shadow and body.action.upper() == "SELL" and body.transaction_id:
        # P10: gölge, bağlı SELL işleminin gerçek miktar/fiyatıyla açılır
        try:
            tx = get_client().collection("transactions").get_one(body.transaction_id)
        except Exception:
            raise HTTPException(400, "transaction_id geçersiz veya bulunamadı")
        if (
            str(getattr(tx, "user", "")) != user_id
            or str(getattr(tx, "asset_symbol", "")).upper() != body.asset_symbol
            or str(getattr(tx, "type", "")).upper() != "SELL"
        ):
            raise HTTPException(
                400, "transaction_id bu kullanıcının aynı sembollü SELL işlemine ait değil"
            )
        shadow_qty = float(getattr(tx, "quantity", 0) or 0)
        shadow_price = float(getattr(tx, "price", 0) or 0)

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
        # shortcut: transaction_id yoksa eski davranış (miktar 1.0, giriş=target_price)
        if body.track_shadow and body.action.upper() == "SELL":
            create_shadow_position(
                user_id=user_id,
                decision_id=result["id"],
                asset_symbol=body.asset_symbol,
                shadow_type="HELD_INSTEAD",
                entry_price=shadow_price if shadow_price is not None else body.target_price,
                quantity=shadow_qty if shadow_qty is not None else 1.0,
                entry_date=body.decision_date,
            )

        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/decisions/stats", dependencies=[Depends(get_current_user)])
def decisions_stats_endpoint(request: Request):
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


@app.get("/api/decisions/{decision_id}", dependencies=[Depends(get_current_user)])
def get_decision_endpoint(decision_id: PbId, request: Request):
    """ID ile tek karar. PB decisions collection'undan."""
    user_id = _extract_user_id(request)
    dec = svc_get_decision(decision_id)
    if dec is None or dec.get("user") != user_id:
        raise HTTPException(status_code=404, detail="Karar bulunamadı")
    return decision_to_dict(dec)


@app.put("/api/decisions/{decision_id}", dependencies=[Depends(get_current_user)])
def update_decision_endpoint(
    decision_id: PbId,
    body: DecisionUpdateRequest,
    request: Request,
):
    """Karar alanlarını güncelle (None → değiştirme). PB decisions collection'unda."""
    user_id = _extract_user_id(request)
    existing = svc_get_decision(decision_id)
    if existing is None or existing.get("user") != user_id:
        raise HTTPException(status_code=404, detail="Karar bulunamadı")

    dec = svc_update_decision(
        user_id,
        decision_id,
        rationale=body.rationale,
        sentiment=body.sentiment,
        target_price=body.target_price,
        target_date=body.target_date,
    )
    if dec is None:
        raise HTTPException(status_code=404, detail="Karar bulunamadı")
    return decision_to_dict(dec)


@app.post("/api/decisions/{decision_id}/close", dependencies=[Depends(get_current_user)])
def close_decision_endpoint(decision_id: PbId, request: Request):
    """Kararı REVIEWED yap. PB decisions collection'unda."""
    user_id = _extract_user_id(request)
    existing = svc_get_decision(decision_id)
    if existing is None or existing.get("user") != user_id:
        raise HTTPException(status_code=404, detail="Karar bulunamadı")

    dec = svc_close_decision(user_id, decision_id)
    if dec is None:
        raise HTTPException(status_code=404, detail="Karar bulunamadı")
    return decision_to_dict(dec)


@app.get(
    "/api/decisions/{decision_id}/target-check",
    dependencies=[Depends(get_current_user)],
)
def decision_target_check_endpoint(decision_id: PbId, request: Request):
    """Kararın hedef fiyat/vade gerçekleşme kontrolü. PB decisions collection'undan."""
    user_id = _extract_user_id(request)
    existing = svc_get_decision(decision_id)
    if existing is None or existing.get("user") != user_id:
        raise HTTPException(status_code=404, detail="Karar bulunamadı")

    result = svc_check_decision_target(decision_id)
    if "error" in result:
        return JSONResponse(status_code=404, content=result)
    return result


@app.post(
    "/api/decisions/{decision_id}/evaluate",
    dependencies=[Depends(get_current_user)],
)
def evaluate_decision_endpoint(decision_id: PbId, request: Request):
    """Kararın sonucunu ölçer: outcome_price, outcome_return_pct, target_hit (Prompt 13)."""
    user_id = _extract_user_id(request)
    existing = svc_get_decision(decision_id)
    if existing is None or existing.get("user") != user_id:
        raise HTTPException(status_code=404, detail="Karar bulunamadı")
    result = svc_evaluate_decision(user_id, decision_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Karar bulunamadı")
    return result


@app.post(
    "/api/decisions/{decision_id}/retrospective",
    dependencies=[Depends(check_retrospective_rate_limit)],
)
def generate_retrospective_endpoint(decision_id: PbId, request: Request):
    """Bir karar için AI post-mortem (retrospektif) oluşturur. PB decisions collection'unda kaydeder."""
    from services.ai_service import _check_ai_rate_limit

    user_id = _extract_user_id(request)
    existing = svc_get_decision(decision_id)
    if existing is None or existing.get("user") != user_id:
        raise HTTPException(status_code=404, detail="Karar bulunamadı")

    # AI hız sınırı (ekstra: per-user dakika/gün)
    allowed, retry_after = _check_ai_rate_limit(user_id, "retrospective")
    if not allowed:
        raise HTTPException(status_code=429, detail="AI hız sınırı aşıldı", headers={"Retry-After": str(retry_after)})

    result = svc_generate_ai_retrospective(decision_id)
    # P8 hata semantiği: servis yapılandırılmış döndürür → uç HTTP koduna eşlenir
    if result.get("retrospective") is None and result.get("error"):
        if result.get("api_available") is False:
            raise HTTPException(503, result["error"])
        raise HTTPException(502, result["error"])
    if result.get("retrospective") is None and result.get("api_available") is False:
        raise HTTPException(503, "AI servisi kullanılabilir değil (OPENROUTER_API_KEY eksik)")
    return result


# ---------------------------------------------------------------------------
# Counterfactual / What-If endpoint'ler (Prompt 12: PB geçişli service)
# ---------------------------------------------------------------------------


@app.get("/api/counterfactual", dependencies=[Depends(get_current_user)])
def counterfactual_endpoint(
    request: Request,
    decision_id: str = Query(..., pattern=PB_ID_PATTERN, description="Karar ID"),
    as_of: date | None = Query(None, description="ISO YYYY-MM-DD. Yoksa bugün."),
):
    """What-If senaryosu: decision_id ile gölge portföy kıyaslaması (PB)."""
    user_id = _extract_user_id(request)
    existing = svc_get_decision(decision_id)
    if existing is None or existing.get("user") != user_id:
        return JSONResponse(status_code=404, content={"error": "Karar bulunamadı"})
    as_of_date = as_of or date.today()
    result = what_if_scenario(decision_id, as_of=as_of_date)
    if "error" in result:
        return JSONResponse(status_code=404, content=result)
    return result


@app.post(
    "/api/counterfactual/shadow-positions",
    status_code=201,
    dependencies=[Depends(get_current_user)],
)
def create_shadow_position_endpoint(
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


@app.get("/api/counterfactual/shadow-positions", dependencies=[Depends(get_current_user)])
def list_shadow_positions_endpoint(
    request: Request,
    decision_id: str | None = Query(None, pattern=PB_ID_PATTERN, description="Karar ID filter"),
    asset_symbol: str | None = Query(None, description="Varlık sembolü filter"),
):
    """Gölge pozisyon listesi (filter ile)."""
    user_id = _extract_user_id(request)
    return get_shadow_positions(
        user_id=user_id,
        decision_id=decision_id,
        asset_symbol=asset_symbol,
    )


@app.delete(
    "/api/counterfactual/shadow-positions/{position_id}",
    dependencies=[Depends(get_current_user)],
)
def delete_shadow_position_endpoint(position_id: PbId, request: Request):
    """Gölge pozisyonunu sil (PB shadow_portfolios)."""
    user_id = _extract_user_id(request)
    try:
        from services.pb import admin_delete
        admin_delete("shadow_portfolios", position_id, user_id)
        return {"status": "deleted", "position_id": position_id}
    except PermissionError:
        raise HTTPException(status_code=404, detail="Gölge pozisyon bulunamadı")
    except Exception:
        raise HTTPException(status_code=404, detail="Gölge pozisyon bulunamadı")


@app.delete("/api/decisions/{decision_id}", dependencies=[Depends(get_current_user)])
def delete_decision_endpoint(decision_id: PbId, request: Request):
    """Kararı sil (bağlı gölge pozisyonlar cascade silinir; transaction etkilenmez)."""
    user_id = _extract_user_id(request)
    existing = svc_get_decision(decision_id)
    if existing is None or existing.get("user") != user_id:
        raise HTTPException(status_code=404, detail="Karar bulunamadı")
    try:
        result = svc_delete_decision(user_id, decision_id)
        if not result:
            logger.error("svc_delete_decision returned False for decision %s", decision_id)
            raise HTTPException(500, "Karar silinemedi")
        return {"status": "deleted", "decision_id": decision_id}
    except PermissionError:
        raise HTTPException(status_code=404, detail="Karar bulunamadı")
    except Exception as e:
        logger.error("delete_decision_endpoint error: %s", e)
        raise HTTPException(500, str(e))


@app.get("/api/simulation/monte-carlo", dependencies=[Depends(get_current_user)])
def monte_carlo_endpoint(
    request: Request,
    assets: str = Query(..., description="Virgülle ayrılmış semboller (örn: BTC,ETH,GC=F)"),
    days: int | None = Query(
        None,
        ge=1,
        le=756,
        description="Gün sayısı; verilmezse 3/6/12 ay (63/126/252) tek çağrıda hesaplanır",
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
    max_horizon = 252 if days is None else days
    cells = simulations * max_horizon * max(1, len(asset_list))
    if cells > 10_000_000:
        raise HTTPException(
            422,
            f"Simülasyon hücre bütçesi aşıldı ({cells} hücre; en fazla 10M). "
            "Gün/simülasyon sayısını azaltın veya horizon'u tek days ile verin.",
        )
    if days is None:
        # Prompt 12: 3/6/12 ay tek çağrıda
        horizons = {
            str(h): monte_carlo_simulation(
                user_id=user_id,
                asset_list=asset_list,
                days=h,
                n_simulations=simulations,
                percentiles=pct_list,
                seed=seed,
            )
            for h in (63, 126, 252)
        }
        return {"horizons": horizons}
    return monte_carlo_simulation(
        user_id=user_id,
        asset_list=asset_list,
        days=days,
        n_simulations=simulations,
        percentiles=pct_list,
        seed=seed,
    )


class TransactionCreateRequest(BaseModel):
    asset_symbol: str = Field(
        pattern=r"^[A-Z0-9.=^\-/]{1,20}$",
        max_length=20,
        description="Varlık sembolü",
    )
    tx_type: Literal[TransactionType.BUY, TransactionType.SELL, TransactionType.DIVIDEND, TransactionType.CASH_IN, TransactionType.CASH_OUT]
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


@app.post("/api/transactions", status_code=201, dependencies=[Depends(get_current_user)])
def create_transaction_endpoint(
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


@app.get("/api/transactions", dependencies=[Depends(get_current_user)])
def list_transactions_endpoint(
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


@app.get("/api/transactions/{transaction_id}", dependencies=[Depends(get_current_user)])
def get_transaction_endpoint(transaction_id: PbId, request: Request):
    """Tekil işlem kaydı (sahiplik kontrolü ile)."""
    user_id = _extract_user_id(request)
    try:
        result = srv_get_transactions(user_id=user_id, limit=1)
        for tx in result:
            if tx["id"] == transaction_id:
                return tx
        raise HTTPException(404, "İşlem bulunamadı")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/transactions/{transaction_id}", dependencies=[Depends(get_current_user)])

def delete_transaction_endpoint(
    transaction_id: PbId,
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
    except (PermissionError, ValueError) as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/portfolio/benchmarks", dependencies=[Depends(get_current_user)])
def portfolio_benchmarks_endpoint(
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
    n_simulations: int = Field(1000, ge=100, le=20000, description="Patika sayısı (maks 20.000)")


StressTestRequest.model_rebuild()


@app.post("/api/simulation/stress-test", dependencies=[Depends(get_current_user)])
def stress_test_endpoint(body: StressTestRequest):
    """Makro şok senaryoları altında portföy değerlerini simüle eder."""
    if body.n_simulations * body.days > 20_000_000:
        raise HTTPException(
            422,
            f"Simülasyon hücre bütçesi aşıldı ({body.n_simulations}×{body.days}); en fazla 20M hücre.",
        )
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


@app.post("/api/simulation/narrative", dependencies=[Depends(get_current_user)])
def narrative_endpoint(request: Request, body: NarrativeRequest):
    """Monte Carlo / stres test sonucu için Türkçe risk anlatısı (502/503 semantiği)."""
    from services.ai_service import (
        AIGenerationError,
        AIUnavailableError,
        _check_ai_rate_limit,
    )

    user_id = _extract_user_id(request)
    # AI hız sınırı kontrolü
    allowed, retry_after = _check_ai_rate_limit(user_id, "narrative")
    if not allowed:
        raise HTTPException(status_code=429, detail="AI hız sınırı aşıldı", headers={"Retry-After": str(retry_after)})

    try:
        result = srv_generate_risk_narrative(
            simulation_result=body.simulation_result,
            portfolio_context=body.portfolio_context,
        )
        return {"narrative": result}
    except AIUnavailableError as e:
        raise HTTPException(503, str(e))
    except AIGenerationError:
        # Her zaman güvenli genel mesaj; detay loglanmıştır
        raise HTTPException(502, "AI sağlayıcısı geçici olarak yanıt vermedi")
    except Exception as e:
        logger.error("narrative_endpoint error: %s", e)
        raise HTTPException(500, "İç sunucu hatası")
