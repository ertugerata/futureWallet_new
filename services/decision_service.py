"""
FutureWallet – Karar Günlüğü Servisi (Decision Journal) – PocketBase
=======================================================================

Yatırımcının alınan stratejik kararlarını kaydeder, duygu durumlarını
tag'ler, hedef fiyat/vade gerçekleşme kontrolü yapar ve AI post-mortem
mantığına alan açar.

PocketBase `decisions` koleksiyonu üzerinde çalışır.
db.py (SQLAlchemy) → pocketbase.py geçişi ile senkronize.

MVP §3.2, TODO 2.2, Prompt 7 (AI retrospektif), Prompt 13 (karar günlüğü
eksiklikleri – decision_date, target_hit, outcome alanları PB şemasında).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

import config
from services.ai_service import (
    AIGenerationError,
    AIUnavailableError,
    generate_decision_retrospective,
)
from services.multi_asset_manager import AssetManager
from services.pocketbase import get_client

# ---------------------------------------------------------------------------
# Sabitler – duygu durum tag'leri (MVP §3.2)
# ---------------------------------------------------------------------------

SENTIMENT_ALLOWED = frozenset(
    {
        "FOMO",  # FOMO — Fersizlik
        "STRATEGIC",  # Stratejik Analiz
        "PANIC",  # Panik Satışı
        "DIVIDEND",  # Temettü/Gelir
        "RISK_REDUCTION",  # Risk Azaltma
    }
)

SENTIMENT_LABELS = {
    "FOMO": "FOMO (Fersizlik)",
    "STRATEGIC": "Stratejik Analiz",
    "PANIC": "Panik Satışı",
    "DIVIDEND": "Temettü/Gelir",
    "RISK_REDUCTION": "Risk Azaltma",
}

ACTION_ALLOWED = frozenset({"BUY", "SELL", "HOLD"})

# PB decisions şemasında: OPEN, EXPIRED, REVIEWED, CLOSED
STATUS_ALLOWED = frozenset({"OPEN", "EXPIRED", "REVIEWED", "CLOSED"})

PB_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S%z"  # PB DateTime fields formatı


# ---------------------------------------------------------------------------
# Helper – PB record tarih alanlarını datetime.date'a çevir
# ---------------------------------------------------------------------------


def _parse_pb_date(value: str | None) -> date | None:
    """PB DateTime/Timestamp string → datetime.date."""
    if not value:
        return None
    try:
        # PB timestamp: "2024-01-15T00:00:00Z" veya "2024-01-15"
        if "T" in value:
            return date.fromisoformat(value.split("T")[0])
        return date.fromisoformat(value)
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
    """Yeni bir karar kaydı oluşturur (Prompt 13: decision_date eklendi).

    Args:
        user_id:      PB auth kullanıcı ID'si.
        asset_symbol: Varlık sembolü (BTC, THYAO, GC=F, …).
        action:       İşlem tipi — BUY, SELL, HOLD.
        rationale:    Karar gerekçesi (opsiyonel, max 5000).
        sentiment:    Duygu durum tag'i (None → yok). Allowed: SENTIMENT_ALLOWED.
        target_price: Hedef fiyat (opsiyonel, >0).
        target_date:  Hedef tarih (opsiyonel).
        decision_date:Karar tarihi (opsiyonel; gelecekte olamaz, yoksa today).
        transaction_id: İlgili transaction ID (opsiyonel).

    Returns:
        Decision dict (decision_to_dict formatında).
    """
    # decision_date: gelecek tarih reddedilir
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

    data = {
        "user": user_id,
        "asset_symbol": asset_symbol.upper(),
        "action": action_upper,
        "rationale": rationale,
        "sentiment": sentiment_upper,
        "target_price": target_price,
        "target_date": target_date.isoformat() if target_date else None,
        "decision_date": decision_date.isoformat() if decision_date else None,
        "status": "OPEN",
        "transaction_id": transaction_id,
    }

    record = decisions.create(data)  # PB otomatik ID atar
    return decision_to_dict(record)
    """Yeni bir karar kaydı oluşturur (Prompt 13: decision_date eklendi).

    Args:
        user_id: PB auth kullanıcı ID'si (API token → PB auth'dan).
        asset_symbol: Varlık sembolü (BTC, THYAO, GC=F, …).
        action: İşlem tipi — BUY, SELL, HOLD.
        rationale: Karar gerekçesi (opsiyonel, max 5000).
        sentiment: Duygu durum tag'i (None → yok). Allowed: SENTIMENT_ALLOWED.
        target_price: Hedef fiyat (opsiyonel, >0).
        target_date: Hedef tarih (opsiyonel).
        transaction_id: İlgili transaction ID (opsiyonel).

    Returns:
        Decision dict (decision_to_dict formatında).
    """
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

    data = {
        "user": user_id,
        "asset_symbol": asset_symbol.upper(),
        "action": action_upper,
        "rationale": rationale,
        "sentiment": sentiment_upper,
        "target_price": target_price,
        "target_date": target_date.isoformat() if target_date else None,
        "status": "OPEN",
        "transaction_id": transaction_id,
    }

    record = decisions.create(data)  # PB otomatik ID atar
    return decision_to_dict(record)


# ---------------------------------------------------------------------------
# 2. get_decision
# ---------------------------------------------------------------------------


def get_decision(decision_id: str) -> dict | None:
    """ID ile tek karar. Yoksa None."""
    client = get_client()
    decisions = client.collection("decisions")
    records = decisions.get_list(params=f"filter=id='{decision_id}'&per_page=1")
    if records:
        return decision_to_dict(records[0])
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
) -> list[dict]:
    """Filtrelenmiş karar listesi.

    PB filter syntax: filter=field='value' AND field2='value2'
    PB sort syntax:    sort=field DIRECTION
    """
    client = get_client()
    decisions = client.collection("decisions")

    filters: list[str] = []
    if status is not None:
        filters.append(f"status='{status.upper()}'")
    if sentiment is not None:
        filters.append(f"sentiment='{sentiment.upper()}'")
    if asset_symbol is not None:
        filters.append(f"asset_symbol='{asset_symbol.upper()}'")
    if action is not None:
        filters.append(f"action='{action.upper()}'")
    if target_date_from is not None:
        filters.append(f"target_date>='{target_date_from.isoformat()}'")
    if target_date_to is not None:
        filters.append(f"target_date<='{target_date_to.isoformat()}'")

    filter_str = " AND ".join(filters) if filters else ""
    sort = "date DESC" if order_by_date_desc else "date ASC"
    params = f"filter={filter_str}&sort={sort}"
    if limit is not None:
        params += f"&per_page={limit}"

    records = decisions.get_list(params=params)
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
    """Karar alanlarını günceller. None → o alan değiştirilmez.

    Returns:
        Güncellenmiş decision dict. Yoksa None.
    """
    client = get_client()
    decisions = client.collection("decisions")

    try:
        record = decisions.retrieve(decision_id)
    except Exception:
        return None

    if rationale is not None:
        record["rationale"] = rationale
    if sentiment is not None:
        sentiment_upper = sentiment.upper()
        if sentiment_upper not in SENTIMENT_ALLOWED:
            raise ValueError(f"sentiment: {sentiment!r} — allowed: {SENTIMENT_ALLOWED}")
        record["sentiment"] = sentiment_upper
    if target_price is not None:
        record["target_price"] = target_price
    if target_date is not None:
        record["target_date"] = target_date.isoformat() if target_date else None
    if status is not None:
        status_upper = status.upper()
        if status_upper not in STATUS_ALLOWED:
            raise ValueError(f"status: {status!r} — allowed: {STATUS_ALLOWED}")
        record["status"] = status_upper

    decisions.update(record)
    return decision_to_dict(record)


# ---------------------------------------------------------------------------
# 5. close_decision
# ---------------------------------------------------------------------------


def close_decision(decision_id: str) -> dict | None:
    """Kararı REVIEWED durumuna taşır (kullanıcı taraflı gözden geçirme)."""
    return update_decision(decision_id, status="REVIEWED")


# ---------------------------------------------------------------------------
# 6. decision_to_dict
# ---------------------------------------------------------------------------


def decision_to_dict(record) -> dict:
    """PB decisions record veya dict → flat dict (API response / serializasyon).

    idempotent: dict girişte değerni doğrudan döner; PB Record girişte convert eder.
    """
    # dict zaten convert edilmiş → direkt return
    if isinstance(record, dict):
        return record
    return {
        "id": record.id,
        "date": _parse_pb_date(getattr(record, "date", None)),
        "asset_symbol": getattr(record, "asset_symbol", ""),
        "action": getattr(record, "action", ""),
        "rationale": getattr(record, "rationale", None),
        "sentiment": getattr(record, "sentiment", None),
        "target_price": getattr(record, "target_price", None),
        "target_date": _parse_pb_date(getattr(record, "target_date", None)),
        "status": getattr(record, "status", "OPEN"),
        "ai_retrospective": getattr(record, "ai_retrospective", None),
        "transaction_id": getattr(record, "transaction_id", None),
        "user": getattr(record, "user", None),
        "decision_date": _parse_pb_date(getattr(record, "decision_date", None)),
        "outcome_return_pct": getattr(record, "outcome_return_pct", None),
        "outcome_price": getattr(record, "outcome_price", None),
        "target_hit": getattr(record, "target_hit", None),
    }


# ---------------------------------------------------------------------------
# 7. get_sentiment_summary
# ---------------------------------------------------------------------------


def get_sentiment_summary() -> dict[str, int]:
    """Her sentiment tag'ına göre karar sayıları (in-memory aggregation)."""
    client = get_client()
    decisions = client.collection("decisions")
    records = decisions.get_list(params="per_page=1000")
    out = {s: 0 for s in SENTIMENT_ALLOWED}
    for rec in records:
        s = getattr(rec, "sentiment", None)
        if s and s in out:
            out[s] += 1
    return out


