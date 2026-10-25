"""
FutureWallet - Benchmark & Enflasyon Servisi

Piyasa verileri (Altın, S&P 500, TÜFE, US CPI) çeker, macro_data tablosuna
önbelleğe alır ve reel (enflasyondan arındırılmış) değerleme yapar.

MVP §3.4, TODO 1.2, 2.1.
"""

from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd
import yfinance as yf
import requests

from sqlalchemy import select
from sqlalchemy.orm import Session

from db import MacroData
from config import FRED_API_KEY, TCMB_API_KEY


# ---------------------------------------------------------------------------
# Sabitler / konfigürasyon
# ---------------------------------------------------------------------------

GC_F_TICKER   = "GC=F"     # Ons Altın (USD)
XAUUSD_TICKER = "XAUUSD"   # Gram Altın (USD) — yfinance'de bazen GC=F kullanılır
SP500_TICKER  = "^GSPC"    # S&P 500

FRED_CPI_SERIES    = "CPIAUCSL"   # US CPI (All Urban Consumers)
TCMB_TUFE_SERIES  = "TUFE_G_0000000001"   # TÜİK TÜFE (2023=100)

# EVDS API endpoint'leri
EVDS_JSON_URL = "https://evds.tcmb.gov.tr/evds_services/api/values"

# FRED API endpoint'i
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# Fallback annual inflation rates (API erişilemezse kullanılan tahminler)
FALLBACK_TR_CPI_ANNUAL  = 0.487   # 2024 TÜİK TÜFE: ~48.7% (resmi)
FALLBACK_US_CPI_ANNUAL  = 0.035   # 2024 US CPI: ~3.5% (resmi)


# ---------------------------------------------------------------------------
# 1. Piyasa fiyatları (yfinance)
# ---------------------------------------------------------------------------

def fetch_gold_prices(
    start: date,
    end: date,
    granularity: str = "1mo",
) -> pd.DataFrame:
    """
    Ons Altın (GC=F) tarihsel kapanış fiyatlarını çeker.

    Args:
        start: Başlangıç tarihi
        end: Bitiş tarihi (dahil)
        granularity: yfinance timeframe: "1d" | "1wk" | "1mo"

    Returns:
        İndeksi date, columns: Close (float). Boş DataFrame olabilir.
    """
    df = yf.download(GC_F_TICKER, start=start, end=end, progress=False)
    if df.empty:
        return pd.DataFrame()

    # yfinance multi-index columns: (metric, ticker)
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
    """
    S&P 500 (^GSPC) tarihsel kapanış fiyatlarını çeker.
    """
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


def get_current_market_prices() -> Dict[str, Optional[float]]:
    """
    Güncel (bugün) Altın ve S&P 500 fiyatlarını döndürür.
    benchmark_service inertial price fn'lerinde kullanılır.

    Returns:
        {"gold_usd": 2650.0, "sp500": 5800.0}
    """
    out: Dict[str, Optional[float]] = {"gold_usd": None, "sp500": None}

    try:
        # period="1d" yfinance'de GC=F için "delisted" veriyor;
        # 5 günlik pencere kullanıp son available değeri al.
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

    return out


# ---------------------------------------------------------------------------
# 2. TÜİK TÜFE (TR enflasyon) — EVDS API + fallback
# ---------------------------------------------------------------------------

