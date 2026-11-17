"""
Benchmark Servisi Birim Testleri (Prompt 11 kabul kriterleri).

- gold_try_gram formülü: (GC=F_USD / 31.1035) * USDTRY
- _upsert_to_pb: aynı tarih iki kez yazıldırılırsa tek kayıt kalır (benzersiz indeks)
- alpha = portföy getirisi − benchmark getirisi
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from services.benchmark_service import (
    GRAMS_PER_OUNCE,
    _upsert_to_pb,
    compare_to_benchmark,
    compute_gold_try_gram,
)
from services.pb import get_admin_client, list_all


def test_gold_try_gram_formula() -> None:
    got = compute_gold_try_gram(2650.0, 34.5)
    expected = (2650.0 / 31.1035) * 34.5
    assert abs(got - expected) < 1e-9
    assert GRAMS_PER_OUNCE == 31.1035


def test_gold_try_gram_none_inputs() -> None:
    assert compute_gold_try_gram(None, 34.5) is None
    assert compute_gold_try_gram(2650.0, None) is None


@pytest.mark.pb
def test_upsert_same_date_keeps_single_record(pb_server, pb_clean) -> None:
    """Aynı tarih için iki upsert tek kayıt bırakır (benzersiz date indeksi)."""
    client = get_admin_client()
    macro = client.collection("macro_data")

    idx = pd.to_datetime([date(2026, 1, 15)])
    df_v1 = pd.DataFrame({"gold_usd": [2000.0]}, index=idx)
    df_v2 = pd.DataFrame({"gold_usd": [2100.0]}, index=idx)

    assert _upsert_to_pb(macro, df_v1, "gold_usd", source="test") == 1
    assert _upsert_to_pb(macro, df_v2, "gold_usd", source="test") == 1

    records = list_all(macro)
    assert len(records) == 1, "aynı tarih ikinci kez upsert edilmemeli, güncellenmeli"
    assert float(records[0].gold_usd) == 2100.0


@pytest.mark.pb
def test_upsert_persists_source_and_is_estimate(pb_server, pb_clean) -> None:
    """source/is_estimate PB şemasında tutulmalı; şema dışı alan PB'de SESSİZ düşer
    (gold_try vakası — e2e denetiminde price_history.asset_type ile aynı sınıf)."""
    client = get_admin_client()
    macro = client.collection("macro_data")

    idx = pd.to_datetime([date(2026, 2, 10)])
    df = pd.DataFrame({"us_cpi": [321.5]}, index=idx)
    assert _upsert_to_pb(macro, df, "us_cpi", source="FRED", is_estimate=True) == 1

    rec = list_all(macro)[0]
    assert rec.source == "FRED"
    assert rec.is_estimate is True


@pytest.mark.pb
def test_compare_to_benchmark_alpha(pb_server, pb_clean) -> None:
    """alpha = portföy − benchmark; deterministik macro_data satırlarıyla."""
    client = get_admin_client()
    macro = client.collection("macro_data")
    d_start, d_end = date(2026, 1, 5), date(2026, 4, 6)
    macro.create(
        {
            "date": f"{d_start.isoformat()} 00:00:00.000Z",
            "gold_usd": 1000.0,
            "sp500": 100.0,
            "gold_try_gram": 500.0,
        }
    )
    macro.create(
        {
            "date": f"{d_end.isoformat()} 00:00:00.000Z",
            "gold_usd": 1100.0,
            "sp500": 105.0,
            "gold_try_gram": 550.0,
        }
    )

    # Portföy %15; altın %10; S&P %5; gram altın %10
    out = compare_to_benchmark(1000.0, 1150.0, d_start, d_end)
    assert out["portfolio_return_pct"] == 0.15
    assert out["gold_usd"]["return_pct"] == pytest.approx(0.1)
    assert out["sp500"]["return_pct"] == pytest.approx(0.05)
    assert out["alpha"]["gold_usd"] == pytest.approx(0.05)
    assert out["alpha"]["sp500"] == pytest.approx(0.10)
    assert out["alpha"]["gold_try_gram"] == pytest.approx(0.05)