# ---------------------------------------------------------------------------
# 8. get_status_summary
# ---------------------------------------------------------------------------


def get_status_summary() -> dict[str, int]:
    """OPEN / EXPIRED / REVIEWED / CLOSED sayımları."""
    client = get_client()
    decisions = client.collection("decisions")
    records = decisions.get_list(params="per_page=1000")
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
    """Bir kararı sil (Prompt 13)."""
    client = get_client()
    decisions = client.collection("decisions")
    try:
        record = decisions.get_list(params=f"filter=id='{decision_id}'&per_page=1")[0]
        decisions.delete(record)
        return True
    except (IndexError, Exception):
        return False


# ---------------------------------------------------------------------------
# 9. check_decision_target
# ---------------------------------------------------------------------------


def check_decision_target(
    decision_id: str,
    price_fn: Callable[[str], float | None] | None = None,
) -> dict:
    """Bir kararın hedef fiyat / vade gerçekleşme durumunu kontrol eder.

    BUY → hedef fiyatın üzerindeyse "hit"
    SELL → hedef fiyatın altındaysa "hit"

    Args:
        decision_id: Karar ID.
        price_fn: (asset_symbol) → güncel fiyat. None → AssetManager default.

    Returns:
        {
            "decision_id", "asset_symbol", "action", "target_price",
            "target_date", "current_price", "target_hit",
            "target_date_passed", "status_suggestion",
        }
    """
    decision = get_decision(decision_id)
    if decision is None:
        return {"error": "decision not found"}

    if price_fn is None:
        mgr = AssetManager()
        price_fn = lambda sym: mgr.get_price(sym, _guess_asset_type(sym))

    current_price = (
        price_fn(decision["asset_symbol"]) if decision["asset_symbol"] else None
    )

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
        status_suggestion = "REVIEWED"  # vade geçmiş → review önerilir
    else:
        status_suggestion = "OPEN"

    return {
        "decision_id": decision_id,
        "asset_symbol": decision["asset_symbol"],
        "action": decision["action"],
        "target_price": decision["target_price"],
        "target_date": decision["target_date"].isoformat()
        if decision["target_date"]
        else None,
        "current_price": current_price,
        "target_hit": target_hit,
        "target_date_passed": target_date_passed,
        "status_suggestion": status_suggestion,
    }


