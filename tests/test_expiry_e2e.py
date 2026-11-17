"""
EXPIRED zamanlayıcı job'ının gerçek PocketBase uçtan uca testi
(Hızlı kontrol 11 — job gövdesi `auto_close_expired_decisions` PB üzerinde hiç tetiklenmemişti).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status

from services.decision_service import auto_close_expired_decisions


@pytest.mark.pb
def test_expire_job_marks_overdue_decision_expired_with_outcome(
    api_client, pb_admin, make_user, pb_clean
) -> None:
    """Vadesi geçmiş OPEN karar job ile EXPIRED olur; outcome alanları PB cache'den dolar."""
    _, token, _ = make_user("expiry_e2e@test.local")
    headers = {"Authorization": f"Bearer {token}"}
    d0 = date.today() - timedelta(days=5)
    target = date.today() - timedelta(days=1)

    # PB price_history cache: dış servise (yfinance/ccxt) hiç gidilmez (Temel İlke: PB gerçek)
    for when, px in ((d0, 50000.0), (target, 60000.0)):
        pb_admin.collection("price_history").create(
            {
                "symbol": "BTC",
                "asset_type": "crypto",
                "date": f"{when.isoformat()} 00:00:00.000Z",
                "price": px,
            }
        )

    # decision_date geçmişte: giriş fiyatı d0'daki cache fiyatı olmalı (created değil)
    dec = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "sentiment": "STRATEGIC",
            "decision_date": d0.isoformat(),
            "target_date": target.isoformat(),
        },
        headers=headers,
    )
    assert dec.status_code == status.HTTP_201_CREATED
    dec_id = dec.json()["id"]

    # Vadesi geçmemiş ikinci karar EXPIRED OLMAMALI
    open_dec = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "BTC",
            "action": "BUY",
            "sentiment": "OPPORTUNITY",
            "target_date": (date.today() + timedelta(days=30)).isoformat(),
        },
        headers=headers,
    )
    assert open_dec.status_code == status.HTTP_201_CREATED
    open_id = open_dec.json()["id"]

    closed = auto_close_expired_decisions()
    assert [c["id"] for c in closed] == [dec_id]

    got = api_client.get(f"/api/decisions/{dec_id}", headers=headers).json()
    assert got["status"] == "EXPIRED"
    assert got["outcome_price"] == 60000.0
    assert got["outcome_return_pct"] == 20.0

    still = api_client.get(f"/api/decisions/{open_id}", headers=headers).json()
    assert still["status"] == "OPEN"
