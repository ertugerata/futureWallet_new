"""
FutureWallet – OpenRouter AI Servisi
====================================
OpenRouter üzerinden LLM çağrıları (fallback zinciri, hız sınırı, hata semantiği).
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import httpx

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Özel istisna sınıfları (Prompt 8 – hata semantiği)
# ---------------------------------------------------------------------------


class AIUnavailableError(Exception):
    """API anahtarı yok / OpenRouter yapılandırılmamış → 503."""


class AIGenerationError(Exception):
    """Sağlayıcı hatası / tüm modeller başarısız → 502.

    Attributes:
        public_message: İstemciye güvenle dönülebilecek genel mesaj.
        detail: Loglama için detay (anahtar/URL içermeyen, 300 karaktere kırpılmış).
    """

    def __init__(self, public_message: str, detail: str | None = None):
        self.public_message = public_message
        self.detail = detail or public_message
        super().__init__(public_message)

    def __str__(self) -> str:
        return self.public_message


# ---------------------------------------------------------------------------
# Prompt güvenliği (Prompt 8 – prompt injection koruması)
# ---------------------------------------------------------------------------


def _sanitize_user_input(text: str, max_len: int = 2000) -> str:
    """Kullanıcı metnini sınırlayıcı etiket ile sarmala ve uzunluğunu kıs."""
    if not text:
        return ""
    # Etiket kaçırma: <user_input> ve </user_input> dizilerini HTML entity'ye çevir
    safe = text.replace("<user_input>", "&lt;user_input&gt;").replace("</user_input>", "&lt;/user_input&gt;")
    truncated = safe[:max_len]
    return f"<user_input>{truncated}</user_input>"


def _truncate_for_log(text: str, max_len: int = 300) -> str:
    """Log için metni kırp ve hassas verileri temizle."""
    if not text:
        return ""
    # API key pattern'lerini maskele
    cleaned = re.sub(r"(sk-or-[a-zA-Z0-9_-]{20,})", "sk-or-***", text)
    cleaned = re.sub(r"(Bearer\s+[a-zA-Z0-9_-]{20,})", "Bearer ***", cleaned)
    return cleaned[:max_len]


# ---------------------------------------------------------------------------
# Hız sınırlayıcı (Prompt 4 – AI hız sınırı)
# ---------------------------------------------------------------------------

_ai_rate_limits: dict[str, list[int]] = defaultdict(list)
_ai_daily_limits: dict[str, list[datetime]] = defaultdict(list)

AI_DAILY_LIMIT = int(os.environ.get("AI_DAILY_LIMIT_PER_USER", "30"))
AI_MINUTE_LIMIT = int(os.environ.get("AI_MINUTE_LIMIT_PER_USER", "5"))


def _check_ai_rate_limit(user_id: str, endpoint: str) -> tuple[bool, int | None]:
    """Kullanıcı için AI hız sınırını kontrol et.

    Returns:
        (allowed, retry_after_seconds)
    """
    now = datetime.now()
    minute_key = f"{user_id}:{endpoint}:minute"
    daily_key = f"{user_id}:{endpoint}:daily"

    # Dakikalık pencere (son 60 saniye)
    minute_ago = now - timedelta(seconds=60)
    _ai_rate_limits[minute_key] = [ts for ts in _ai_rate_limits[minute_key] if ts > minute_ago.timestamp()]

    # Günlük pencere
    day_ago = now - timedelta(days=1)
    _ai_daily_limits[daily_key] = [dt for dt in _ai_daily_limits[daily_key] if dt > day_ago]

    if len(_ai_rate_limits[minute_key]) >= AI_MINUTE_LIMIT:
        retry_after = int(60 - (now.timestamp() - _ai_rate_limits[minute_key][0]))
        return False, max(retry_after, 1)

    if len(_ai_daily_limits[daily_key]) >= AI_DAILY_LIMIT:
        retry_after = int(86400 - (now - _ai_daily_limits[daily_key][0]).total_seconds())
        return False, max(retry_after, 1)

    # İzin ver - kaydet
    _ai_rate_limits[minute_key].append(int(now.timestamp()))
    _ai_daily_limits[daily_key].append(now)
    return True, None


def reset_ai_rate_limits() -> None:
    """Testler için AI hız sınırlarını sıfırla."""
    _ai_rate_limits.clear()
    _ai_daily_limits.clear()


# ---------------------------------------------------------------------------
# Sistem Promptları
# ---------------------------------------------------------------------------

_RETROSPECTIVE_SYSTEM_PROMPT = """Sen bir finansal karar günlüğü (decision journal) analiz asistanısın.
Kullanıcının geçmiş bir yatırım kararını ve piyasa gerçekleşmesini karşılaştırıp,
Türkçe, öğretici ve yargılamayan bir dilde retrospektif analiz üret.
Kesinlikle yatırım tavsiyesi verme; sadece karar sürecini analiz et.
Yanıt en fazla 500 kelime."""


_RISK_NARRATIVE_SYSTEM_PROMPT = """Sen bir finansal risk anlatıcısın.
Monte Carlo / stres testi simülasyon çıktılarını alıp,
Türkçe, sade ve eyleme geçirilebilir bir risk özeti üret.
Kesinlikle yatırım tavsiyesi verme; sadece riskleri açıkla.
Yanıt en fazla 400 kelime."""


def _build_retrospective_prompt(
    decision: dict[str, Any],
    market_data: dict[str, Any] | None = None,
) -> str:
    """Karar POST-MORTEM prompt'u."""
    symbol = decision.get("asset_symbol", "")
    action = decision.get("action", "")
    sentiment = decision.get("sentiment", "")
    rationale = decision.get("rationale", "")
    target_price = decision.get("target_price")
    target_date = decision.get("target_date")
    status = decision.get("status", "OPEN")
    decision_date = decision.get("decision_date")

    rationale_wrapped = _sanitize_user_input(rationale)

    prompt_parts = [
        "Karar detayı:",
        f"  Varlık: {symbol}",
        f"  İşlem: {action}",
        f"  Duygu Durumu: {sentiment}",
        f"  Karar Tarihi: {decision_date if decision_date else 'Belirtilmemiş'}",
        f"  Hedef Fiyat: {target_price if target_price else 'Belirtilmemiş'}",
        f"  Hedef Vade: {target_date if target_date else 'Belirtilmemiş'}",
        f"  Karar Durumu: {status}",
        "",
        f"Karar Gerekçesi:\n{rationale_wrapped}",
    ]

    if market_data:
        price_on_decision = market_data.get("price_on_decision")
        price_on_maturity = market_data.get("price_on_maturity")
        prompt_parts.append("")
        prompt_parts.append("Piyasa Gerçekleşmesi:")
        if price_on_decision is not None:
            prompt_parts.append(f"  Karar Anındaki Fiyat: {price_on_decision}")
        if price_on_maturity is not None:
            prompt_parts.append(f"  Vade Anındaki Fiyat: {price_on_maturity}")

    return "\n".join(prompt_parts)


