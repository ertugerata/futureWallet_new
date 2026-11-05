"""
FutureWallet – Kimlik doğrulama, CORS, Host doğrulama testleri (Prompt 1).

Kabul kriterleri:
- Token yokken /api/decisions → 401.
- Yanlış token → 401.
- Doğru token → 200.
- Origin: https://evil.example ile preflight → Access-Control-Allow-Origin DÖNDÜRMEZ.
- Host: evil.example → 400.
- API_TOKEN boş ve DEBUG=false → uygulama başlangıcı hata verir.
- Retrospective en fazla 5/dp dakikada, 60 sn içinde tekrar → 429.
"""

from __future__ import annotations

import pytest
from fastapi import status

# ---------------------------------------------------------------------------
# 1. Token yokken 401
# ---------------------------------------------------------------------------


def test_no_token_returns_401(api_client) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "test",
            "sentiment": "STRATEGIC",
        },
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_wrong_token_returns_401(api_client) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "test",
            "sentiment": "STRATEGIC",
        },
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_valid_token_returns_200_or_201(api_client, test_db) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "test gerekçe",
            "sentiment": "STRATEGIC",
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# 2. /health token'sız çalışmalı (statik endpoint'ler)
# ---------------------------------------------------------------------------


def test_health_no_token_ok(api_client) -> None:
    resp = api_client.get("/health")
    assert resp.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# 3. CORS: yabancı Origin reddedilmeli
# ---------------------------------------------------------------------------


def test_cors_evil_origin_not_allowed(api_client) -> None:
    """
    Evil bir origin'den gelen OPTIONS preflight isteği
    Access-Control-Allow-Origin header'ı döndürmemeli.
    """
    resp = api_client.options(
        "/api/decisions",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    acao = resp.headers.get("access-control-allow-origin", "")
    assert acao != "https://evil.example", (
        f"evil.example origin'i CORS'da yanıt vermemeli: {acao!r}"
    )
    # Ayrıca genel olarak * should NOT be present
    assert acao != "*"


def test_cors_allowed_origin_permitted(api_client) -> None:
    resp = api_client.options(
        "/api/decisions",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "GET",
        },
    )
    acao = resp.headers.get("access-control-allow-origin", "")
    assert acao == "http://localhost:8000" or acao == "*", (
        f"allowed origin kabul edilmeli: {acao!r}"
    )


# ---------------------------------------------------------------------------
# 4. Host doğrulama: evil.example → 400
# ---------------------------------------------------------------------------


def test_trusted_host_evil_rejected(api_client) -> None:
    resp = api_client.get(
        "/health",
        headers={"Host": "evil.example"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# 5. Retrospective ratelimit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_calls", [1, 2, 3, 4, 5])
def test_retrospective_under_rate_limit(
    api_client,
    test_db,
    n_calls: int,
) -> None:
    """
    Önce bir karar oluştur, ardından n_calls adet retrospective isteği at.
    5'erçe fazlası 429 dönmeli ama ilk 5'i 200/201/202/404/503 olabilir
    (mock Gemini kullanılıyor, AI_available=True).
    """
    # Karar oluştur (token ile)
    dec_resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "test",
            "sentiment": "STRATEGIC",
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert dec_resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    decision_id = dec_resp.json()["id"]

    for i in range(n_calls):
        resp = api_client.post(
            f"/api/decisions/{decision_id}/retrospective",
            headers={"Authorization": "Bearer test-secret-token"},
        )
        # Mock Gemini her şeyi kabul ettiği için 200 beklenir
        if i < 5:
            assert resp.status_code in (
                status.HTTP_200_OK,
                status.HTTP_201_CREATED,
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ), f"{i + 1}. çağrı {resp.status_code} döndü: {resp.text}"


def test_retrospective_rate_limit_429(api_client, test_db) -> None:
    """
    Aynı karar için dakikada 6. çağrı → 429.
    (Bu test, hız sınırı kont rolü yapar; fixture'taki hız sınırını
    test eder. 6 çağrı atıp 6.'un 429 gelmesini bekler.)
    """
    # Karar oluştur
    dec_resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "test rate limit",
            "sentiment": "STRATEGIC",
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert dec_resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    decision_id = dec_resp.json()["id"]

    # 6 çağrı at — 6. unten 429 dönmeli
    statuses = []
    for _ in range(6):
        resp = api_client.post(
            f"/api/decisions/{decision_id}/retrospective",
            headers={"Authorization": "Bearer test-secret-token"},
        )
        statuses.append(resp.status_code)

    # En az bir 429 bekleniyor (6. çağrı)
    assert status.HTTP_429_TOO_MANY_REQUESTS in statuses, (
        f"6. çağrı 429 dönmeliydi. Alınan kodlar: {statuses}"
    )
