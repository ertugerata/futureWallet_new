"""
Monte Carlo & Stres Testi Kabul Doğrulamaları (Prompt 12).

Kapsam:
- Sabit mu/sigma ile 20k yolda GBM medyanı teorik değere %2 içinde; 40 kutu histogram.
- market_crash %50 şoku kalıcı: vade medyanı ≈ -%50.
- Verisi olmayan varlıklarda kovaryans tekildir → Cholesky epsilon fallback'i çökmemeli.
- Cholesky korelasyonlu simülasyon deterministik (aynı seed → aynı çıktı) ve p5<p50<p95.
- API limitleri: simulations>20000 ve days>756 → 422.
- days verilmezse 63/126/252 tek çağrıda.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from fastapi import status

from services import simulation_service as sim


def _fixed_returns(mean: float = 0.001, base: float = 0.02, n: int = 500) -> pd.Series:
    """Deterministik log-getiri serisi: mean tam, std ≈ base (ddof=1)."""
    sign = np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
    idx = pd.date_range("2020-01-01", periods=n, freq="D").date
    return pd.Series(mean + base * sign, index=idx)


@pytest.fixture()
def no_network(monkeypatch) -> None:
    monkeypatch.setattr(sim.AssetManager, "get_price", lambda self, symbol, asset_type: 100.0)
    monkeypatch.setattr(
        sim,
        "_fetch_all_asset_returns",
        lambda assets, days=504: {a["symbol"]: _fixed_returns() for a in assets},
    )


def test_gbm_median_within_2_percent_of_theory(no_network) -> None:
    res = sim.monte_carlo_simulation(
        user_id="u1",
        asset_list=[{"symbol": "BTC", "type": "crypto", "amount": 1.0}],
        days=126,
        n_simulations=20000,
        seed=42,
        use_ledger=False,
    )
    p50 = res["percentile_values"]["portfolio"]["p50"]
    # GBM medyanı: V0 * exp(mu * (days-1))  (125 log-adım, varyans düzeltmesi yok)
    theoretical = 100.0 * math.exp(0.001 * 125)
    assert abs(p50 / theoretical - 1.0) < 0.02, f"p50={p50}, teori={theoretical:.2f}"
    assert len(res["histogram"]["counts"]) == 40
    assert len(res["histogram"]["bins"]) == 41


def test_market_crash_shock_persists_to_maturity() -> None:
    res = sim.stress_test(
        portfolio_value=1000.0,
        shocks={"market_crash": 0.50},
        days=63,
        n_simulations=5000,
        seed=7,
    )
    mc = res["stressed_values"]["market_crash"]
    # Kalıcı etki yoksa vade medyanı ~0'a yakın kalırdı; çarpan vadeye kadar taşınmalı
    assert abs(mc["loss_pct"] + 0.50) < 0.05, f"loss_pct={mc['loss_pct']}"
    assert mc["p5"] < mc["p50"] < mc["p95"]
    assert res["worst_case_name"] == "market_crash"


def test_singular_covariance_does_not_crash(monkeypatch) -> None:
    """Tüm varlıkların verisi yok → cov sıfır matrisi; epsilon fallback çözülmeli."""
    monkeypatch.setattr(sim.AssetManager, "get_price", lambda self, symbol, asset_type: 50.0)
    monkeypatch.setattr(
        sim,
        "_fetch_all_asset_returns",
        lambda assets, days=504: {a["symbol"]: None for a in assets},
    )
    res = sim.monte_carlo_simulation(
        user_id="u1",
        asset_list=[{"symbol": "BTC", "type": "crypto", "amount": 1.0}],
        days=63,
        n_simulations=500,
        seed=1,
        use_ledger=False,
    )
    assert res["data_quality"] == "estimated"
    assert res["percentile_values"]["portfolio"]["p50"] > 0


def test_cholesky_multivariate_reproducible_and_ordered(monkeypatch) -> None:
    # İki varlık aynı seriyi döner → kovaryans tekil; korelasyon yolu Cholesky fallback'i dener
    monkeypatch.setattr(sim.AssetManager, "get_price", lambda self, symbol, asset_type: 100.0)
    monkeypatch.setattr(
        sim,
        "_fetch_all_asset_returns",
        lambda assets, days=504: {a["symbol"]: _fixed_returns() for a in assets},
    )
    assets = [
        {"symbol": "BTC", "type": "crypto", "amount": 1.0},
        {"symbol": "GC=F", "type": "commodity", "amount": 1.0},
    ]
    r1 = sim.monte_carlo_simulation(
        user_id="u1", asset_list=assets, days=63, n_simulations=2000, seed=3, use_ledger=False
    )
    r2 = sim.monte_carlo_simulation(
        user_id="u1", asset_list=assets, days=63, n_simulations=2000, seed=3, use_ledger=False
    )
    assert r1 == r2, "aynı seed deterministik olmalı"
    pv = r1["percentile_values"]["portfolio"]
    assert pv["p5"] < pv["p50"] < pv["p95"]
    assert len(r1["asset_final_values"]) == 2


@pytest.mark.pb
def test_monte_carlo_api_limits_422(api_client, auth_headers) -> None:
    resp = api_client.get(
        "/api/simulation/monte-carlo",
        params={"assets": "BTC", "simulations": 25000},
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    resp = api_client.get(
        "/api/simulation/monte-carlo",
        params={"assets": "BTC", "days": 900},
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.pb
def test_monte_carlo_api_three_horizons_single_call(
    api_client, test_db, auth_headers, monkeypatch
) -> None:
    monkeypatch.setattr(sim.AssetManager, "get_price", lambda self, symbol, asset_type: 100.0)
    monkeypatch.setattr(
        sim,
        "_fetch_all_asset_returns",
        lambda assets, days=504: {a["symbol"]: _fixed_returns() for a in assets},
    )
    resp = api_client.get(
        "/api/simulation/monte-carlo",
        params={"assets": "BTC,ETH", "simulations": 500},
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert set(body["horizons"].keys()) == {"63", "126", "252"}
    for h in body["horizons"].values():
        pv = h["percentile_values"]["portfolio"]
        assert pv["p5"] <= pv["p50"] <= pv["p95"]
