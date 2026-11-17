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
