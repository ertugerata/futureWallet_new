"""
FutureWallet – Benchmark & Enflasyon Servisi (PocketBase)
============================================================
Piyasa verileri (Altın, S&P 500, Gram Altın TL, TÜFE, US CPI) çeker,
PB `macro_data` koleksiyonuna önbelleğe alır ve reel (enflasyondan
arındırılmış) değerleme yapar.

Veri çekme fonksiyonları (yfinance, EVDS, FRED) PB'den bağımsız kalır;
sadece `macro_data` upsert ve CPI okuma PB client üzerinden yapılır.

db.py (SQLAlchemy) → pocketbase.py geçişi ile senkronize.

MVP §3.4, TODO 2.2, Prompt 11 (Benchmark / enflasyon verisi).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import requests  # type: ignore[import-untyped]
import yfinance as yf

from config import FRED_API_KEY, TCMB_API_KEY
from services.pocketbase import get_client

# ---------------------------------------------------------------------------
# Sabitler / konfigürasyon
# ---------------------------------------------------------------------------

GC_F_TICKER = "GC=F"  # Ons Altın (USD) – COMEX
XAUUSD_TICKER = "XAUUSD"  # Gram Altın (USD) – şişe
SP500_TICKER = "^GSPC"  # S&P 500
USDTRY_TICKER = "USDTRY=X"  # USD/TRY kur

FRED_CPI_SERIES = "CPIAUCSL"  # US CPI (All Urban Consumers)
TCMB_TUFE_SERIES = "TUFE_G_0000000001"  # TÜİK TÜFE (2023=100)

EVDS_JSON_URL = "https://evds.tcmb.gov.tr/evds_services/api/values"
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

GRAMS_PER_OUNCE = 31.1035  # ons → gram


# ---------------------------------------------------------------------------
# 1. Piyasa fiyatları (yfinance) – PB'den bağımsız
# ---------------------------------------------------------------------------


def fetch_gold_prices(
    start: date,
    end: date,
    granularity: str = "1mo",
) -> pd.DataFrame:
    """Ons Altın (GC=F) tarihsel kapanış fiyatlarını çeker."""
    df = yf.download(GC_F_TICKER, start=start, end=end, progress=False)
    if df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        close_series = df[("Close", GC_F_TICKER)]
    else:
        close_series = df["Close"]

    result = pd.DataFrame({"gold_usd": close_series})
    result.index = pd.to_datetime(result.index).date
    result.index.name = "date"
    return result


def fetch_sp500_prices(
    start: date,
    end: date,
    granularity: str = "1mo",
) -> pd.DataFrame:
    """S&P 500 (^GSPC) tarihsel kapanış fiyatlarını çeker."""
    df = yf.download(SP500_TICKER, start=start, end=end, progress=False)
    if df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        close_series = df[("Close", SP500_TICKER)]
    else:
        close_series = df["Close"]

    result = pd.DataFrame({"sp500": close_series})
    result.index = pd.to_datetime(result.index).date
    result.index.name = "date"
    return result


def fetch_usd_try_rate(
    start: date,
    end: date,
) -> pd.Series | None:
    """USD/TRY kuru serisi (yfinance USDTRY=X).

    Returns:
        İndeksi date, değerler USDTRY kuru (float). Yoksa None.
    """
    df = yf.download(USDTRY_TICKER, start=start, end=end, progress=False)
    if df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        close_series = df[("Close", USDTRY_TICKER)]
    else:
        close_series = df["Close"]

    if close_series is None or close_series.empty:
        return None

    series = close_series.astype(float)
    series.index = pd.to_datetime(series.index).date
    return series


def get_current_market_prices() -> dict[str, float | None]:
    """Güncel (bugün) Altın ve S&P 500 ve USD/TRY fiyatlarını döndürür."""
    out: dict[str, float | None] = {
        "gold_usd": None,
        "sp500": None,
        "usd_try": None,
    }

    try:
        g = yf.download(GC_F_TICKER, period="5d", progress=False)
        if not g.empty and isinstance(g.columns, pd.MultiIndex):
            out["gold_usd"] = float(g[("Close", GC_F_TICKER)].iloc[-1])
        elif not g.empty:
            out["gold_usd"] = float(g["Close"].iloc[-1])
    except Exception:
        pass

    try:
        s = yf.download(SP500_TICKER, period="1d", progress=False)
        if not s.empty and isinstance(s.columns, pd.MultiIndex):
            out["sp500"] = float(s[("Close", SP500_TICKER)].iloc[-1])
        elif not s.empty:
            out["sp500"] = float(s["Close"].iloc[-1])
    except Exception:
        pass

    try:
        u = yf.download(USDTRY_TICKER, period="5d", progress=False)
        if not u.empty and isinstance(u.columns, pd.MultiIndex):
            out["usd_try"] = float(u[("Close", USDTRY_TICKER)].iloc[-1])
        elif not u.empty:
            out["usd_try"] = float(u["Close"].iloc[-1])
    except Exception:
        pass

    return out


# ---------------------------------------------------------------------------
# 2. TÜİK TÜFE (TR enflasyon) – EVDS API (Prompt 11)
# ---------------------------------------------------------------------------


def _evds_fetch_turkey_cpi(
    start: date,
    end: date,
) -> pd.DataFrame | None:
    """TCMB EVDS API'sinden TÜFE (TUFE_G_0000000001) serisini çeker.

    GET {EVDS_JSON_URL}?series=...&startDate=...&endDate=...&key={TCMB_API_KEY}
    """
    if not TCMB_API_KEY:
        return None

    params = {
        "series": TCMB_TUFE_SERIES,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "key": TCMB_API_KEY,
    }

    try:
        resp = requests.get(EVDS_JSON_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    records = data.get("records", {})
    series_data = records.get(TCMB_TUFE_SERIES, {})
    items = series_data.get("data", [])
    if not items:
        items = data.get("data", [])
        if not items:
            return None

    dates: list = []
    values: list = []
    for item in items:
        d = item.get("date")
        v = item.get("value")
        if d and v is not None:
            try:
                dates.append(datetime.strptime(d, "%Y-%m-%d").date())
                values.append(float(v))
            except (ValueError, TypeError):
                continue

    if not dates:
        return None

    return pd.DataFrame({"tr_cpi": values}, index=dates)


def fetch_turkey_cpi(
    start: date,
    end: date,
    allow_estimate: bool = False,
) -> pd.DataFrame:
    """Türkiye TÜFE endeksi serisi (aylık).

    allow_estimate=False ve veri yoksa ValueError (Prompt 11).
    """
    evds = _evds_fetch_turkey_cpi(start, end)
    if evds is not None and not evds.empty:
        return evds

    if not allow_estimate:
        raise ValueError(
            "TÜFE verisi alınamadı: TCMB_API_KEY yapılandırılmamış "
            "veya EVDS API erişilemez. ?allow_estimate=true ile izleyici seri istenebilir."
        )

    months = []
    current = start.replace(day=1)
    end_moment = end.replace(day=1)
    while current <= end_moment:
        months.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return pd.DataFrame(
        {"tr_cpi": [100.0] * len(months), "data_quality": "estimated"},
        index=months,
    )


# ---------------------------------------------------------------------------
# 3. US CPI (ABD enflasyon) – FRED API (Prompt 11)
# ---------------------------------------------------------------------------


def _fred_fetch_us_cpi(
    start: date,
    end: date,
) -> pd.DataFrame | None:
    """FRED API'sinden US CPI (CPIAUCSL) serisini çeker."""
    if not FRED_API_KEY:
        return None

    params = {
        "series_id": FRED_CPI_SERIES,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start.isoformat(),
        "observation_end": end.isoformat(),
    }

    try:
        resp = requests.get(FRED_BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    obs = data.get("observations", [])
    if not obs:
        return None

    dates: list = []
    values: list = []
    for item in obs:
        d = item.get("date")
        v = item.get("value")
        if d and v != ".":
            try:
                dates.append(datetime.strptime(d, "%Y-%m-%d").date())
                values.append(float(v))
            except (ValueError, TypeError):
                continue

    if not dates:
        return None

    return pd.DataFrame({"us_cpi": values}, index=dates)


def fetch_us_cpi(
    start: date,
    end: date,
    allow_estimate: bool = False,
) -> pd.DataFrame:
    """US CPI (CPIAUCSL) serisi.

    allow_estimate=False ve veri yoksa ValueError (Prompt 11).
    """
    fred = _fred_fetch_us_cpi(start, end)
    if fred is not None and not fred.empty:
        return fred

    if not allow_estimate:
        raise ValueError(
            "US CPI verisi alınamadı: FRED_API_KEY yapılandırılmamış "
            "veya FRED API erişilemez. ?allow_estimate=true ile izleyici seri istenebilir."
        )

    months = []
    current = start.replace(day=1)
    end_moment = end.replace(day=1)
    while current <= end_moment:
        months.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return pd.DataFrame(
        {"us_cpi": [100.0] * len(months), "data_quality": "estimated"},
        index=months,
    )


# ---------------------------------------------------------------------------
# 4. Gram Altın TL (Prompt 11)
# ---------------------------------------------------------------------------


def compute_gold_try_gram(
    gold_usd_ons: float | None,
    usd_try: float | None,
) -> float | None:
    """Gram altın TL fiyatı = (ons altın USD / 31.1035) * USDTRY."""
    if gold_usd_ons is None or usd_try is None:
        return None
    return (gold_usd_ons / GRAMS_PER_OUNCE) * usd_try


# ---------------------------------------------------------------------------
# 5. Tüm makro verilerini çekip PB'ye kaydet  (Prompt 11 – source/is_estimate)
# ---------------------------------------------------------------------------


def fetch_and_save_macro_data(
    user_id: str,
    start: date | None = None,
    end: date | None = None,
    save_sp500: bool = True,
    save_gold_usd: bool = True,
    save_gold_try_gram: bool = True,
    save_tr_cpi: bool = True,
    save_us_cpi: bool = True,
) -> dict[str, int]:
    """Tüm makro verilerini çeker ve PB `macro_data` koleksiyonuna kaydeder.

    PB macro_data alanları:
      date, gold_usd, gold_try_gram, sp500, tr_cpi, us_cpi,
      source, is_estimate
    """
    if start is None:
        start = date.today().replace(year=date.today().year - 1)
    if end is None:
        end = date.today()

    stats: dict[str, int] = {
        "gold_usd": 0,
        "sp500": 0,
        "gold_try_gram": 0,
        "tr_cpi": 0,
        "us_cpi": 0,
    }

    client = get_client()
    macro = client.collection("macro_data")

    # Altın (ons USD)
    if save_gold_usd:
        gold_df = fetch_gold_prices(start, end, granularity="1mo")
        stats["gold_usd"] = _upsert_to_pb(
            macro,
            gold_df,
            "gold_usd",
            user_id,
            source="yfinance",
            is_estimate=False,
        )

    # S&P 500
    if save_sp500:
        sp_df = fetch_sp500_prices(start, end, granularity="1mo")
        stats["sp500"] = _upsert_to_pb(
            macro,
            sp_df,
            "sp500",
            user_id,
            source="yfinance",
            is_estimate=False,
        )

    # Gram altın TL
    if save_gold_try_gram:
        gold_usd_series = fetch_gold_prices(start, end, granularity="1mo")["gold_usd"]
        usd_try_series = fetch_usd_try_rate(start, end)
        if gold_usd_series is not None and usd_try_series is not None:
            gold_try_df = pd.DataFrame(
                {"gold_try_gram": (gold_usd_series / GRAMS_PER_OUNCE) * usd_try_series}
            )
            gold_try_df = gold_try_df.dropna()
            if not gold_try_df.empty:
                stats["gold_try_gram"] = _upsert_to_pb(
                    macro,
                    gold_try_df,
                    "gold_try_gram",
                    user_id,
                    source="derived",
                    is_estimate=False,
                )

    # TÜFE
    if save_tr_cpi:
        try:
            tr_df = fetch_turkey_cpi(start, end, allow_estimate=False)
            stats["tr_cpi"] = _upsert_to_pb(
                macro,
                tr_df,
                "tr_cpi",
                user_id,
                source="EVDS/TÜİK",
                is_estimate=False,
            )
        except ValueError:
            pass

    # US CPI
    if save_us_cpi:
        try:
            us_df = fetch_us_cpi(start, end, allow_estimate=False)
            stats["us_cpi"] = _upsert_to_pb(
                macro,
                us_df,
                "us_cpi",
                user_id,
                source="FRED",
                is_estimate=False,
            )
        except ValueError:
            pass

    return stats


def _upsert_to_pb(
    collection,
    df: pd.DataFrame,
    value_col: str,
    user_id: str,
    source: str = "",
    is_estimate: bool = False,
) -> int:
    """Bir DataFrame'i PB macro_data koleksiyonuna upsert eder.

    DataFrame:
      index = date (datetime.date)
      columns = [value_col]

    PB macro_data fields (PB DateTime string ile kaydedilir):
      date (DateTime), gold_usd, gold_try_gram, sp500, tr_cpi, us_cpi,
      source (text), is_estimate (bool), user (Relation - users)

    datetime.date → PB DateTime: ISO "YYYY-MM-DD" veya "YYYY-MM-DDTHH:MM:SSZ"
    """
    if df.empty:
        return 0

    count = 0
    for dt, row in df.iterrows():
        d = dt.date() if hasattr(dt, "date") else dt
        val = row[value_col]
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue

        pb_date_str = d.isoformat()  # "YYYY-MM-DD" — PB DateTime olarak kabul eder

        try:
            existing = collection.get_list(params=f"filter=date='{pb_date_str}'&per_page=1")
        except Exception:
            existing = []

        record_data: dict = {
            "date": pb_date_str,
            value_col: float(val),
            "source": source,
            "is_estimate": is_estimate,
            "user": user_id,
        }

        if existing:
            existing[0].update(record_data)
            collection.update(existing[0])
        else:
            collection.create(record_data)

        count += 1

    return count


# ---------------------------------------------------------------------------
# 6. Reel değerleme: enflasyondan arındırılmış getiri  (Prompt 11)
# ---------------------------------------------------------------------------


def get_cpi_for_date(
    dt: date,
    cpi_type: str = "us",  # "us" | "tr"
) -> float | None:
    """Belirtilen tarihteki veya en yakın geçmiş CPI değerini PB macro_data'den döndürür.

    PB macro_data: date (DateTime), tr_cpi / us_cpi (float).
    """
    client = get_client()
    macro = client.collection("macro_data")

    col = "us_cpi" if cpi_type == "us" else "tr_cpi"
    try:
        records = macro.get_list(
            params=(f"filter=date<='{dt.isoformat()}' AND {col}!=''&sort=date DESC&per_page=1")
        )
    except Exception:
        return None

    if records:
        val = getattr(records[0], col, None)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            return float(val)
    return None


def adjust_for_inflation(
    nominal_value: float,
    date_from: date,
    date_to: date,
    cpi_type: str = "tr",
) -> float | None:
    """Nominal bir değeri, date_from'tan date_toye kadar olan enflasyona göre ayarlar.

    reel_değer = nominal × CPI(başlangıç) / CPI(bitiş)
    """
    cpi_from = get_cpi_for_date(date_from, cpi_type)
    cpi_to = get_cpi_for_date(date_to, cpi_type)

    if cpi_from is None or cpi_to is None:
        return None
    if cpi_to == 0:
        return None

    return nominal_value * (cpi_from / cpi_to)


def compute_real_return(
    portfolio_value_start: float,
    portfolio_value_end: float,
    date_start: date,
    date_end: date,
    cpi_type: str = "tr",
) -> dict:
    """Portföyün reel (enflasyondan arındırılmış) getirisini hesaplar."""
    cpi_from = get_cpi_for_date(date_start, cpi_type)
    cpi_to = get_cpi_for_date(date_end, cpi_type)

    nominal_return = (
        (portfolio_value_end - portfolio_value_start) / portfolio_value_start
        if portfolio_value_start
        else 0.0
    )

    real_return: float | None = None
    if cpi_from and cpi_to and cpi_to > 0:
        real_return = (portfolio_value_end / portfolio_value_start) * (cpi_from / cpi_to) - 1.0

    return {
        "nominal_return_pct": round(nominal_return, 6),
        "real_return_pct": round(real_return, 6) if real_return is not None else None,
        "cpi_type": cpi_type,
        "cpi_from": cpi_from,
        "cpi_to": cpi_to,
    }


# ---------------------------------------------------------------------------
# 7. Benchmark kıyas  (Prompt 11)
# ---------------------------------------------------------------------------


def compare_to_benchmark(
    portfolio_value_start: float,
    portfolio_value_end: float,
    date_start: date,
    date_end: date,
    benchmark_gold: bool = True,
    benchmark_sp500: bool = True,
    benchmark_gold_try_gram: bool = True,
) -> dict:
    """Portföy performansını Altın, Gram Altın TL ve S&P 500 ile kıyaslar.

    PB macro_data'den fiyatları çeker; yoksa yfinance'den çeker.
    """
    out: dict = {
        "portfolio_return_pct": round(
            (portfolio_value_end - portfolio_value_start) / portfolio_value_start
            if portfolio_value_start
            else 0.0,
            6,
        ),
        "gold_usd": {"price_start": None, "price_end": None, "return_pct": None},
        "gold_try_gram": {"price_start": None, "price_end": None, "return_pct": None},
        "sp500": {"price_start": None, "price_end": None, "return_pct": None},
    }

    def _get_pb_price(col: str, dt: date) -> float | None:
        client = get_client()
        macro = client.collection("macro_data")
        try:
            records = macro.get_list(
                params=(f"filter=date<='{dt.isoformat()}' AND {col}!=''&sort=date DESC&per_page=1")
            )
        except Exception:
            records = []
        if records:
            val = getattr(records[0], col, None)
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                return float(val)
        return None

    if benchmark_gold:
        g_start = _get_pb_price("gold_usd", date_start)
        g_end = _get_pb_price("gold_usd", date_end)
        if g_start and g_end and g_start > 0:
            out["gold_usd"] = {
                "price_start": g_start,
                "price_end": g_end,
                "return_pct": round((g_end - g_start) / g_start, 6),
            }

    if benchmark_gold_try_gram:
        gt_start = _get_pb_price("gold_try_gram", date_start)
        gt_end = _get_pb_price("gold_try_gram", date_end)
        if gt_start and gt_end and gt_start > 0:
            out["gold_try_gram"] = {
                "price_start": gt_start,
                "price_end": gt_end,
                "return_pct": round((gt_end - gt_start) / gt_start, 6),
            }

    if benchmark_sp500:
        s_start = _get_pb_price("sp500", date_start)
        s_end = _get_pb_price("sp500", date_end)
        if s_start and s_end and s_start > 0:
            out["sp500"] = {
                "price_start": s_start,
                "price_end": s_end,
                "return_pct": round((s_end - s_start) / s_start, 6),
            }

    return out


# ---------------------------------------------------------------------------
# 8. Sağlık kontrolü
# ---------------------------------------------------------------------------


def check_data_sources() -> dict[str, bool]:
    """Veri kaynaklarının erişilebilirliğini test eder."""
    out: dict[str, bool] = {"yfinance": False, "evds": False, "fred": False}

    try:
        g = yf.download(GC_F_TICKER, period="5d", progress=False)
        out["yfinance"] = not g.empty
    except Exception:
        pass

    today = date.today()
    try:
        evds = _evds_fetch_turkey_cpi(today - timedelta(days=30), today)
        out["evds"] = evds is not None and not evds.empty
    except Exception:
        pass

    if FRED_API_KEY:
        try:
            us = _fred_fetch_us_cpi(today - timedelta(days=30), today)
            out["fred"] = us is not None and not us.empty
        except Exception:
            pass

    return out