def _evds_fetch_turkey_cpi(
    start: date,
    end: date,
) -> Optional[pd.DataFrame]:
    """
    TCMB EVDS API'sinden TÜFE (TUFE_G_0000000001) serisini çeker.

    API formatı (JSON):
      POST {EVDS_JSON_URL}
      body: {"series": [{"item": "TUFE_G_0000000005"}],
             "startDate": "2024-01-01", "endDate": "2024-12-31"}

    Dönen JSON'da her bir seri için "data" listesi vardır;
    her bir data item'ı: {"date": "2024-01-01", "value": "100.5"}

    Returns:
        İndeksi date (datetime.date), columns: tr_cpi.
        None: API erişilemez hoặc veri yok.
    """
    body = {
        "series": [{"item": TCMB_TUFE_SERIES}],
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
    }

    try:
        resp = requests.post(EVDS_JSON_URL, json=body, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    # EVDS JSON formatı: {"records": {"TUFE_G_...": {"data": [{"date":..., "value":...}]}}}
    # Formatı kontrol edip parse et
    records = data.get("records", {})
    series_data = records.get(TCMB_TUFE_SERIES, {})
    items = series_data.get("data", [])

    if not items:
        return None

    dates = []
    values = []
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
) -> pd.DataFrame:
    """
    Türkiye TÜFE endeksi serisi (aylık).

    Önce EVDS'den çeker. Başarısız olursa fallback: 
    её annually podstawı ile aylık seri üretir.

    Args:
        start: Başlangıç
        end: Bitiş

    Returns:
        İndeksi date, columns: tr_cpi (float).
    """
    evds = _evds_fetch_turkey_cpi(start, end)
    if evds is not None and not evds.empty:
        return evds

    # Fallback: annual rate ile aylık seri üret
    return _build_fallback_tr_cpi(start, end, FALLBACK_TR_CPI_ANNUAL)


def _build_fallback_tr_cpi(
    start: date,
    end: date,
    annual_rate: float,
) -> pd.DataFrame:
    """
    Belirtilen annual inflation rate ile aylık CPI seri üretir.
    Başlangıç tarihindeki CPI = 100 (veya normalize edilmiş bir referans).

    Formula: CPI(ay) = CPI(ay-1) * (1 + annual_rate)^(1/12)
    """
    months = []
    current = start.replace(day=1)
    end_moment = end.replace(day=1)

    # Başlangıç değerini 100 olarak varsay (normalize edilmiş)
    cpi_val = 100.0
    monthly_factor = (1 + annual_rate) ** (1 / 12)

    while current <= end_moment:
        months.append(current)
        current = (current.replace(year=current.year + (current.month // 12),
                                   month=(current.month % 12) + 1)
                   if current.month == 12
                   else current.replace(month=current.month + 1))
        cpi_val *= monthly_factor

    return pd.DataFrame({"tr_cpi": [100.0] + [100.0 * (monthly_factor ** i) for i in range(1, len(months))]},
                        index=months)


# ---------------------------------------------------------------------------
# 3. US CPI (ABD enflasyon) — FRED API + fallback
# ---------------------------------------------------------------------------

def _fred_fetch_us_cpi(
    start: date,
    end: date,
) -> Optional[pd.DataFrame]:
    """
    FRED API'sinden US CPI (CPIAUCSL) serisini çeker.

    GET {FRED_BASE_URL}?series_id={FRED_CPI_SERIES}&api_key={key}
        &observation_start={start}&observation_end={end}&file_type=json

    Returns:
        İndeksi date, columns: us_cpi. None: API erişilemez.
    """
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

    dates = []
    values = []
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
) -> pd.DataFrame:
    """
    US CPI (CPIAUCSL) serisi.
    FRED API key yoksa fallback: annual rate ile aylık seri.
    """
    fred = _fred_fetch_us_cpi(start, end)
    if fred is not None and not fred.empty:
        return fred

    return _build_fallback_us_cpi(start, end, FALLBACK_US_CPI_ANNUAL)


def _build_fallback_us_cpi(
    start: date,
    end: date,
    annual_rate: float,
) -> pd.DataFrame:
    """Fallback US CPI: annual rate ile aylık seri üretir (CPI=100 başlangıç)."""
    months = []
    current = start.replace(day=1)
    end_moment = end.replace(day=1)

    monthly_factor = (1 + annual_rate) ** (1 / 12)

    while current <= end_moment:
        months.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return pd.DataFrame(
        {"us_cpi": [100.0] + [100.0 * (monthly_factor ** i) for i in range(1, len(months))]},
        index=months,
    )


