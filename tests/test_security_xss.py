"""
FutureWallet – Stored XSS & girdi doğrulama testleri (Prompt 2).

Kabul kriterleri:
- POST /api/decisions ile XSS payload'lı asset_symbol → 422.
- Geçerli semboller (BTC, GC=F, ^GSPC, THYAO.IS, BTC/USDT) → 201.
- CSP başlığı /web/ yanıtında mevcut.
- JS tarafında innerHTML yalnızca sabit literal'da (grep kanıtı).
"""

from __future__ import annotations

import pytest
from fastapi import status

# ---------------------------------------------------------------------------
# 1. Asset symbol regex doğrulama
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "symbol,should_pass",
    [
        ("BTC", True),
        ("GC=F", True),
        ("^GSPC", True),
        ("THYAO.IS", True),
        ("BTC/USDT", True),
        ("XAUUSD", True),
        ("USDTRY=X", True),
        # rejected cases
        ("<img src=x onerror=1>", False),
        ("<script>alert(1)</script>", False),
        ("", False),  # empty → regex uymuyor (min 1 karakter)
        ("a" * 21, False),  # 21 karakter → limit aşıldı
        ("sembol; DROP TABLE transactions;", False),
        ("sembol with space", False),  # boşluk regex'de yok
    ],
)
def test_asset_symbol_validation(
    api_client,
    test_db,
    symbol: str,
    should_pass: bool,
) -> None:
    r"""asset_symbol regex ^[A-Z0-9.=^\-/]{1,20}$ uyumluylar kabul edilir, diğerleri 422."""
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": symbol,
            "action": "BUY",
            "rationale": "test gerekçe",
            "sentiment": "STRATEGIC",
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )

    if should_pass:
        assert resp.status_code == status.HTTP_201_CREATED, (
            f"'{symbol}' kabul edilmeliydi ama {resp.status_code}: {resp.text}"
        )
    else:
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, (
            f"'{symbol}' reddedilmeliydi ama {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# 2. Action literal doğrulama
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action",
    ["BUY", "SELL", "HOLD"],
)
def test_valid_action_accepted(
    api_client,
    test_db,
    action: str,
) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": action,
            "rationale": "test",
            "sentiment": "STRATEGIC",
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert resp.status_code == status.HTTP_201_CREATED


def test_invalid_action_rejected(api_client, test_db) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "ABC",
            "rationale": "test",
            "sentiment": "STRATEGIC",
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# 3. Sentiment literal + case-insensitive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentiment",
    ["FOMO", "STRATEGIC", "PANIC", "DIVIDEND", "OPPORTUNITY"],
)
def test_valid_sentiment_accepted(
    api_client,
    test_db,
    sentiment: str,
) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "test",
            "sentiment": sentiment,
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert resp.status_code == status.HTTP_201_CREATED


def test_risk_reduction_sentiment_rejected(api_client, test_db) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "test",
            "sentiment": "RISK_REDUCTION",
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# 4. Rationale max_length 5000
# ---------------------------------------------------------------------------


def test_rationale_too_long_rejected(api_client, test_db) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "x" * 5001,
            "sentiment": "STRATEGIC",
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_rationale_exactly_5000_accepted(api_client, test_db) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "x" * 5000,
            "sentiment": "STRATEGIC",
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert resp.status_code == status.HTTP_201_CREATED


# ---------------------------------------------------------------------------
# 5. Target price validation (gt=0, no inf/nan)
# ---------------------------------------------------------------------------


def test_target_price_negative_rejected(api_client, test_db) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "test",
            "sentiment": "STRATEGIC",
            "target_price": -5.0,
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_target_price_zero_ok(api_client, test_db) -> None:
    """gt=0 olduğu için 0 kabul edilmemeli. Ama business constraint: 0 olabilir?
    Prompt 2'de gt=0 → 0 reddedilmeli."""
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "test",
            "sentiment": "STRATEGIC",
            "target_price": 0.0,
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# 6. Target date parsing (date.fromisoformat, boş string → None)
# ---------------------------------------------------------------------------


def test_valid_target_date_accepted(api_client, test_db) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "test",
            "sentiment": "STRATEGIC",
            "target_date": "2026-12-31",
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert resp.status_code == status.HTTP_201_CREATED


def test_invalid_target_date_rejected(api_client, test_db) -> None:
    resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "rationale": "test",
            "sentiment": "STRATEGIC",
            "target_date": "not-a-date",
        },
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert resp.status_code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


# ---------------------------------------------------------------------------
# 7. CSP başlığı var mı
# ---------------------------------------------------------------------------


def test_security_headers_on_web_response(api_client) -> None:
    resp = api_client.get("/")
    csp = resp.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp, f"CSP header bulunamadı: {csp!r}"
    assert "object-src 'none'" in csp
    assert "base-uri 'none'" in csp


def test_x_content_type_options_header(api_client) -> None:
    resp = api_client.get("/")
    assert resp.headers.get("x-content-type-options") == "nosniff"


def test_referrer_policy_header(api_client) -> None:
    resp = api_client.get("/")
    assert resp.headers.get("referrer-policy") == "no-referrer"
