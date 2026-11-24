"""
PocketBase Entegrasyon Testleri (Prompt 2 & Prompt 3 Kabul Kriterleri).
=======================================================================
Gerçek PocketBase (v0.40.6) sunucusuna karşı çalışır.
"""

from __future__ import annotations

import pytest


@pytest.mark.pb
def test_pb_server_and_collections_exist(pb_admin) -> None:
    """PB v0.40.6 ayakta ve 5 koleksiyon migration ile başarıyla yüklenmiş olmalı."""
    cols = pb_admin.collections.get_full_list()
    col_names = {c.name for c in cols}

    expected = {"transactions", "decisions", "shadow_portfolios", "macro_data", "price_history"}
    missing = expected - col_names
    assert not missing, f"Eksik koleksiyonlar: {missing}"


@pytest.mark.pb
def test_user_creation_and_auth(make_user) -> None:
    """Kullanıcı oluşturulup JWT token alınabilmeli."""
    user_id, token, user_client = make_user("trader1@test.local", "TraderPass123!")
    assert user_id
    assert token
    assert user_client.auth_store.is_valid
    assert user_client.auth_store.token == token


@pytest.mark.pb
def test_transaction_crud_and_user_isolation(make_user, api_client) -> None:
    """
    Kullanıcı izolasyonu FastAPI endpoint'leri üzerinden test edilir.
    """
    _user_a_id, token_a, _ = make_user("user_a@test.local", "Pass12345!")
    _user_b_id, token_b, _ = make_user("user_b@test.local", "Pass12345!")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A işlem oluşturur (FastAPI endpoint)
    tx_data = {
        "asset_symbol": "BTC/USDT",
        "tx_type": "BUY",
        "quantity": 1.5,
        "price": 60000.0,
        "fee": 10.0,
        "timestamp": "2024-01-15 00:00:00.000Z",
    }
    r = api_client.post("/api/transactions", headers=headers_a, json=tx_data)
    assert r.status_code == 201
    created_tx = r.json()
    tx_id = created_tx["id"]

    # User A kendi işlemlerini listeler -> bulur
    r = api_client.get("/api/transactions", headers=headers_a)
    assert r.status_code == 200
    txs_a = r.json()
    assert len(txs_a) == 1
    assert txs_a[0]["id"] == tx_id

    # User B listeler -> boş döner (izolasyon)
    r = api_client.get("/api/transactions", headers=headers_b)
    assert r.status_code == 200
    txs_b = r.json()
    assert len(txs_b) == 0

    # User B, User A'nın işlemine erişim denerse -> 404
    r = api_client.get(f"/api/transactions/{tx_id}", headers=headers_b)
    assert r.status_code == 404


@pytest.mark.pb
def test_decision_and_shadow_portfolio_cascade(make_user, api_client) -> None:
    """
    Karar ve gölge portföy ilişkisi:
    Karar silindiğinde bağlı gölge pozisyon cascade olarak silinmeli.
    """
    _user_id, token, _ = make_user("dec_user@test.local", "Pass12345!")
    headers = {"Authorization": f"Bearer {token}"}

    # Karar oluştur (FastAPI endpoint)
    r = api_client.post(
        "/api/decisions",
        headers=headers,
        json={
            "asset_symbol": "THYAO.IS",
            "action": "BUY",
            "sentiment": "STRATEGIC",
            "rationale": "Bilanço beklentisi",
        },
    )
    assert r.status_code == 201
    dec = r.json()
    dec_id = dec["id"]

    # Karara bağlı gölge pozisyon oluştur (FastAPI endpoint)
    r = api_client.post(
        "/api/counterfactual/shadow-positions",
        headers=headers,
        json={
            "decision_id": dec_id,
            "asset_symbol": "THYAO.IS",
            "shadow_type": "HELD_INSTEAD",
            "entry_price": 300.0,
            "quantity": 50.0,
            "entry_date": "2024-11-01",
        },
    )
    assert r.status_code == 201
    shadow = r.json()
    _ = shadow["id"]

    # Kararı sil (FastAPI endpoint - cascade silinir)
    r = api_client.delete(f"/api/decisions/{dec_id}", headers=headers)
    assert r.status_code == 200

    # Gölge pozisyonun da silindiğini doğrula
    r = api_client.get("/api/counterfactual/shadow-positions", headers=headers)
    assert r.status_code == 200
    shadows = r.json()
    assert len(shadows) == 0