# ---------------------------------------------------------------------------
# 4. Tüm makro verileri çekip DB'ye kaydet
# ---------------------------------------------------------------------------

def fetch_and_save_macro_data(
    session: Session,
    start: Optional[date] = None,
    end: Optional[date] = None,
    save_sp500: bool = True,
    save_gold: bool = True,
    save_tr_cpi: bool = True,
    save_us_cpi: bool = True,
) -> Dict[str, int]:
    """
    Belirtilen tarih aralığında tüm makro verilerini çeker ve macro_data
    tablosuna kaydeder.

    Args:
        session: SQLAlchemy Session
        start: Başlangıç. None → 1 yıl önce
        end: Bitiş. None → bugün
        save_*: Hangi veriyi çeker/kaydeder

    Returns:
        {"gold": N, "sp500": N, "tr_cpi": N, "us_cpi": N} — kaça row eklendi/update
    """
    if start is None:
        start = date.today().replace(year=date.today().year - 1)
    if end is None:
        end = date.today()

    # haftalık aralık kullan (SP500/gold için daily fazla olabilir)
    # Bu fonksiyon ayık seviye data çeker; daily detay sitenize göre ayarlanır
    stats: Dict[str, int] = {"gold": 0, "sp500": 0, "tr_cpi": 0, "us_cpi": 0}

    # Altın
    if save_gold:
        gold_df = fetch_gold_prices(start, end, granularity="1mo")
        stats["gold"] = _upsert_macro_df(session, gold_df, "gold_usd")

    # S&P 500
    if save_sp500:
        sp_df = fetch_sp500_prices(start, end, granularity="1mo")
        stats["sp500"] = _upsert_macro_df(session, sp_df, "sp500")

    # TÜFE
    if save_tr_cpi:
        tr_df = fetch_turkey_cpi(start, end)
        stats["tr_cpi"] = _upsert_macro_df(session, tr_df, "tr_cpi")

    # US CPI
    if save_us_cpi:
        us_df = fetch_us_cpi(start, end)
        stats["us_cpi"] = _upsert_macro_df(session, us_df, "us_cpi")

    session.commit()
    return stats


def _upsert_macro_df(
    session: Session,
    df: pd.DataFrame,
    value_col: str,
) -> int:
    """
    Bir DataFrame'i macro_data tablosuna upsert eder.
    value_col: 'gold_usd' | 'sp500' | 'tr_cpi' | 'us_cpi'

    DataFrame şu formatta olmalı:
      index = date (datetime.date veya datetime)
      columns = [value_col]

    Returns:
        Kaç row eklendi/updated.
    """
    if df.empty:
        return 0

    count = 0
    for dt, row in df.iterrows():
        d = dt.date() if hasattr(dt, "date") else dt
        val = row[value_col]

        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue

        existing = session.execute(
            select(MacroData).where(MacroData.date == d)
        ).scalars().first()

        if existing:
            setattr(existing, value_col, float(val))
        else:
            session.add(MacroData(date=d, **{value_col: float(val)}))

        count += 1

    return count


# ---------------------------------------------------------------------------
# 5. Reel değerleme: enflasyondan arındırılmış getiri
# ---------------------------------------------------------------------------

def get_cpi_for_date(
    session: Session,
    dt: date,
    cpi_type: str = "us",   # "us" | "tr"
) -> Optional[float]:
    """
    Belirtilen tarihteki veya en yakın geçmiş (ve CPI değeri olan) CPI
    değerini DB'den döndürür.

    CPI verisi aylık olduğundan, tarih tam eşleşmeyebilir.
    dt'ye eşit veya önceki, tr_cpi/us_cpi değeri dolu olan en son satırı
    döndürür.

    Args:
        session: SQLAlchemy Session
        dt: Tarih
        cpi_type: "us" → us_cpi, "tr" → tr_cpi
    """
    col = "us_cpi" if cpi_type == "us" else "tr_cpi"
    row = session.execute(
        select(getattr(MacroData, col))
        .where(MacroData.date <= dt)
        .where(getattr(MacroData, col).isnot(None))
        .order_by(MacroData.date.desc())
        .limit(1)
    ).scalars().first()
    return row


