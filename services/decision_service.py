"""
FutureWallet – Karar Günlüğü Servisi (Decision Journal) – PocketBase
=======================================================================
Yatırımcının alınan stratejik kararlarını kaydeder, duygu durumlarını
tag'ler, hedef fiyat/vade gerçekleşme kontrolü yapar ve AI post-mortem
mantığına alan açar.

PocketBase `decisions` koleksiyonu üzerinde çalışır (services.pb üzerinden).
MVP §3.2, Prompt 3, 5, 7, 13 ile tam uyumlu.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import config
from services.ai_service import (
    AIGenerationError,
    AIUnavailableError,
    generate_decision_retrospective,
)
from services.enums import (
    ACTION_ALLOWED,
    SENTIMENT_ALLOWED,
    STATUS_ALLOWED,
)
from services.multi_asset_manager import AssetManager
from services.pb import get_client

logger = logging.getLogger(__name__)


def _parse_pb_date(value: str | None) -> date | None:
    """PB DateTime/Timestamp string → datetime.date."""
    if not value:
        return None
    try:
        if "T" in str(value):
            return date.fromisoformat(str(value).split("T")[0])
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 1. create_decision
# ---------------------------------------------------------------------------


def create_decision(
    user_id: str,
    asset_symbol: str,
    action: str,
    rationale: str | None = None,
    sentiment: str | None = None,
    target_price: float | None = None,
    target_date: date | None = None,
    decision_date: date | None = None,
    transaction_id: str | None = None,
) -> dict:
    """Yeni bir karar kaydı oluşturur."""
    if decision_date is not None and decision_date > date.today():
        raise ValueError("decision_date gelecekte olamaz")

    action_upper = action.upper()
    if action_upper not in ACTION_ALLOWED:
        raise ValueError(f"action: {action!r} — allowed: {ACTION_ALLOWED}")

    sentiment_upper: str | None = None
    if sentiment is not None:
        sentiment_upper = sentiment.upper()
        if sentiment_upper not in SENTIMENT_ALLOWED:
            raise ValueError(f"sentiment: {sentiment!r} — allowed: {SENTIMENT_ALLOWED}")

    client = get_client()
    decisions = client.collection("decisions")

    data: dict[str, Any] = {
        "user": user_id,
        "asset_symbol": asset_symbol.upper(),
        "action": action_upper,
        "rationale": rationale,
        "sentiment": sentiment_upper,
        "target_price": target_price,
        "target_date": target_date.isoformat() if target_date else None,
        "decision_date": decision_date.isoformat() if decision_date else None,
        "status": "OPEN",
    }
    if transaction_id:
        data["transaction"] = transaction_id

    record = decisions.create(data)
    return decision_to_dict(record)


# ---------------------------------------------------------------------------
# 2. get_decision
# ---------------------------------------------------------------------------


def get_decision(decision_id: str) -> dict | None:
    """ID ile tek karar. Yoksa None."""
    client = get_client()
    try:
        record = client.collection("decisions").get_one(decision_id)
        return decision_to_dict(record)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 3. list_decisions
# ---------------------------------------------------------------------------


def list_decisions(
    status: str | None = None,
    sentiment: str | None = None,
    asset_symbol: str | None = None,
    action: str | None = None,
    target_date_from: date | None = None,
    target_date_to: date | None = None,
    limit: int | None = None,
    order_by_date_desc: bool = True,
    user_id: str | None = None,
) -> list[dict]:
    """Filtrelenmiş karar listesi."""
    client = get_client()
    decisions = client.collection("decisions")

    filter_parts: list[str] = []
    filter_params: dict[str, Any] = {}
    if user_id:
        filter_parts.append("user = {:user_id}")
        filter_params["user_id"] = user_id
    if status is not None:
        filter_parts.append("status = {:status}")
        filter_params["status"] = status.upper()
    if sentiment is not None:
        filter_parts.append("sentiment = {:sentiment}")
        filter_params["sentiment"] = sentiment.upper()
    if asset_symbol is not None:
        filter_parts.append("asset_symbol = {:asset_symbol}")
        filter_params["asset_symbol"] = asset_symbol.upper()
    if action is not None:
        filter_parts.append("action = {:action}")
        filter_params["action"] = action.upper()
    if target_date_from is not None:
        filter_parts.append("target_date >= {:target_date_from}")
        filter_params["target_date_from"] = target_date_from.isoformat()
    if target_date_to is not None:
        filter_parts.append("target_date <= {:target_date_to}")
        filter_params["target_date_to"] = target_date_to.isoformat()

    query_params: dict[str, Any] = {}
    if filter_parts:
        query_params["filter"] = client.filter(" && ".join(filter_parts), filter_params)

    sort = "-created" if order_by_date_desc else "+created"
    query_params["sort"] = sort

    if limit is not None and limit <= 500:
        res = decisions.get_list(page=1, per_page=limit, query_params=query_params)
        records = res.items
    else:
        records = decisions.get_full_list(batch=200, query_params=query_params)
        if limit is not None:
            records = records[:limit]

    return [decision_to_dict(r) for r in records]


# ---------------------------------------------------------------------------
# 4. update_decision
# ---------------------------------------------------------------------------


def update_decision(
    decision_id: str,
    rationale: str | None = None,
    sentiment: str | None = None,
    target_price: float | None = None,
    target_date: date | None = None,
    status: str | None = None,
) -> dict | None:
    """Karar alanlarını günceller."""
    client = get_client()
    decisions = client.collection("decisions")

    body: dict[str, Any] = {}
    if rationale is not None:
        body["rationale"] = rationale
    if sentiment is not None:
        sentiment_upper = sentiment.upper()
        if sentiment_upper not in SENTIMENT_ALLOWED:
            raise ValueError(f"sentiment: {sentiment!r} — allowed: {SENTIMENT_ALLOWED}")
        body["sentiment"] = sentiment_upper
    if target_price is not None:
        body["target_price"] = target_price
    if target_date is not None:
        body["target_date"] = target_date.isoformat() if target_date else None
    if status is not None:
        status_upper = status.upper()
        if status_upper not in STATUS_ALLOWED:
            raise ValueError(f"status: {status!r} — allowed: {STATUS_ALLOWED}")
        body["status"] = status_upper

    try:
        updated = decisions.update(decision_id, body)
        return decision_to_dict(updated)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 5. close_decision
# ---------------------------------------------------------------------------


def close_decision(decision_id: str) -> dict | None:
    """Kararı REVIEWED durumuna taşır."""
    return update_decision(decision_id, status="REVIEWED")


# ---------------------------------------------------------------------------
# 6. decision_to_dict
# ---------------------------------------------------------------------------


def decision_to_dict(record) -> dict:
    """PB decisions record veya dict → flat dict."""
    if isinstance(record, dict):
        return record
    return {
        "id": getattr(record, "id", ""),
        "date": _parse_pb_date(getattr(record, "created", None)),
        "asset_symbol": getattr(record, "asset_symbol", ""),
        "action": getattr(record, "action", ""),
        "rationale": getattr(record, "rationale", None),
        "sentiment": getattr(record, "sentiment", None),
        "target_price": getattr(record, "target_price", None),
        "target_date": _parse_pb_date(getattr(record, "target_date", None)),
        "status": getattr(record, "status", "OPEN"),
        "ai_retrospective": getattr(record, "ai_retrospective", None),
        "transaction_id": getattr(record, "transaction", None),
        "user": getattr(record, "user", None),
        "decision_date": _parse_pb_date(getattr(record, "decision_date", None)),
        "outcome_return_pct": getattr(record, "outcome_return_pct", None),
        "outcome_price": getattr(record, "outcome_price", None),
        "target_hit": getattr(record, "target_hit", None),
    }


# ---------------------------------------------------------------------------
# 7. get_sentiment_summary
# ---------------------------------------------------------------------------


def get_sentiment_summary(user_id: str | None = None) -> dict[str, int]:
    """Her sentiment tag'ına göre karar sayıları."""
    client = get_client()
    decisions = client.collection("decisions")
    query_params: dict[str, Any] = {}
    if user_id:
        query_params["filter"] = client.filter("user = {:user_id}", {"user_id": user_id})
    records = decisions.get_full_list(query_params=query_params)
    out = {s: 0 for s in SENTIMENT_ALLOWED}
    for rec in records:
        s = getattr(rec, "sentiment", None)
        if s and s in out:
            out[s] += 1
    return out


