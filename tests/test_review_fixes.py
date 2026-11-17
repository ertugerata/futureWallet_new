"""Final review bulgularının regresyon testleri (fix pass).

#1 simülasyon hücre bütçesi (Memory-DoS), #2 chunked 64 KB bypass,
#3 günlük makro job'ı, #6 rate-limit pruning.
"""

from __future__ import annotations

import pytest
from fastapi import status


@pytest.mark.pb
def test_stress_api_rejects_over_cell_budget(api_client, auth_headers) -> None:
    """#1: n_simulations×days bütçeyi aşarsa 422 (eskiden 200k×756 ≈ 5 GB)."""
    resp = api_client.post(
        "/api/simulation/stress-test",
        json={"portfolio_value": 1000, "days": 756, "n_simulations": 200000},
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.pb
def test_monte_carlo_api_rejects_over_cell_budget(api_client, auth_headers) -> None:
    assets = ",".join(f"SYM{i}" for i in range(15))
    resp = api_client.get(
        "/api/simulation/monte-carlo",
        params={"assets": assets, "days": 756, "simulations": 20000},
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.pb
def test_monte_carlo_default_budget_still_works(
    api_client, test_db, auth_headers, monkeypatch
) -> None:
    from services import simulation_service as sim

    monkeypatch.setattr(sim.AssetManager, "get_price", lambda self, s, t: 100.0)
    monkeypatch.setattr(
        sim,
        "_fetch_all_asset_returns",
        lambda assets, days=504: {a["symbol"]: None for a in assets},
    )
    resp = api_client.get(
        "/api/simulation/monte-carlo",
        params={"assets": "BTC", "days": 63, "simulations": 500},
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.pb
def test_chunked_body_without_content_length_is_413(api_client, auth_headers) -> None:
    """#2: Content-Length olmayan (chunked) 64 KB+ gövde de 413 almalı."""

    def chunks():
        for _ in range(8):
            yield b"x" * 16384  # 128 KB

    resp = api_client.post(
        "/api/decisions",
        content=chunks(),
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    assert resp.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


@pytest.mark.pb
def test_scheduler_registers_daily_macro_job(pb_server) -> None:
    """#3: lifespan'da expire_decisions YANINDA günlük makro veri job'ı olmalı."""
    from fastapi.testclient import TestClient

    import api.app as app_module

    with TestClient(app_module.app):
        ids = {job.id for job in app_module._scheduler.get_jobs()}
    assert "expire_decisions" in ids
    assert "refresh_macro" in ids


def test_prune_rate_limits_drops_expired(pb_server) -> None:
    """#6: süresi dolmuş sayaç anahtarları budanır."""
    from api.app import _RETRO_RATE_LIMITS, _prune_rate_limits

    _RETRO_RATE_LIMITS.clear()
    _RETRO_RATE_LIMITS[("u1", "d1")] = {"count": 1, "reset_at": 1}
    _RETRO_RATE_LIMITS[("u1", "d2")] = {"count": 1, "reset_at": 9_999_999_999}
    _prune_rate_limits(now=1_000)
    assert ("u1", "d1") not in _RETRO_RATE_LIMITS
    assert ("u1", "d2") in _RETRO_RATE_LIMITS
    _RETRO_RATE_LIMITS.clear()


# ---------------------------------------------------------------------------
# Ertelenen review minörleri: shadow-create sahipliği + PB record ID doğrulaması
# ---------------------------------------------------------------------------


@pytest.mark.pb
def test_shadow_position_rejects_foreign_decision(api_client, make_user, pb_clean) -> None:
    """Başka kullanıcının kararıyla shadow-positions create → 400 (sahiplik kontrolü)."""
    _, token_b, _ = make_user("own_b@test.local", "Pass12345!")
    _, token_a, _ = make_user("own_a@test.local", "Pass12345!")
    dec = api_client.post(
        "/api/decisions",
        json={"asset_symbol": "ETH", "action": "SELL", "sentiment": "STRATEGIC"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert dec.status_code == status.HTTP_201_CREATED
    resp = api_client.post(
        "/api/counterfactual/shadow-positions",
        json={
            "decision_id": dec.json()["id"],
            "asset_symbol": "ETH",
            "shadow_type": "BOUGHT_INSTEAD",
            "entry_price": 3000.0,
            "quantity": 1.0,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.pb
def test_shadow_position_rejects_missing_decision(api_client, make_user, pb_clean) -> None:
    """Biçimli ama var olmayan karar ID'si → 400 (PB sessiz düşürme/500 yerine)."""
    _, token, _ = make_user("own_missing@test.local", "Pass12345!")
    resp = api_client.post(
        "/api/counterfactual/shadow-positions",
        json={
            "decision_id": "abc123def456ghi",
            "asset_symbol": "ETH",
            "shadow_type": "HELD_INSTEAD",
            "entry_price": 100.0,
            "quantity": 1.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.pb
def test_invalid_pb_ids_rejected_422(api_client, auth_headers) -> None:
    """PB record ID formatı girdide doğrulanır: path/query/body → 422."""
    bad = "NOT-VALID-ID"
    assert (
        api_client.get(f"/api/decisions/{bad}", headers=auth_headers).status_code
        == status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    assert (
        api_client.get(
            "/api/counterfactual",
            params={"decision_id": bad},
            headers=auth_headers,
        ).status_code
        == status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    assert (
        api_client.post(
            "/api/counterfactual/shadow-positions",
            json={
                "decision_id": bad,
                "asset_symbol": "ETH",
                "shadow_type": "HELD_INSTEAD",
            },
            headers=auth_headers,
        ).status_code
        == status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    # Olumlu kontrol: biçimli ama olmayan transaction ID doğrulamadan geçer → 404
    assert (
        api_client.delete("/api/transactions/zzz000111222333", headers=auth_headers).status_code
        == status.HTTP_404_NOT_FOUND
    )
