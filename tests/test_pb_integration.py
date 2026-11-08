"""
PocketBase Entegrasyon Testleri (Prompt 2 & Prompt 3 Kabul Kriterleri).
=======================================================================
Gerçek PocketBase (v0.40.6) sunucusuna karşı çalışır.
"""

from __future__ import annotations

import pytest
from pocketbase.errors import ClientResponseError


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
def test_transaction_crud_and_user_isolation(make_user, pb_clean) -> None:
    """
    Kullanıcı izolasyonu:
    Kullanıcı A'nın oluşturduğu işlemi Kullanıcı B göremez veya değiştiremez.
    """
    user_a_id, _token_a, client_a = make_user("user_a@test.local", "Pass12345!")
    _user_b_id, _token_b, client_b = make_user("user_b@test.local", "Pass12345!")

    # User A işlem oluşturur
    tx_data = {
        "user": user_a_id,
        "asset_symbol": "BTC/USDT",
        "type": "BUY",
        "quantity": 1.5,
        "price": 60000.0,
        "fee": 10.0,
        "timestamp": "2026-11-01T10:00:00Z",
        "voided": False,
    }
    created_tx = client_a.collection("transactions").create(tx_data)
    assert created_tx.id
    assert created_tx.asset_symbol == "BTC/USDT"

    # User A kendi işlemlerini listeler -> bulur
    txs_a = client_a.collection("transactions").get_full_list()
    assert len(txs_a) == 1
    assert txs_a[0].id == created_tx.id

    # User B listeler -> boş döner (RLS izolasyonu)
    txs_b = client_b.collection("transactions").get_full_list()
    assert len(txs_b) == 0

    # User B, User A'nın ID'si ile get_one denerse -> 404 / ClientResponseError
    with pytest.raises(ClientResponseError):
        client_b.collection("transactions").get_one(created_tx.id)


@pytest.mark.pb
def test_decision_and_shadow_portfolio_cascade(make_user, pb_clean) -> None:
    """
    Karar ve gölge portföy ilişkisi:
    Karar silindiğinde bağlı gölge pozisyon cascade olarak silinmeli.
    """
    user_id, _token, client = make_user("dec_user@test.local", "Pass12345!")

    # Karar oluştur
    dec_record = client.collection("decisions").create(
        {
            "user": user_id,
            "asset_symbol": "THYAO.IS",
            "action": "BUY",
            "sentiment": "STRATEGIC",
            "rationale": "Bilanço beklentisi",
            "status": "OPEN",
        }
    )
    assert dec_record.id

    # Karara bağlı gölge pozisyon oluştur
    shadow_record = client.collection("shadow_portfolios").create(
        {
            "user": user_id,
            "decision": dec_record.id,
            "asset_symbol": "THYAO.IS",
            "shadow_type": "HELD_INSTEAD",
            "entry_price": 300.0,
            "quantity": 50.0,
            "entry_date": "2026-11-01T00:00:00Z",
        }
    )
    assert shadow_record.id

    # Kararı sil
    client.collection("decisions").delete(dec_record.id)

    # Gölge pozisyonun da silindiğini doğrula (cascadeDelete)
    shadows = client.collection("shadow_portfolios").get_full_list()
    assert len(shadows) == 0
