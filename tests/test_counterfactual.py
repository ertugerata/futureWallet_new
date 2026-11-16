"""
FutureWallet - Gölge Portföy (Counterfactual Engine) Testleri (Prompt 10).
==========================================================================
"""

from __future__ import annotations

import pytest
from fastapi import status

from services.counterfactual_service import (
    compare_real_vs_shadow,
)


def test_shadow_position_opportunity_cost():
    """
    10 BTC 50,000'den satıldı (500,000 nakit).
    BTC 80,000 olunca gölge = 800,000 -> fırsat maliyeti = 800k - 500k = +300k.
    BTC 40,000 olunca gölge = 400,000 -> fırsat maliyeti = 400k - 500k = -100k.
    """
    as_of = pytest.importorskip("datetime").date.today()
    real_holdings = [{"asset_symbol": "USDT", "quantity": 500000.0}]

    shadow_positions = [
        {
            "asset_symbol": "BTC",
            "quantity": 10.0,
            "entry_price": 50000.0,
            "shadow_type": "HELD_INSTEAD",
        }
    ]

    # Senaryo 1: Fiyat 80k
    comp_up = compare_real_vs_shadow(
        as_of=as_of,
        real_holdings=real_holdings,
        shadow_positions=shadow_positions,
        price_fn=lambda s: 80000.0 if s == "BTC" else 1.0,
    )
    assert comp_up["real_portfolio_value"] == 500000.0
    assert comp_up["shadow_portfolio_value"] == 800000.0
    assert comp_up["opportunity_cost"] == 300000.0

    # Senaryo 2: Fiyat 40k
    comp_down = compare_real_vs_shadow(
        as_of=as_of,
        real_holdings=real_holdings,
        shadow_positions=shadow_positions,
        price_fn=lambda s: 40000.0 if s == "BTC" else 1.0,
    )
    assert comp_down["real_portfolio_value"] == 500000.0
    assert comp_down["shadow_portfolio_value"] == 400000.0
    assert comp_down["opportunity_cost"] == -100000.0


def test_shadow_position_user_isolation(api_client, make_user, pb_clean):
    """Kullanıcı B, Kullanıcı A'nın gölge pozisyonlarını göremez veya silemez."""
    _user_a_id, token_a, _ = make_user("user_a_cf@test.local", "Pass12345!")
    _user_b_id, token_b, _ = make_user("user_b_cf@test.local", "Pass12345!")

    # User A karar ve gölge pozisyon oluşturur
    dec_resp = api_client.post(
        "/api/decisions",
        json={
            "asset_symbol": "ETH",
            "action": "SELL",
            "rationale": "Kar satışı",
            "sentiment": "STRATEGIC",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    dec_id = dec_resp.json()["id"]

    sp_resp = api_client.post(
        "/api/counterfactual/shadow-positions",
        json={
            "decision_id": dec_id,
            "asset_symbol": "ETH",
            "shadow_type": "HELD_INSTEAD",
            "entry_price": 3000.0,
            "quantity": 5.0,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert sp_resp.status_code == status.HTTP_201_CREATED
    sp_id = sp_resp.json()["id"]

    # User B liste çağrısı yapınca User A'nın gölge pozisyonunu göremez
    list_b = api_client.get(
        "/api/counterfactual/shadow-positions",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert list_b.status_code == status.HTTP_200_OK
    assert len(list_b.json()) == 0

    # User B silmeye çalışınca 404 alır
    del_b = api_client.delete(
        f"/api/counterfactual/shadow-positions/{sp_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert del_b.status_code == status.HTTP_404_NOT_FOUND