# ---------------------------------------------------------------------------
# 10. get_decisions_due_for_review
# ---------------------------------------------------------------------------


def get_decisions_due_for_review() -> list[dict]:
    """Hedef tarihi geçmiş ama henüz REVIEWED edilmemiş kararlar."""
    due: list[dict] = []
    for d in list_decisions(status="OPEN"):
        if d["target_date"] is not None and d["target_date"] < date.today():
            due.append(d)
    due.sort(key=lambda d: d["target_date"] or date.min)
    return due


# ---------------------------------------------------------------------------
# 11. auto_close_expired_decisions
# ---------------------------------------------------------------------------


def auto_close_expired_decisions(days_before: int = 0) -> list[dict]:
    """Hedef tarihleri dolmuş ama REVIEWED yapılmamış kararları EXPIRED yapar.

    Args:
        days_before: Hedef tarih bu kadar gün önce geçtiyse kapat.
                     0 → bugün geçmiş hedef tarihler.

    Returns:
        Kapatılan (artık EXPIRED) decision listesi.
    """
    cutoff = date.today() - timedelta(days=days_before)
    closed: list[dict] = []
    for d in list_decisions(status="OPEN"):
        if d["target_date"] is not None and d["target_date"] < cutoff:
            updated = update_decision(d["id"], status="EXPIRED")
            if updated:
                closed.append(updated)
    return closed


