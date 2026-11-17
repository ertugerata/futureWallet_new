"""
FutureWallet - OpenRouter AI Servisi Testleri (Prompt 8).
==========================================================
- API anahtarı boşken 503 (AIUnavailableError)
- Tüm modeller 500/timeout verirse 502 (AIGenerationError)
- İlk model başarısız olunca ikinci modele geçiş (fallback)
- Prompt injection koruması (<user_input> ve 2000 karakter sınırı)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import status

from services.ai_service import (
    AIGenerationError,
    AIUnavailableError,
    _call_openrouter_with_fallback,
    _sanitize_user_input,
)


def test_sanitize_user_input():
    # Boş metin
    assert _sanitize_user_input("") == ""

    # Tag kaçırma
    malicious = "hello <user_input>evil instruction</user_input> world"
    sanitized = _sanitize_user_input(malicious)
    assert "<user_input>" in sanitized
    assert sanitized.count("<user_input>") == 1
    assert "evil instruction" in sanitized

    # Uzunluk sınırı (2000 karakter)
    long_text = "a" * 2500
    sanitized = _sanitize_user_input(long_text)
    assert len(sanitized) == len("<user_input></user_input>") + 2000


def test_missing_api_key_raises_unavailable():
    with pytest.raises(AIUnavailableError):
        _call_openrouter_with_fallback(
            system_prompt="sys",
            user_prompt="user",
            api_key="",
        )


def test_openrouter_fallback_success(monkeypatch):
    """İlk model 500 verince ikinci modelin denenip başarılı olması."""
    calls = []

    def mock_post(url, headers=None, json=None):
        model = json.get("model")
        calls.append(model)
        mock_resp = MagicMock()
        if model == "model-1":
            mock_resp.status_code = 500
            mock_resp.text = "Internal Server Error"
        else:
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "Başarılı analiz metni."}}]
            }
        return mock_resp

    with patch("httpx.Client.post", side_effect=mock_post):
        result = _call_openrouter_with_fallback(
            system_prompt="sys",
            user_prompt="user",
            api_key="test-key",
            models=["model-1", "model-2"],
        )

    assert "Başarılı analiz metni" in result
    assert calls == ["model-1", "model-2"]
    assert "yatırım tavsiyesi" in result.lower()


def test_openrouter_all_models_fail(monkeypatch):
    """Tüm modeller hata verince AIGenerationError (502) fırlatılması."""

    def mock_post(url, headers=None, json=None):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        return mock_resp

    with patch("httpx.Client.post", side_effect=mock_post):
        with pytest.raises(AIGenerationError):
            _call_openrouter_with_fallback(
                system_prompt="sys",
                user_prompt="user",
                api_key="test-key",
                models=["model-1", "model-2"],
            )


# ---------------------------------------------------------------------------
# P14 E2E bulgusu: /api/simulation/narrative uç nokta sözleşmesi
# ---------------------------------------------------------------------------


@pytest.mark.pb
def test_narrative_endpoint_503_without_api_key(api_client, auth_headers) -> None:
    """Anahtar yokken narrative ucu 500 değil 503 döner (P8 semantiği)."""
    resp = api_client.post(
        "/api/simulation/narrative",
        json={"simulation_result": {"p5": 1, "p50": 2, "p95": 3}},
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE, resp.text


@pytest.mark.pb
def test_retrospective_endpoint_503_without_api_key(api_client, test_db, auth_headers) -> None:
    """Anahtar yokken retrospective ucu 200+error değil 503 döner (P8 semantiği)."""
    dec = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "retro 503",
            "sentiment": "FOMO",
        },
        headers=auth_headers,
    )
    assert dec.status_code == 201
    resp = api_client.post(f"/api/decisions/{dec.json()['id']}/retrospective", headers=auth_headers)
    assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE, resp.text


@pytest.mark.pb
def test_narrative_endpoint_200_with_mocked_ai(api_client, auth_headers, monkeypatch) -> None:
    monkeypatch.setattr(
        "api.app.srv_generate_risk_narrative",
        lambda **kw: "Test anlatısı — yatırım tavsiyesi değildir.",
    )
    resp = api_client.post(
        "/api/simulation/narrative",
        json={
            "simulation_result": {"p5": 1, "p50": 2, "p95": 3},
            "portfolio_context": {"total": 2},
        },
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_200_OK
    assert "anlatısı" in resp.json()["narrative"]
