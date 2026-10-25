"""
FutureWallet - Karar Günlüğü Servisi (Decision Journal)

Yatırımcının alınan stratejik kararlarını kaydeder, duygu durumlarını
tag'ler, hedef fiyat/vade gerçekleşme kontrolü yapar ve AI post-mortem
mantığına alan açar.

MVP §3.2, TODO 2.2.
"""

from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from db import Decision, Transaction
from services.multi_asset_manager import AssetManager
from services.ai_service import DecisionSupportAI
import config


# ---------------------------------------------------------------------------
# Duygu durum tag'leri (MVP §3.2 "duygu durum tag'leri")
# ---------------------------------------------------------------------------

SENTIMENT_ALLOWED = frozenset({
    "FOMO",           # FOMO — Fersizlik
    "STRATEGIC",      # Stratejik Analiz
    "PANIC",          # Panik Satışı
    "DIVIDEND",       # Temettü/Gelir
    "RISK_REDUCTION", # Risk Azaltma
})

SENTIMENT_LABELS = {
    "FOMO":           "FOMO (Fersizlik)",
    "STRATEGIC":      "Stratejik Analiz",
    "PANIC":          "Panik Satışı",
    "DIVIDEND":       "Temettü/Gelir",
    "RISK_REDUCTION": "Risk Azaltma",
}

ACTION_ALLOWED = frozenset({"BUY", "SELL", "HOLD"})
STATUS_ALLOWED  = frozenset({"OPEN", "REVIEWED", "EXPIRED"})


# ---------------------------------------------------------------------------
# 1. create_decision
# ---------------------------------------------------------------------------

def create_decision(
    session: Session,
    asset_symbol: str,
    action: str,
    rationale: Optional[str] = None,
    sentiment: Optional[str] = None,
    target_price: Optional[float] = None,
    target_date: Optional[date] = None,
    transaction_id: Optional[str] = None,
) -> Decision:
    """
    Yeni bir karar kaydı oluşturur.

    Args:
        session: SQLAlchemy Session
        asset_symbol: Varlık sembolü (BTC, THYAO, GC=F, …)
        action: İşlem tipi — BUY, SELL, HOLD
        rationale: Karar gerekçesi (opsiyonel)
        sentiment: Duygu durum tag'i.
                   None → tag'siz kaydedilir.
                   Allowed: FOMO, STRATEGIC, PANIC, DIVIDEND, RISK_REDUCTION
        target_price: Hedef fiyat (opsiyonel)
        target_date: Hedef tarih (opsiyonel)
        transaction_id: İlgili transaction ID (opsiyonel, FK).

    Returns:
        Yeni Decision (session.commit() → caller'ın sorumluluğu).
    """
    action_upper = action.upper()
    if action_upper not in ACTION_ALLOWED:
        raise ValueError(f"action: {action!r} — allowed: {ACTION_ALLOWED}")

    if sentiment is not None and sentiment not in SENTIMENT_ALLOWED:
        raise ValueError(
            f"sentiment: {sentiment!r} — allowed: {SENTIMENT_ALLOWED}"
        )

    if transaction_id is not None:
        tx = session.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        ).scalars().first()
        if tx is None:
            raise ValueError(f"transaction_id={transaction_id} bulunamadı")

    dec = Decision(
        asset_symbol=asset_symbol.upper(),
        action=action_upper,
        rationale=rationale,
        sentiment=sentiment,
        target_price=target_price,
        target_date=target_date,
        transaction_id=transaction_id,
    )
    session.add(dec)
    return dec


# ---------------------------------------------------------------------------
# 2. get_decision
# ---------------------------------------------------------------------------

def get_decision(session: Session, decision_id: str) -> Optional[Decision]:
    """ID ile tek karar. Yoksa None."""
    return session.execute(
        select(Decision).where(Decision.id == decision_id)
    ).scalars().first()


# ---------------------------------------------------------------------------
# 3. list_decisions
# ---------------------------------------------------------------------------