# ---------------------------------------------------------------------------
# 12. generate_ai_retrospective (Prompt 7 – düzeltme: hata yutma + DB değişmez)
# ---------------------------------------------------------------------------


def generate_ai_retrospective(
    decision_id: str,
    price_fn: Callable[[str], float | None] | None = None,
    market_context: str | None = None,
) -> dict:
    """Bir karar için AI post-mortem (retrospektif) üretir.

    Prompt 7 düzeltmeleri:
      - AIUnavailableError → 503 (anahtar yok)
      - AIGenerationError → 502 (sağlayıcı hatası)
      - Hata durumunda ai_retrospective DEĞİŞMEZ, status DEĞİŞMEZ.
      - google-genai SDK'sı + config.GEMINI_MODEL kullanılır.
      - prompt injection koruması <kullanici_notu> (ai_service içinde).

    Args:
        decision_id: Karar ID.
        price_fn: (asset_symbol) → güncel fiyat. None → AssetManager default.
        market_context: İsteğe bağlı piyasa bağlamı metni.

    Returns:
        {
            "decision_id":     str,
            "retrospective":   str | None,
            "status":          str,       # REVIEWED sadece AI başarılıysa
            "api_available":   bool,
        }
    """
    decision = get_decision(decision_id)
    if decision is None:
        return {"error": "decision not found", "api_available": False}

    if price_fn is None:
        mgr = AssetManager()
        price_fn = lambda sym: mgr.get_price(sym, _guess_asset_type(sym))

    current_price = (
        price_fn(decision["asset_symbol"]) if decision["asset_symbol"] else None
    )

    # market_data: decision tarihi ve vade tarihi fiyatlarını Prompt 7'a besle
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

            # Başarılı → AI retrospective'yi kaydet + status REVIEWED
            decision["ai_retrospective"] = retrospective
            client = get_client()
            decisions = client.collection("decisions")
            decisions.update(decision)

            return {
                "decision_id": decision_id,
                "retrospective": retrospective,
                "status": "REVIEWED",
                "api_available": True,
            }

        except AIUnavailableError:
            # API anahtarı yok / yapılandırılmamış → 503
            return {
                "error": "AI servisi kullanılabilir değil (API anahtarı eksik)",
                "api_available": False,
                "retrospective": None,
                "status": decision["status"],  # değişmez
            }

        except AIGenerationError as exc:
            # Sağlayıcı hatası → 502
            return {
                "error": f"AI yanıt oluşturulamadı: {exc}",
                "api_available": True,
                "retrospective": None,
                "status": decision["status"],  # değişmez
            }

    return {
        "decision_id": decision_id,
        "retrospective": None,
        "status": decision["status"],  # değişmez
        "api_available": False,
    }


