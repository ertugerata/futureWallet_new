"""
FutureWallet – Kimlik doğrulama, CORS, Host doğrulama testleri (Prompt 1).

Kabul kriterleri:
- Token yokken /api/decisions → 401.
- Yanlış token → 401.
- Doğru token → 200.
- Origin: https://evil.example ile preflight → Access-Control-Allow-Origin DÖNDÜRMEZ.
- Host: evil.example → 400.
- Kimlik doğrulama yalnızca PB JWT iledir; statik API_TOKEN kaldırıldı.
- Aynı karar için retrospective 60 sn içinde tekrar → 429.
"""

from __future__ import annotations

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


def test_valid_token_returns_200_or_201(api_client, test_db, auth_headers) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "test gerekçe",
            "sentiment": "STRATEGIC",
        },
        headers=auth_headers,
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
# 5. Retrospective hız sınırı (kullanıcı + karar başına 60 sn'de 1)
# ---------------------------------------------------------------------------


def _make_decision(api_client, headers) -> str:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "retro limit testi",
            "sentiment": "STRATEGIC",
        },
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED
    return resp.json()["id"]


def test_retrospective_second_call_within_60s_returns_429(api_client, test_db, make_user) -> None:
    _, token, _ = make_user("retro_rl@test.local")
    headers = {"Authorization": f"Bearer {token}"}
    decision_id = _make_decision(api_client, headers)

    first = api_client.post(f"/api/decisions/{decision_id}/retrospective", headers=headers)
    # OPENROUTER_API_KEY yoksa 503 olabilir; limit bunu sayar
    assert first.status_code in (
        status.HTTP_200_OK,
        status.HTTP_201_CREATED,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ), f"1. çağrı {first.status_code}: {first.text}"

    second = api_client.post(f"/api/decisions/{decision_id}/retrospective", headers=headers)
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_retrospective_rate_limit_isolated_per_decision_and_user(
    api_client, test_db, make_user
) -> None:
    _, token_a, _ = make_user("retro_iso_a@test.local")
    _, token_b, _ = make_user("retro_iso_b@test.local")
    ha = {"Authorization": f"Bearer {token_a}"}
    hb = {"Authorization": f"Bearer {token_b}"}

    dec1 = _make_decision(api_client, ha)
    dec2 = _make_decision(api_client, ha)

    api_client.post(f"/api/decisions/{dec1}/retrospective", headers=ha)
    # Farklı karar: A'nın sayacı ondan bağımsız → limit dışı
    other = api_client.post(f"/api/decisions/{dec2}/retrospective", headers=ha)
    assert other.status_code != status.HTTP_429_TOO_MANY_REQUESTS

    # Aynı karar, kullanıcı B: B'nin sayacı kendi; sahiplik yok → 404 (429 değil)
    foreign = api_client.post(f"/api/decisions/{dec1}/retrospective", headers=hb)
    assert foreign.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# 6. 64 KB Payload Limiti ve Kullanıcı İzolasyonu Testleri (Prompt 6)
# ---------------------------------------------------------------------------


def test_payload_too_large_returns_413(api_client, auth_headers) -> None:
    """64 KB üzeri istek gövdesi 413 Payload Too Large dönmeli."""
    large_payload = {"data": "x" * (65 * 1024)}
    resp = api_client.post(
        "/api/decisions",
        json=large_payload,
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


def test_cross_user_decision_delete_returns_404(api_client, make_user, pb_clean) -> None:
    """Kullanıcı B, Kullanıcı A'ya ait kararı silememeli (404)."""
    _user_a_id, token_a, _ = make_user("usera_del@test.local", "Pass12345!")
    _user_b_id, token_b, _ = make_user("userb_del@test.local", "Pass12345!")

    # User A karar oluşturur
    create_resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "User A kararı",
            "sentiment": "STRATEGIC",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert create_resp.status_code == status.HTTP_201_CREATED
    dec_id = create_resp.json()["id"]

    # User B bu kararı silmeye çalışır -> 404
    del_resp = api_client.delete(
        f"/api/decisions/{dec_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert del_resp.status_code == status.HTTP_404_NOT_FOUND
