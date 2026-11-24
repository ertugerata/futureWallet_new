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
from services.asset_types import _guess_asset_type
from services.enums import (
    ACTION_ALLOWED,
    SENTIMENT_ALLOWED,
    STATUS_ALLOWED,
)
from services.multi_asset_manager import AssetManager
from services.pb import admin_create, admin_delete, admin_update, get_admin_client, get_client

logger = logging.getLogger(__name__)


def _parse_pb_date(value: Any) -> date | None:
    """PB DateTime/Timestamp string ("YYYY-MM-DD[ HH:MM:SS(.mmmZ)]") veya datetime → date.

    Eski hali boşluklu PB formatını ve datetime nesnesi olan `created` alanını None'a
    düşürüyordu; EXPIRED job'ı bu yüzden hiç karar bulamıyordu (test_expiry_e2e).
    """
    if not value:
        return None
    date_getter = getattr(value, "date", None)
    if callable(date_getter):
        return date_getter()
    try:
        return date.fromisoformat(str(value).replace(" ", "T").split("T")[0])
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

    # Transaction ownership check (P3: karar-transaction ilişkisi sahiplik doğrulama)
    if transaction_id:
        client = get_client()
        try:
            tx = client.collection("transactions").get_one(transaction_id)
            if getattr(tx, "user", None) != user_id:
                raise PermissionError("Transaction does not belong to user")
        except PermissionError:
            raise
        except Exception:
            raise ValueError("Transaction not found")

    data: dict[str, Any] = {
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

    record = admin_create("decisions", data, user_id)
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
    user_id: str,
    decision_id: str,
    rationale: str | None = None,
    sentiment: str | None = None,
    target_price: float | None = None,
    target_date: date | None = None,
) -> dict | None:
    """Karar alanlarını günceller (sadece kullanıcı alanları: rationale, sentiment, target_price, target_date)."""
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

    try:
        updated = admin_update("decisions", decision_id, body, user_id)
        return decision_to_dict(updated)
    except PermissionError:
        raise
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 5. close_decision (sistem endpoint'i - status yazar)
# ---------------------------------------------------------------------------


def close_decision(user_id: str, decision_id: str) -> dict | None:
    """Kararı REVIEWED durumuna taşır (sistem yazması)."""
    try:
        updated = admin_update("decisions", decision_id, {"status": "REVIEWED"}, user_id)
        return decision_to_dict(updated)
    except PermissionError:
        raise
    except Exception:
        return None


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


def delete_decision(user_id: str, decision_id: str) -> bool:
    """Bir kararı siler (bağlı gölge pozisyonlar da silinir)."""
    try:
        # Önce bağlı gölge pozisyonları sil (admin client ile)
        admin = get_admin_client()
        shadows = admin.collection("shadow_portfolios").get_full_list(
            query_params={"filter": f"decision = '{decision_id}'"}
        )
        for sp in shadows:
            if getattr(sp, "user", None) == user_id:
                admin.collection("shadow_portfolios").delete(sp.id)

        # Sonra kararı sil
        admin_delete("decisions", decision_id, user_id)
        return True
    except PermissionError:
        raise
    except Exception as exc:
        logger.error("Karar silinemedi (%s): %s", decision_id, exc)
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


def _get_outcome_price(sym: str, atype: str, target_d: date) -> float | None:
    """Get outcome price for symbol at target date."""
    from services.price_service import get_price_on

    return get_price_on(sym, atype, target_d)


def _get_entry_price(sym: str, atype: str, dec: dict) -> float | None:
    """Get entry price from decision date/created or target_price."""
    from services.price_service import get_price_on

    entry_basis = dec.get("decision_date") or dec.get("date")
    if entry_basis:
        entry_p = get_price_on(sym, atype, entry_basis)
        if entry_p is not None:
            return entry_p
    return dec.get("target_price")


def _calculate_return_and_target(
    action: str,
    entry_p: float | None,
    outcome_p: float | None,
    target_price: float | None,
) -> tuple[float | None, bool | None]:
    """Calculate return_pct and target_hit."""
    if outcome_p is None or entry_p is None or entry_p <= 0:
        return None, None

    sign = 1 if action == "BUY" else (-1 if action == "SELL" else 0)
    if not sign:
        return None, None

    return_pct = round(sign * (outcome_p - entry_p) / entry_p * 100, 2)

    target_hit = None
    if target_price:
        target_hit = outcome_p >= target_price if action == "BUY" else outcome_p <= target_price

    return return_pct, target_hit


def evaluate_decision(
    user_id: str,
    decision_id: str,
    as_of: date | None = None,
) -> dict[str, Any] | None:
    """Kararın sonucunu ölçer: outcome_price, outcome_return_pct, target_hit (Prompt 13)."""
    dec = get_decision(decision_id)
    if not dec:
        return None

    # Verify ownership
    if dec.get("user") != user_id:
        raise PermissionError("Decision not owned by user")

    target_d = as_of or dec.get("target_date") or date.today()
    sym = dec.get("asset_symbol", "")
    atype = _guess_asset_type(sym)

    outcome_p = _get_outcome_price(sym, atype, target_d)
    entry_p = _get_entry_price(sym, atype, dec)

    action = dec.get("action", "BUY").upper()
    return_pct, target_hit = _calculate_return_and_target(
        action, entry_p, outcome_p, dec.get("target_price")
    )

    update_fields: dict[str, Any] = {}
    if outcome_p is not None:
        update_fields["outcome_price"] = outcome_p
    if return_pct is not None:
        update_fields["outcome_return_pct"] = return_pct
    if target_hit is not None:
        update_fields["target_hit"] = target_hit

    if update_fields:
        try:
            updated = admin_update("decisions", decision_id, update_fields, user_id)
            dec.update(decision_to_dict(updated))
        except PermissionError:
            raise
        except Exception as exc:
            logger.error("Karar sonucu kaydedilemedi (%s): %s", decision_id, exc)

    return dec


def auto_close_expired_decisions(days_before: int = 0) -> list[dict]:
    """Hedef tarihleri dolmuş ama REVIEWED yapılmamış kararları EXPIRED yapar ve sonuçları doldurur."""
    cutoff = date.today() - timedelta(days=days_before)
    closed: list[dict] = []

    # Admin client ile tüm OPEN kararları çek (user client listRule sadece kendi kararlarını görür)
    admin = get_admin_client()
    records = admin.collection("decisions").get_full_list(
        query_params={"filter": "status = 'OPEN'", "sort": "target_date"}
    )

    for record in records:
        target_date = record.target_date
        if target_date is None:
            continue
        # target_date is string "YYYY-MM-DD HH:MM:SS.mmmZ"
        try:
            target_d = date.fromisoformat(str(target_date).split(" ")[0])
        except Exception:
            continue
        if target_d >= cutoff:
            continue

        user_id = record.user
        dec_id = record.id

        # Evaluate outcome
        evaluate_decision(user_id, dec_id, as_of=target_d)

        # Set status to EXPIRED (system write)
        try:
            admin_update("decisions", dec_id, {"status": "EXPIRED"}, user_id)
            # Refresh the decision dict
            updated = get_decision(dec_id)
            if updated:
                closed.append(updated)
        except Exception as exc:
            logger.error("Karar EXPIRED yapılamadı (%s): %s", dec_id, exc)

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

    api_available = bool(config.OPENROUTER_API_KEY)
    retrospective: str | None = None

    if api_available:
        try:
            retrospective = generate_decision_retrospective(
                decision,
                market_data=market_data,
                api_key=config.OPENROUTER_API_KEY,
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