def adjust_for_inflation(
    session: Session,
    nominal_value: float,
    date_from: date,
    date_to: date,
    cpi_type: str = "tr",
) -> Optional[float]:
    """
    Nominal bir değeri, date_from'tan date_toye kadar olan enflasyona
    göre ayarlar (reel değer =nominal × CPI(date_from) / CPI(date_to)).

    Enflasyondan arındırılmış getiri hesabı için:
      reel_değer = nominal × CPI(başlangıç) / CPI(bitiş)

    Eğer date_to > date_from ise:
      - CPI(bitiş) > CPI(başlangıç) → reel değer nominalden KüÇÜK
        (para değerini kaybetmiş demektir)

    Args:
        session: SQLAlchemy Session
        nominal_value: Anlagın nominal değeri
        date_from: Başlangıç tarihi ( CPI buradan )
        date_to: Bitiş tarihi ( CPI buradan )
        cpi_type: "tr" → TÜFE, "us" → US CPI

    Returns:
        Reel değer. None: CPI verisi bulunamadı.
    """
    cpi_from = get_cpi_for_date(session, date_from, cpi_type)
    cpi_to   = get_cpi_for_date(session, date_to,   cpi_type)

    if cpi_from is None or cpi_to is None:
        return None

    if cpi_to == 0:
        return None

    return nominal_value * (cpi_from / cpi_to)


def compute_real_return(
    session: Session,
    portfolio_value_start: float,
    portfolio_value_end: float,
    date_start: date,
    date_end: date,
    cpi_type: str = "tr",
) -> Dict[str, Optional[float]]:
    """
    Portföyün reel (enflasyondan arındırılmış) getirisini hesaplar.

    Args:
        session: SQLAlchemy Session
        portfolio_value_start: T_start'deki portföy değeri (nominal)
        portfolio_value_end:   T_end'teki portföy değeri (nominal)
        date_start: Başlangıç
        date_end: Bitiş
        cpi_type: "tr" → TÜFE, "us" → US CPI

    Returns:
        {
            "nominal_return_pct": float,   # (end-start)/start
            "real_return_pct": float | None, # enflasyondan arındırılmış
            "cpi_type": str,
            "cpi_from": float | None,
            "cpi_to": float | None,
        }
    """
    cpi_from = get_cpi_for_date(session, date_start, cpi_type)
    cpi_to   = get_cpi_for_date(session, date_end,   cpi_type)

    nominal_return = ((portfolio_value_end - portfolio_value_start)
                      / portfolio_value_start) if portfolio_value_start else 0.0

    real_return: Optional[float] = None
    if cpi_from and cpi_to and cpi_to > 0:
        # Reel getiri = (nominal getiri - enflasyon)
        # = (nominal_end / nominal_start) × (CPI_from / CPI_to) - 1
        real_return = ((portfolio_value_end / portfolio_value_start)
                       * (cpi_from / cpi_to)) - 1.0

    return {
        "nominal_return_pct": round(nominal_return, 6),
        "real_return_pct": round(real_return, 6) if real_return is not None else None,
        "cpi_type": cpi_type,
        "cpi_from": cpi_from,
        "cpi_to": cpi_to,
    }


# ---------------------------------------------------------------------------
# 6. Benchmark kıyas
# ---------------------------------------------------------------------------