def list_decisions(
    session: Session,
    status: Optional[str] = None,
    sentiment: Optional[str] = None,
    asset_symbol: Optional[str] = None,
    action: Optional[str] = None,
    target_date_from: Optional[date] = None,
    target_date_to: Optional[date] = None,
    limit: Optional[int] = None,
    order_by_date_desc: bool = True,
) -> List[Dict]:
    """
    Filtrelenmiş karar listesi.

    Args:
        session: SQLAlchemy Session
        status: OPEN | REVIEWED | EXPIRED
        sentiment: FOMO | STRATEGIC | PANIC | DIVIDEND | RISK_REDUCTION
        asset_symbol: Varlık sembolü (Büyük/Küçük harf farketmez)
        action: BUY | SELL | HOLD
        target_date_from: target_date >= bu tarih
        target_date_to: target_date <= bu tarih
        limit: Maksimum kayıt sayısı
        order_by_date_desc: True → en yeni ilk

    Returns:
        List[Dict] — her karar için serialization (decision_to_dict).
    """
    stmt = select(Decision)

    if status is not None:
        stmt = stmt.where(Decision.status == status.upper())
    if sentiment is not None:
        stmt = stmt.where(Decision.sentiment == sentiment)
    if asset_symbol is not None:
        stmt = stmt.where(Decision.asset_symbol == asset_symbol.upper())
    if action is not None:
        stmt = stmt.where(Decision.action == action.upper())
    if target_date_from is not None:
        stmt = stmt.where(Decision.target_date >= target_date_from)
    if target_date_to is not None:
        stmt = stmt.where(Decision.target_date <= target_date_to)

    stmt = stmt.order_by(
        Decision.date.desc() if order_by_date_desc else Decision.date.asc()
    )

    if limit is not None:
        stmt = stmt.limit(limit)

    decisions = session.execute(stmt).scalars().all()
    return [decision_to_dict(d) for d in decisions]


# ---------------------------------------------------------------------------
# 4. update_decision
# ---------------------------------------------------------------------------

def update_decision(
    session: Session,
    decision_id: str,
    rationale: Optional[str] = None,
    sentiment: Optional[str] = None,
    target_price: Optional[float] = None,
    target_date: Optional[date] = None,
    status: Optional[str] = None,
) -> Optional[Decision]:
    """
    Karar alanlarını günceller. None → o alan değiştirilmez.

    Args:
        session: SQLAlchemy Session
        decision_id: Karar ID
        rationale: Yeni gerekçe (None → değiştirmeme)
        sentiment: Yeni duygu tag'i (None → değiştirmeme)
        target_price: Yeni hedef fiyat (None → değiştirmeme)
        target_date: Yeni hedef tarih (None → değiştirmeme)
        status: Yeni durum (None → değiştirmeme)

    Returns:
        Güncellenmiş Decision. Yoksa None.
    """
    dec = get_decision(session, decision_id)
    if dec is None:
        return None

    if rationale is not None:
        dec.rationale = rationale
    if sentiment is not None:
        if sentiment not in SENTIMENT_ALLOWED:
            raise ValueError(f"sentiment: {sentiment} not allowed")
        dec.sentiment = sentiment
    if target_price is not None:
        dec.target_price = target_price
    if target_date is not None:
        dec.target_date = target_date
    if status is not None:
        if status.upper() not in STATUS_ALLOWED:
            raise ValueError(f"status: {status!r} — allowed: {STATUS_ALLOWED}")
        dec.status = status.upper()

    return dec


# ---------------------------------------------------------------------------
# 5. close_decision
# ---------------------------------------------------------------------------

def close_decision(session: Session, decision_id: str) -> Optional[Decision]:
    """
    Kararı REVIEWED durumuna taşıır.
    Kullanıcı tarafından gözden geçirilmiş/hasil alınmış anlamında.
    """
    return update_decision(session, decision_id, status="REVIEWED")


# ---------------------------------------------------------------------------
# 6. decision_to_dict
# ---------------------------------------------------------------------------

def decision_to_dict(decision: Decision) -> Dict:
    """Decision → flat dict (API response / serialization)."""
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


# ---------------------------------------------------------------------------
# 7. get_sentiment_summary
# ---------------------------------------------------------------------------

def get_sentiment_summary(session: Session) -> Dict[str, int]:
    """
    Her sentiment tag'ına göre karar sayıları.

    Returns:
        {"FOMO": 5, "STRATEGIC": 12, "PANIC": 3, "DIVIDEND": 2, "RISK_REDUCTION": 1}
    """
    rows = session.execute(
        select(Decision.sentiment, func.count(Decision.id))
        .where(Decision.sentiment.isnot(None))
        .group_by(Decision.sentiment)
    ).all()

    out = {s: 0 for s in SENTIMENT_ALLOWED}
    for sentiment, cnt in rows:
        out[sentiment] = cnt
    return out


# ---------------------------------------------------------------------------
# 8. get_status_summary
# ---------------------------------------------------------------------------