def _build_risk_narrative_prompt(
    simulation_result: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> str:
    """Risk anlatısı için kullanıcı prompt'u."""
    parts = ["Simülasyon Özeti:"]
    if simulation_result:
        parts.append(f"  Simülasyon Sayısı: {simulation_result.get('n_simulations', '?')}")
        parts.append(f"  Gün Sayısı: {simulation_result.get('days', '?')}")
        percentiles = simulation_result.get("percentile_values", {})
        for key, val in percentiles.items():
            parts.append(f"  {key}: {val}")
    else:
        parts.append("  Simülasyon verisi sağlanmadı.")

    if context:
        parts.append("")
        parts.append(f"Bağlam: {_sanitize_user_input(str(context))}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# OpenRouter API İstemcisi & Model Fallback
# ---------------------------------------------------------------------------


def _call_openrouter_with_fallback(
    system_prompt: str,
    user_prompt: str,
    api_key: str | None = None,
    models: list[str] | None = None,
) -> str:
    """OpenRouter üzerinden fallback zinciri ile çağrı yapar."""
    key = api_key if api_key is not None else config.OPENROUTER_API_KEY
    if not key or not key.strip():
        raise AIUnavailableError("OpenRouter API anahtarı yapılandırılmadı (OPENROUTER_API_KEY).")

    candidate_models = models or [
        m.strip() for m in config.OPENROUTER_MODELS.split(",") if m.strip()
    ]
    if not candidate_models:
        raise AIGenerationError(
            "AI model listesi boş. OPENROUTER_MODELS ortam değişkenini ayarlayın.",
            "OPENROUTER_MODELS is empty",
        )

    base_url = config.OPENROUTER_BASE_URL.rstrip("/")
    url = f"{base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://futurewallet.app",
        "X-Title": "FutureWallet",
        "Content-Type": "application/json",
    }

    last_error: str | None = None

    with httpx.Client(timeout=30.0) as client:
        for model_name in candidate_models:
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
            }
            try:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        content = choices[0]["message"].get("content", "")
                        if content:
                            if "yatırım tavsiyesi" not in content.lower():
                                content += "\n\n*Yasal Uyarı: Bu analiz yatırım tavsiyesi niteliğinde değildir.*"
                            return content
                    logger.warning("OpenRouter model %s boş yanıt döndü", model_name)
                    continue

                if resp.status_code in (429, 500, 502, 503, 504):
                    logger.warning(
                        "OpenRouter model %s HTTP %s verdi, sonrakine geçiliyor",
                        model_name,
                        resp.status_code,
                    )
                    last_error = _truncate_for_log(f"HTTP {resp.status_code}: {resp.text}")
                    continue

                # Diğer hatalar (4xx) - son hata olarak kaydet ama fallback'a geçme
                last_error = _truncate_for_log(f"HTTP {resp.status_code}: {resp.text}")
                logger.error("OpenRouter model %s hatalı yanıt: %s", model_name, last_error)
                break  # 4xx hatalarında fallback yapma

            except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                logger.warning("OpenRouter model %s ağ hatası: %s", model_name, net_err)
                last_error = _truncate_for_log(str(net_err))
                continue
            except Exception as e:
                logger.warning("OpenRouter model %s beklenmeyen hata: %s", model_name, e)
                last_error = _truncate_for_log(str(e))
                continue

    raise AIGenerationError(
        "AI sağlayıcısı geçici olarak yanıt vermedi",
        f"Tüm OpenRouter modelleri başarısız oldu. Son hata: {last_error}",
    )


def generate_decision_retrospective(
    decision: dict[str, Any],
    market_data: dict[str, Any] | None = None,
    api_key: str | None = None,
    models: list[str] | None = None,
) -> str:
    """Karar için AI post-mortem metni üretir."""
    user_prompt = _build_retrospective_prompt(decision, market_data)
    return _call_openrouter_with_fallback(
        system_prompt=_RETROSPECTIVE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        api_key=api_key,
        models=models,
    )


def generate_risk_narrative(
    simulation_result: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
    api_key: str | None = None,
    models: list[str] | None = None,
) -> str:
    """Monte Carlo / stres test sonucu için Türkçe risk anlatısı."""
    user_prompt = _build_risk_narrative_prompt(simulation_result, context)
    return _call_openrouter_with_fallback(
        system_prompt=_RISK_NARRATIVE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        api_key=api_key,
        models=models,
    )