# ---------------------------------------------------------------------------
# 8. get_status_summary
# ---------------------------------------------------------------------------


def get_status_summary(user_id: str | None = None) -> dict[str, int]:
    """OPEN / EXPIRED / REVIEWED / CLOSED sayımları."""
    client = get_client()
    decisions = client.collection("decisions")
    query_params: dict[str, Any] = {}
    if user_id:
        query_params["filter"] = client.filter("user = {:user_id}", {"user_id": user_id})
    records = decisions.get_full_list(query_params=query_params)
    out = {s: 0 for s in STATUS_ALLOWED}
    for rec in records:
        s = getattr(rec, "status", None)
        if s and s in out:
            out[s] += 1
    return out


# ---------------------------------------------------------------------------
# 8b. delete_decision
# ---------------------------------------------------------------------------


def delete_decision(decision_id: str) -> bool:
    """Bir kararı siler (Prompt 13)."""
    client = get_client()
    try:
        client.collection("decisions").delete(decision_id)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 9. check_decision_target
# ---------------------------------------------------------------------------


def check_decision_target(
    decision_id: str,
    price_fn: Callable[[str], float | None] | None = None,
) -> dict:
    """Bir kararın hedef fiyat / vade gerçekleşme durumunu kontrol eder."""
    decision = get_decision(decision_id)
    if decision is None:
        return {"error": "decision not found"}

    if price_fn is None:
        mgr = AssetManager()
        price_fn = lambda sym: mgr.get_price(sym, _guess_asset_type(sym))

    current_price = price_fn(decision["asset_symbol"]) if decision["asset_symbol"] else None

    target_hit: bool | None = None
    if decision["target_price"] is not None and current_price is not None:
        if decision["action"] == "BUY":
            target_hit = current_price >= decision["target_price"]
        elif decision["action"] == "SELL":
            target_hit = current_price <= decision["target_price"]

    target_date_passed = (
        decision["target_date"] is not None and decision["target_date"] < date.today()
    )

    if decision["status"] == "REVIEWED":
        status_suggestion = "REVIEWED"
    elif target_date_passed:
        status_suggestion = "REVIEWED"
    else:
        status_suggestion = "OPEN"

    return {
        "decision_id": decision_id,
        "asset_symbol": decision["asset_symbol"],
        "action": decision["action"],
        "target_price": decision["target_price"],
        "target_date": decision["target_date"].isoformat() if decision["target_date"] else None,
        "current_price": current_price,
        "target_hit": target_hit,
        "target_date_passed": target_date_passed,
        "status_suggestion": status_suggestion,
    }