def compare_to_benchmark(
    session: Session,
    portfolio_value_start: float,
    portfolio_value_end: float,
    date_start: date,
    date_end: date,
    benchmark_gold: bool = True,
    benchmark_sp500: bool = True,
) -> Dict:
    """
    Portföy performansını Altın ve S&P 500 ile kıyaslar.

    DB'macro_data'den fiyatları çeker; yoksa yfinance'den çeker.

    Args:
        session: SQLAlchemy Session
        portfolio_value_start: T_start portföy değeri
        portfolio_value_end:   T_end portföy değeri
        date_start: Başlangıç
        date_end: Bitiş
        benchmark_gold: Altın kıyasını dahil et
        benchmark_sp500: SP500 kıyasını dahil et

    Returns:
        {
            "portfolio_return_pct": float,
            "gold": {"price_start": float|None, "price_end": float|None,
                     "return_pct": float|None},
            "sp500": {"price_start": float|None, "price_end": float|None,
                      "return_pct": float|None},
        }
    """
    out: Dict = {
        "portfolio_return_pct": round(
            (portfolio_value_end - portfolio_value_start) / portfolio_value_start
            if portfolio_value_start else 0.0, 6
        ),
        "gold": {"price_start": None, "price_end": None, "return_pct": None},
        "sp500": {"price_start": None, "price_end": None, "return_pct": None},
    }

    def _get_benchmark_price(benchmark_col: str, dt: date) -> Optional[float]:
        """DB'den dt'ye eşit veya önceki en son benchmark fiyatını çeker;
        yoksa yfinance'den range ile en yakın değer alınır."""
        # 1) DB'de nearest-on-or-before
        row = session.execute(
            select(getattr(MacroData, benchmark_col))
            .where(MacroData.date <= dt)
            .order_by(MacroData.date.desc())
            .limit(1)
        ).scalars().first()
        if row is not None:
            return float(row)
        # 2) DB boş → yfinance range ile en yakın değer
        if benchmark_col == "gold_usd":
            df = fetch_gold_prices(dt, dt)
        else:
            df = fetch_sp500_prices(dt, dt)
        if not df.empty:
            return float(df.iloc[0][benchmark_col])
        return None

    # Altın
    if benchmark_gold:
        gold_start = _get_benchmark_price("gold_usd", date_start)
        gold_end   = _get_benchmark_price("gold_usd", date_end)
        if gold_start and gold_end and gold_start > 0:
            out["gold"] = {
                "price_start": gold_start,
                "price_end": gold_end,
                "return_pct": round((gold_end - gold_start) / gold_start, 6),
            }

    # S&P 500
    if benchmark_sp500:
        sp_start = _get_benchmark_price("sp500", date_start)
        sp_end   = _get_benchmark_price("sp500", date_end)
        if sp_start and sp_end and sp_start > 0:
            out["sp500"] = {
                "price_start": sp_start,
                "price_end": sp_end,
                "return_pct": round((sp_end - sp_start) / sp_start, 6),
            }

    return out


# ---------------------------------------------------------------------------
# 7. Sağlık kontrolü (API erişilebilir mi?)
# ---------------------------------------------------------------------------

def check_data_sources() -> Dict[str, bool]:
    """
    Veri kaynaklarının erişilebilirliğini test eder.

    Returns:
        {"yfinance": bool, "evds": bool, "fred": bool}
    """
    out: Dict[str, bool] = {"yfinance": False, "evds": False, "fred": False}

    # yfinance test
    try:
        g = yf.download(GC_F_TICKER, period="5d", progress=False)
        out["yfinance"] = not g.empty
    except Exception:
        pass

    # EVDS test (son 30 gün)
    today = date.today()
    from datetime import timedelta
    try:
        evds = _evds_fetch_turkey_cpi(
            today - timedelta(days=30), today
        )
        out["evds"] = evds is not None and not evds.empty
    except Exception:
        pass

    # FRED test (API key varsa)
    if FRED_API_KEY:
        try:
            us = _fred_fetch_us_cpi(today - timedelta(days=30), today)
            out["fred"] = us is not None and not us.empty
        except Exception:
            pass
    else:
        out["fred"] = False  # key yok, test edilemez

    return out
