"""
FutureWallet - Portföy Değerleme & Price Service Testleri (Prompt 9).
======================================================================
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from fastapi import status

from services.price_service import get_price_on


def test_value_series_point_limit_422(api_client, make_user) -> None:
    """400'den fazla nokta içeren value-series isteği 422 dönmeli."""
    _, token, _ = make_user("vs_user@test.local", "Pass12345!")
    start = date(2023, 1, 1)
    end = date(2025, 1, 1)  # ~730 gün

    resp = api_client.get(
        "/api/portfolio/value-series",
        params={
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "step": "daily",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT or resp.status_code == 422


def test_price_service_cache_hit(pb_admin) -> None:
    """PB cache'de kayıt varsa dış servise gitmeden cache'den okumalı."""
    test_date = date(2026, 11, 10)
    # Cache'e kayıt ekle
    pb_admin.collection("price_history").create(
        {
            "symbol": "MOCK_BTC",
            "date": f"{test_date.isoformat()} 00:00:00.000Z",
            "price": 85000.0,
        }
    )

    with patch("services.price_service._fetch_from_yfinance") as mock_yf:
        price = get_price_on("MOCK_BTC", "crypto", test_date)
        assert price == 85000.0
        mock_yf.assert_not_called()


def test_price_service_weekend_lookback(pb_admin) -> None:
    """Hafta sonu/tatil durumunda önceki günün fiyatı bulunmalı."""
    friday = date(2026, 11, 6)
    sunday = date(2026, 11, 8)

    # Cuma gününe fiyat ekle
    pb_admin.collection("price_history").create(
        {
            "symbol": "MOCK_STOCK",
            "date": f"{friday.isoformat()} 00:00:00.000Z",
            "price": 320.0,
        }
    )

    # Pazar günü sorgulandığında cuma gününün fiyatı dönmeli
    price = get_price_on("MOCK_STOCK", "stock_tr", sunday, lookback_days=3)
    assert price == 320.0


# ---------------------------------------------------------------------------
# Time-travel kabul senaryosu (hızlı kontrol 8): 5 BTC 30k → 60k = %100 PnL
# ---------------------------------------------------------------------------


@pytest.mark.pb
def test_time_travel_double_price_yields_100_pct_pnl(pb_clean, make_user) -> None:
    from datetime import date

    from services.ledger_service import add_transaction, time_travel_portfolio

    uid, _, _ = make_user("tt_accept@test.local")
    t0 = date(2026, 1, 5)
    t1 = date(2026, 6, 5)
    add_transaction(
        user_id=uid, asset_symbol="BTC", tx_type="BUY", quantity=5, price=1.0, timestamp=t0
    )

    def price_fn(sym, atype, on_date):
        return 30000.0 if on_date <= t0 else 60000.0

    r = time_travel_portfolio(user_id=uid, t_start=t0, t_target=t1, price_fn=price_fn)
    assert r["value_at_start"] == 5 * 30000.0
    assert r["value_at_target"] == 5 * 60000.0
    assert r["pnl"] == 150000.0
    assert r["pnl_pct"] == 100.0


# ---------------------------------------------------------------------------
# P9: Dinamik currency (varlık tabanı) — sabit "TRY" yerine USD/TRY seçimi
# ---------------------------------------------------------------------------


def test_base_currency_mapping() -> None:
    from services.asset_types import base_currency

    assert base_currency("THYAO.IS") == "TRY"
    assert base_currency("GARAN") == "TRY"
    assert base_currency("BTC/USDT") == "USD"
    assert base_currency("GC=F") == "USD"
    assert base_currency("TRY") == "TRY"
    assert base_currency("USDT") == "USD"


def test_infer_portfolio_currency_majority() -> None:
    from services.asset_types import infer_portfolio_currency

    assert infer_portfolio_currency([]) == "TRY"
    assert infer_portfolio_currency(["BTC", "ETH"]) == "USD"
    assert infer_portfolio_currency(["THYAO.IS", "GARAN"]) == "TRY"
    assert infer_portfolio_currency(["BTC", "THYAO.IS"]) == "TRY"
    assert infer_portfolio_currency(["BTC", "ETH", "THYAO.IS"]) == "USD"


@pytest.mark.pb
def test_value_series_currency_usd_for_crypto_portfolio(api_client, pb_clean, make_user) -> None:
    """Sadece BTC tutan portföy → currency USD (sabit TRY olmamalı)."""
    from datetime import timedelta

    _, token, _ = make_user("vs_usd@test.local")
    headers = {"Authorization": f"Bearer {token}"}
    r = api_client.post(
        "/api/transactions",
        json={"asset_symbol": "BTC", "tx_type": "BUY", "quantity": 1.0, "price": 50000.0},
        headers=headers,
    )
    assert r.status_code == status.HTTP_201_CREATED

    end = date.today()
    start = end - timedelta(days=2)
    with patch("services.multi_asset_manager.AssetManager.get_price", return_value=None):
        resp = api_client.get(
            "/api/portfolio/value-series",
            params={"start_date": start.isoformat(), "end_date": end.isoformat(), "step": "daily"},
            headers=headers,
        )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["currency"] == "USD"


@pytest.mark.pb
def test_value_series_currency_try_for_bist_portfolio(api_client, pb_clean, make_user) -> None:
    """Sadece BIST tutan portföy → currency TRY."""
    from datetime import timedelta

    _, token, _ = make_user("vs_try@test.local")
    headers = {"Authorization": f"Bearer {token}"}
    r = api_client.post(
        "/api/transactions",
        json={"asset_symbol": "THYAO.IS", "tx_type": "BUY", "quantity": 100.0, "price": 250.0},
        headers=headers,
    )
    assert r.status_code == status.HTTP_201_CREATED
    end = date.today()
    start = end - timedelta(days=1)
    with patch("services.multi_asset_manager.AssetManager.get_price", return_value=None):
        resp = api_client.get(
            "/api/portfolio/value-series",
            params={"start_date": start.isoformat(), "end_date": end.isoformat()},
            headers=headers,
        )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["currency"] == "TRY"


@pytest.mark.pb
def test_value_series_cash_bucket_does_not_force_usd(api_client, pb_clean, make_user) -> None:
    """Sadeca nakit (CASH kovası) → sembol sinyali yok → currency TRY."""
    from datetime import timedelta

    _, token, _ = make_user("vs_cash@test.local")
    headers = {"Authorization": f"Bearer {token}"}
    r = api_client.post(
        "/api/transactions",
        json={"asset_symbol": "BTC", "tx_type": "CASH_IN", "quantity": 5000.0, "price": 1.0},
        headers=headers,
    )
    assert r.status_code == status.HTTP_201_CREATED
    end = date.today()
    start = end - timedelta(days=1)
    resp = api_client.get(
        "/api/portfolio/value-series",
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["currency"] == "TRY"


# ---------------------------------------------------------------------------
# P5-2 Golden Test: get_portfolio_snapshots == get_portfolio_snapshot per date
# ---------------------------------------------------------------------------


@pytest.mark.pb
def test_value_series_parity_with_single_snapshot(pb_clean, make_user) -> None:
    """
    Golden test: Rastgele sabit seed'li 40 işlem (BUY/SELL/DIVIDEND/CASH_IN, 60 gün)
    → her günlük tarih için get_portfolio_snapshots(...)[d] ile
    get_portfolio_snapshot(d) BİREBİR eşit olmalı.
    Mock price_fn ile deterministik fiyatlar kullanılır.
    """
    import random
    from datetime import date, timedelta

    from services.ledger_service import get_portfolio_snapshot, get_portfolio_snapshots
    from services.pb import get_client

    user_id, _, _ = make_user("golden_test@futurewallet.test")
    client = get_client()

    # Deterministic random operations
    random.seed(42)
    base_date = date(2024, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(60)]

    symbols = ["BTC", "ETH", "THYAO.IS", "AKBNK.IS", "XU100"]
    tx_types = ["BUY", "SELL", "DIVIDEND", "CASH_IN"]

    # Create transactions
    for i in range(40):
        tx_date = random.choice(dates)
        sym = random.choice(symbols)
        tx_type = random.choice(tx_types)
        qty = round(random.uniform(0.1, 10.0), 4)
        price = round(random.uniform(10, 50000), 2)
        fee = round(random.uniform(0, 5), 2)

        if tx_type in ("DIVIDEND", "CASH_IN"):
            sym = "CASH"
            price = 1.0
            fee = 0.0

        client.collection("transactions").create(
            {
                "user": user_id,
                "asset_symbol": sym,
                "type": tx_type,
                "quantity": qty,
                "price": price,
                "fee": fee,
                "timestamp": (tx_date + timedelta(days=1)).isoformat() + " 00:00:00.000Z",
                "voided": False,
            }
        )

    # Mock price function: deterministic prices based on symbol and date
    price_map = {
        "BTC": 50000.0,
        "ETH": 3000.0,
        "THYAO.IS": 250.0,
        "AKBNK.IS": 50.0,
        "XU100": 5000.0,
        "CASH": 1.0,
    }

    def mock_price_fn(sym: str, atype: str, dt: date | None = None) -> float:
        return price_map.get(sym.upper(), 100.0)

    # Adapter for single snapshot (2-arg price_fn)
    def mock_price_fn_2arg(sym: str, atype: str) -> float:
        return mock_price_fn(sym, atype, None)

    # Test all dates
    for d in dates:
        bulk = get_portfolio_snapshots(user_id, [d], custom_price_fn=mock_price_fn)
        single = get_portfolio_snapshot(user_id, d, price_fn=mock_price_fn_2arg)

        # Compare key fields (floating point approx)
        assert bulk[d]["total_value"] == pytest.approx(single["total_value"]), (
            f"total_value mismatch at {d}"
        )
        assert bulk[d]["total_cost"] == pytest.approx(single["total_cost"]), (
            f"total_cost mismatch at {d}"
        )
        assert bulk[d]["cash_received"] == pytest.approx(single["cash_received"]), (
            f"cash_received mismatch at {d}"
        )
        assert bulk[d]["pnl"] == pytest.approx(single["pnl"]), f"pnl mismatch at {d}"
        assert bulk[d]["pnl_pct"] == pytest.approx(single["pnl_pct"]), f"pnl_pct mismatch at {d}"
        assert len(bulk[d]["holdings"]) == len(single["holdings"]), (
            f"holdings count mismatch at {d}"
        )

        # Compare each holding
        bulk_holdings = {h["asset_symbol"]: h for h in bulk[d]["holdings"]}
        single_holdings = {h["asset_symbol"]: h for h in single["holdings"]}
        assert set(bulk_holdings.keys()) == set(single_holdings.keys()), (
            f"holding symbols mismatch at {d}"
        )
        for sym, bh in bulk_holdings.items():
            sh = single_holdings[sym]
            assert bh["quantity"] == pytest.approx(sh["quantity"]), (
                f"quantity mismatch for {sym} at {d}"
            )
            assert bh["current_value"] == pytest.approx(sh["current_value"]), (
                f"current_value mismatch for {sym} at {d}"
            )
            assert bh["total_cost"] == pytest.approx(sh["total_cost"]), (
                f"total_cost mismatch for {sym} at {d}"
            )
            assert bh["unrealized_pnl"] == pytest.approx(sh["unrealized_pnl"]), (
                f"unrealized_pnl mismatch for {sym} at {d}"
            )
            assert bh["unrealized_pnl_pct"] == pytest.approx(sh["unrealized_pnl_pct"]), (
                f"unrealized_pnl_pct mismatch for {sym} at {d}"
            )