def get_status_summary(session: Session) -> Dict[str, int]:
    """OPEN / REVIEWED / EXPIRED sayımları."""
    rows = session.execute(
        select(Decision.status, func.count(Decision.id))
        .group_by(Decision.status)
    ).all()

    out = {s: 0 for s in STATUS_ALLOWED}
    for status, cnt in rows:
        out[status] = cnt
    return out


# ---------------------------------------------------------------------------
# 9. check_decision_target
# ---------------------------------------------------------------------------

def check_decision_target(
    session: Session,
    decision_id: str,
    price_fn: Optional[Callable[[str], Optional[float]]] = None,
) -> Dict:
    """
    Bir kararın hedef fiyat / vade gerçekleşme durumunu kontrol eder.

    BUY → hedef fiyatın üzerindeyse "hit"
    SELL → hedef fiyatın altındaysa "hit"

    Returns:
        {
            "decision_id":        str,
            "asset_symbol":       str,
            "action":             str,
            "target_price":       float | None,
            "target_date":        date | None,
            "current_price":      float | None,
            "target_hit":         bool | None,   # hedef gerçekleşti mi
            "target_date_passed": bool,          # vade geçti mi
            "status_suggestion":  str,           # OPEN | REVIEWED önerisi
        }
    """
    dec = get_decision(session, decision_id)
    if dec is None:
        return {"error": "decision not found"}

    if price_fn is None:
        mgr = AssetManager()
        price_fn = lambda sym: mgr.get_price(sym, _guess_asset_type(sym))

    current_price = price_fn(dec.asset_symbol) if dec.asset_symbol else None

    target_hit: Optional[bool] = None
    if dec.target_price is not None and current_price is not None:
        if dec.action == "BUY":
            target_hit = current_price >= dec.target_price
        elif dec.action == "SELL":
            target_hit = current_price <= dec.target_price
        # HOLD'de hedef fiyat tanımı zayıf → None bırak

    target_date_passed = (
        dec.target_date is not None and dec.target_date < date.today()
    )

    # Status önerisi
    if dec.status == "REVIEWED":
        status_suggestion = "REVIEWED"
    elif target_date_passed:
        # Vade geçmiş → ne olursa olsun review edilmeli
        status_suggestion = "REVIEWED"
    else:
        status_suggestion = "OPEN"

    return {
        "decision_id":        dec.id,
        "asset_symbol":       dec.asset_symbol,
        "action":             dec.action,
        "target_price":       dec.target_price,
        "target_date":        dec.target_date.isoformat()
                              if dec.target_date else None,
        "current_price":      current_price,
        "target_hit":         target_hit,
        "target_date_passed": target_date_passed,
        "status_suggestion":  status_suggestion,
    }


# ---------------------------------------------------------------------------
# 10. get_decisions_due_for_review
# ---------------------------------------------------------------------------

def get_decisions_due_for_review(session: Session) -> List[Dict]:
    """
    Hedef tarihi geçmiş ama henüz REVIEWED edilmemiş kararlar.

    Returns:
        List[Dict] — decision_to_dict ile serialize edilmiş.
    """
    stmt = (
        select(Decision)
        .where(Decision.status == "OPEN")
        .where(Decision.target_date.isnot(None))
        .where(Decision.target_date < date.today())
        .order_by(Decision.target_date.asc())
    )
    return [decision_to_dict(d) for d in session.execute(stmt).scalars().all()]


# ---------------------------------------------------------------------------
# 11. auto_close_expired_decisions
# ---------------------------------------------------------------------------

def auto_close_expired_decisions(
    session: Session,
    days_before: int = 0,
) -> List[Decision]:
    """
    Hedef tarihleri dolmuş ama henüz REVIEWED edilmemiş kararları
    otomatik EXPIRED yapar.

    Args:
        session: SQLAlchemy Session
        days_before: Hedef tarih bu kadar gün önce geçtiyse kapat.
                     0 → bugün geçmiş hedef tarihler.

    Returns:
        Kapatılan (artık EXPIRED) Decision listesi.
    """
    cutoff = date.today() - timedelta(days=days_before)

    stmt = (
        select(Decision)
        .where(Decision.status == "OPEN")
        .where(Decision.target_date.isnot(None))
        .where(Decision.target_date < cutoff)
    )
    expired = session.execute(stmt).scalars().all()
    for dec in expired:
        dec.status = "EXPIRED"
    return expired


# ---------------------------------------------------------------------------
# 12. generate_ai_retrospective  (opsiyonel, API key gerekir)
# ---------------------------------------------------------------------------