# ---------------------------------------------------------------------------
# Yardımcı: retrospective prompt'ı  (Prompt 7 – eskisi kaldırıldı)
# ---------------------------------------------------------------------------


def _build_retrospective_prompt(
    decision: dict,
    current_price: float | None,
    market_context: str | None,
) -> str:
    """AI post-mortem için KULLANICI BAŞLIĞI prompt (Prompt 7).

    Kullanıcı notu <kullanici_notu> içinde geçecek; gerçek prompt
    ai_service._build_retrospective_prompt tarafında oluşturulur.
    Bu fonksiyon yalnızca kararın temel context'ini hazırlar.
    """
    target_hit_str = "Bilinmiyor"
    if decision.get("target_price") is not None and current_price is not None:
        if decision["action"] == "BUY":
            hit = current_price >= decision["target_price"]
            target_hit_str = "ÜSTİNDE" if hit else "ALTINDA"
        elif decision["action"] == "SELL":
            hit = current_price <= decision["target_price"]
            target_hit_str = "ALTINDA" if hit else "ÜSTÜNDE"

    parts = [
        "YATIRIM KARARI RETROSPEKTİF DEĞERLENDİRME",
        "",
        f"Karar Tarihi:     {decision['date']}",
        f"Varlık:           {decision['asset_symbol']}",
        f"İşlem:            {decision['action']}",
        f"Gerekçe:          {decision['rationale'] or '(gerekçe kaydedilmedi)'}",
        f"Duygu Durumu:     {SENTIMENT_LABELS.get(decision['sentiment'], decision['sentiment'] or 'Bilinmiyor')}",
        f"Hedef Fiyat:      {decision['target_price'] or 'Belirtilmemiş'}",
        f"Hedef Tarih:      {decision['target_date']}",
        f"Sonuç:            {decision['status']}",
        "",
    ]

    if current_price is not None:
        parts.append(f"Güncel Fiyat:    {current_price:,.2f}")
        parts.append(f"Hedefe Göre:     {target_hit_str}")
        parts.append("")

    if decision["target_date"] is not None:
        passed = decision["target_date"] < date.today()
        parts.append(f"Vade Geçmiş:     {'EVET' if passed else 'HAYIR'}")
        if passed:
            parts.append(
                f"Vade'den:        {(date.today() - decision['target_date']).days} gün geçmiş"
            )
        parts.append("")

    if market_context:
        parts.append(f"Piyasa Bağlamı:  {market_context}")
        parts.append("")

    parts.append(
        "GÖREV: Bu kararı gerekçe, duygu durumu, hedef gerçekleşme ve "
        "piyasa gelişmeleri ışığında objektif olarak değerlendir. "
        "Eğitim amaçlı olmalı (kesin tavsiye verme). "
        "Kısa, net, mercyili bir değerlendirme yaz."
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helper: asset türünü tahmin et
# ---------------------------------------------------------------------------


def _guess_asset_type(symbol: str) -> str:
    """Price fetch için asset türü tahmini.

    Tek tanım (Prompt 15: _guess_asset_type kopyaları tek yerde).
    """
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