def get_decisions_due_for_review() -> list[dict]:
    """Hedef tarihi geçmiş ama henüz REVIEWED edilmemiş kararlar."""
    due: list[dict] = []
    for d in list_decisions(status="OPEN"):
        if d["target_date"] is not None and d["target_date"] < date.today():
            due.append(d)
    due.sort(key=lambda d: d["target_date"] or date.min)
    return due


def auto_close_expired_decisions(days_before: int = 0) -> list[dict]:
    """Hedef tarihleri dolmuş ama REVIEWED yapılmamış kararları EXPIRED yapar."""
    cutoff = date.today() - timedelta(days=days_before)
    closed: list[dict] = []
    for d in list_decisions(status="OPEN"):
        if d["target_date"] is not None and d["target_date"] < cutoff:
            updated = update_decision(d["id"], status="EXPIRED")
            if updated:
                closed.append(updated)
    return closed


def generate_ai_retrospective(
    decision_id: str,
    price_fn: Callable[[str], float | None] | None = None,
    market_context: str | None = None,
) -> dict:
    """Bir karar için AI post-mortem (retrospektif) üretir."""
    decision = get_decision(decision_id)
    if decision is None:
        return {"error": "decision not found", "api_available": False}

    if price_fn is None:
        mgr = AssetManager()
        price_fn = lambda sym: mgr.get_price(sym, _guess_asset_type(sym))

    current_price = price_fn(decision["asset_symbol"]) if decision["asset_symbol"] else None
    market_data = {"price_on_decision": current_price} if current_price else None

    api_available = bool(config.GOOGLE_API_KEY)
    retrospective: str | None = None

    if api_available:
        try:
            retrospective = generate_decision_retrospective(
                decision,
                market_data=market_data,
                api_key=config.GOOGLE_API_KEY,
                model=config.GEMINI_MODEL,
            )

            # Başarılı → DB güncelle
            client = get_client()
            client.collection("decisions").update(
                decision_id,
                {"ai_retrospective": retrospective, "status": "REVIEWED"},
            )

            return {
                "decision_id": decision_id,
                "retrospective": retrospective,
                "status": "REVIEWED",
                "api_available": True,
            }

        except AIUnavailableError:
            return {
                "error": "AI servisi kullanılabilir değil (API anahtarı eksik)",
                "api_available": False,
                "retrospective": None,
                "status": decision["status"],
            }
        except AIGenerationError as exc:
            return {
                "error": f"AI yanıt oluşturulamadı: {exc}",
                "api_available": True,
                "retrospective": None,
                "status": decision["status"],
            }

    return {
        "decision_id": decision_id,
        "retrospective": None,
        "status": decision["status"],
        "api_available": False,
    }


def _guess_asset_type(symbol: str) -> str:
    """Price fetch için asset türü tahmini."""
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