def generate_ai_retrospective(
    session: Session,
    decision_id: str,
    price_fn: Optional[Callable[[str], Optional[float]]] = None,
    market_context: Optional[str] = None,
) -> Dict:
    """
    Bir karar için AI post-mortem (retrospektif) üretir ve
    decision.ai_retrospective alanına yazar.

    Bu fonksiyon çalışması için GOOGLE_API_KEY env değişkeni tanımlı
    olmalıdır. Yoksa retrospective üretilir ama kaydedilmez ve
    response'da buna dair bilgi verilir.

    Args:
        session: SQLAlchemy Session
        decision_id: Karar ID
        price_fn: (asset_symbol) → güncel fiyat.
                  None → AssetManager default.
        market_context: İsteğe bağlı piyasa bağlamı metni.
                        Örn: "Piyasa bugün yükselen trendte, BTC 50K'nın üzerinde."

    Returns:
        {
            "decision_id":     str,
            "retrospective":   str | None,   # üretilen metin (None if API key missing)
            "status":          str,           # REVIEWED (retrospektif kaydedildikten sonra)
            "api_available":   bool,
        }
    """
    dec = get_decision(session, decision_id)
    if dec is None:
        return {"error": "decision not found", "api_available": False}

    if price_fn is None:
        mgr = AssetManager()
        price_fn = lambda sym: mgr.get_price(sym, _guess_asset_type(sym))

    current_price = price_fn(dec.asset_symbol) if dec.asset_symbol else None

    # Retrospektif prompt'i
    prompt = _build_retrospective_prompt(dec, current_price, market_context)

    api_available = bool(config.GOOGLE_API_KEY)
    retrospective: Optional[str] = None

    if api_available:
        try:
            ai = DecisionSupportAI(api_key=config.GOOGLE_API_KEY)
            retrospective = ai.get_ai_recommendation({"user_question": prompt})
        except Exception as e:
            retrospective = f"[AI retrospektif hatası: {e}]"
            api_available = False  # hata durumunda de facto unavailable

    # Kaydet
    if retrospective is not None:
        dec.ai_retrospective = retrospective
        dec.status = "REVIEWED"

    return {
        "decision_id":   dec.id,
        "retrospective": retrospective,
        "status":        dec.status,
        "api_available": api_available,
    }


# ---------------------------------------------------------------------------
# Yardımcı: retrospective prompt'ı
# ---------------------------------------------------------------------------

def _build_retrospective_prompt(
    dec: Decision,
    current_price: Optional[float],
    market_context: Optional[str],
) -> str:
    """
    Bir karar için AI post-mortem prompt'ı üretir.

    Karar bağlamı + güncel piyasa durumu → AI'ya "bu karar nasıl değerlendirilir?"
    sorusunu sorar.
    """
    target_hit_str = "Bilinmiyor"
    if dec.target_price is not None and current_price is not None:
        if dec.action == "BUY":
            hit = current_price >= dec.target_price
            target_hit_str = ("ÜSTÜNDE" if hit else "ALTINDA")
        elif dec.action == "SELL":
            hit = current_price <= dec.target_price
            target_hit_str = ("ALTINDA" if hit else "ÜSTÜNDE")

    parts = [
        f"YATIRIM KARARI RETROSPEKTİF DEĞERLENDİRME",
        "",
        f"Karar Tarihi:     {dec.date.strftime('%Y-%m-%d') if dec.date else 'Bilinmiyor'}",
        f"Varlık:           {dec.asset_symbol}",
        f"İşlem:            {dec.action}",
        f"Gerekçe:          {dec.rationale or '(gerekçe kaydedilmedi)'}",
        f"Duygu Durumu:     {SENTIMENT_LABELS.get(dec.sentiment, dec.sentiment or 'Bilinmiyor')}",
        f"Hedef Fiyat:      {dec.target_price or 'Belirtilmemiş'}",
        f"Hedef Tarih:      {dec.target_date.isoformat() if dec.target_date else 'Belirtilmemiştir'}",
        f"Sonuç:            {dec.status}",
        "",
    ]

    if current_price is not None:
        parts.append(f"Güncel Fiyat:    {current_price:,.2f}")
        parts.append(f"Hedefe Göre:     {target_hit_str}")
        parts.append("")

    if dec.target_date is not None:
        passed = dec.target_date < date.today()
        parts.append(f"Vade Geçmiş:     {'EVET' if passed else 'HAYIR'}")
        if passed:
            days_late = (date.today() - dec.target_date).days
            parts.append(f"Vade'den:        {days_late} gün geçmiş")
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
# Helper: asset türünü tahmin et (multi_asset_manager'dan ayrı)
# ---------------------------------------------------------------------------

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
    return "crypto"
