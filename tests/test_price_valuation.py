"""
FutureWallet - Portföy Değerleme & Price Service Testleri (Prompt 9).
======================================================================
"""

from __future__ import annotations

from datetime import date, timedelta
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
            "asset_type": "crypto",
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
            "asset_type": "stock_tr",
            "date": f"{friday.isoformat()} 00:00:00.000Z",
            "price": 320.0,
        }
    )

    # Pazar günü sorgulandığında cuma gününün fiyatı dönmeli
    price = get_price_on("MOCK_STOCK", "stock_tr", sunday, lookback_days=3)
    assert price == 320.0
