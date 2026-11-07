"""
Ledger ve Karar Günlüğü Entegrasyon Testleri (Prompt 7 Kabul Kriterleri).
========================================================================
- 2 BUY + 1 SELL sonrası portföy ortalama maliyeti doğru hesaplanır.
- Stok aşan SELL işleminde 409 Conflict fırlatılır.
- Void edilen işlem snapshot'ı etkilemez.
- GET /api/decisions/stats 200 döner (route çakışması yoktur).
"""

from __future__ import annotations

import pytest
from fastapi import status


@pytest.mark.pb
def test_buy_sell_average_cost_and_snapshot(api_client, pb_clean) -> None:
    headers = {"Authorization": "Bearer test-secret-token"}

    # 1. BUY 10 BTC @ 50,000
    r1 = api_client.post(
        "/api/transactions",
        json={"asset_symbol": "BTC", "tx_type": "BUY", "quantity": 10.0, "price": 50000.0},
        headers=headers,
    )
    assert r1.status_code == status.HTTP_201_CREATED

    # 2. BUY 10 BTC @ 60,000 (Ortalama maliyet: 55,000)
    r2 = api_client.post(
        "/api/transactions",
        json={"asset_symbol": "BTC", "tx_type": "BUY", "quantity": 10.0, "price": 60000.0},
        headers=headers,
    )
    assert r2.status_code == status.HTTP_201_CREATED

    # 3. SELL 5 BTC @ 70,000 (Kalan: 15 BTC, ortalama maliyet hala 55,000)
    r3 = api_client.post(
        "/api/transactions",
        json={"asset_symbol": "BTC", "tx_type": "SELL", "quantity": 5.0, "price": 70000.0},
        headers=headers,
    )
    assert r3.status_code == status.HTTP_201_CREATED

    # Snapshot al
    snap_resp = api_client.get("/api/portfolio/snapshot", headers=headers)
    assert snap_resp.status_code == status.HTTP_200_OK
    snap = snap_resp.json()
    btc_holding = next(h for h in snap["holdings"] if h["asset_symbol"] == "BTC")
    assert btc_holding["quantity"] == 15.0
    assert btc_holding["average_cost"] == 55000.0
    assert btc_holding["total_cost"] == 15.0 * 55000.0


@pytest.mark.pb
def test_overselling_returns_409_conflict(api_client, pb_clean) -> None:
    headers = {"Authorization": "Bearer test-secret-token"}

    # Elde 2 ETH varken 5 ETH satmaya çalış
    api_client.post(
        "/api/transactions",
        json={"asset_symbol": "ETH", "tx_type": "BUY", "quantity": 2.0, "price": 3000.0},
        headers=headers,
    )

    resp = api_client.post(
        "/api/transactions",
        json={"asset_symbol": "ETH", "tx_type": "SELL", "quantity": 5.0, "price": 3500.0},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert "Yetersiz stok" in resp.json()["detail"]


@pytest.mark.pb
def test_void_transaction_excludes_from_snapshot(api_client, pb_clean) -> None:
    headers = {"Authorization": "Bearer test-secret-token"}

    # BUY 100 THYAO
    r1 = api_client.post(
        "/api/transactions",
        json={"asset_symbol": "THYAO.IS", "tx_type": "BUY", "quantity": 100.0, "price": 250.0},
        headers=headers,
    )
    tx_id = r1.json()["id"]

    # Void et
    void_resp = api_client.delete(f"/api/transactions/{tx_id}", headers=headers)
    assert void_resp.status_code == status.HTTP_200_OK

    # Snapshot'ta görünmemeli
    snap_resp = api_client.get("/api/portfolio/snapshot", headers=headers)
    snap = snap_resp.json()
    thyao = [h for h in snap["holdings"] if h["asset_symbol"] == "THYAO.IS"]
    assert len(thyao) == 0


@pytest.mark.pb
def test_decisions_stats_route_not_404(api_client, pb_clean) -> None:
    headers = {"Authorization": "Bearer test-secret-token"}

    # Karar ekle
    api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "THYAO.IS",
            "action": "BUY",
            "sentiment": "STRATEGIC",
            "rationale": "Test stats",
        },
        headers=headers,
    )

    # Stats çağrısı 200 dönmeli
    resp = api_client.get("/api/decisions/stats", headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "sentiment_counts" in data
    assert "status_counts" in data
    assert data["sentiment_counts"]["STRATEGIC"] >= 1
