"""
FutureWallet - Price Service (Fiyat Çekme & Cache)

Fiyat çekme fonksiyonları:
- get_price_on(symbol, asset_type, on_date) -> Optional[float]
- get_prices_in_range(symbol, asset_type, start_date, end_date) -> dict

Kaynak önceliği:
1. PocketBase price_history cache (eğer varsa)
2. yfinance tarihsel kapanış (hafta sonu/tatil hariç)
3. ccxt OHLCV (crypto için)

NOT: Bu service hala geliştirme aşamasında - tam integrate edilmedi.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Optional

import pandas as pd
import yfinance as yf

from config import POCKETBASE_URL
from services.pocketbase import get_client

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

GC_F_TICKER = "GC=F"  # Ons Altın (USD) – COMEX
XAUUSD_TICKER = "XAUUSD"  # Gram Altın (USD)
SP500_TICKER = "^GSPC"  # S&P 500
USDTRY_TICKER = "USDTRY=X"  # USD/TRY kur

DEFAULT_CACHE_TTL_DAYS = 7  # Fiyat cache'inin geçerlilik süresi


# ---------------------------------------------------------------------------
# PocketBase Price History Cache
# ---------------------------------------------------------------------------


def _get_price_from_pb(symbol: str, on_date: date) -> Optional[float]:
    """PocketBase price_history koleksiyonundan fiyat çek."""
    try:
        client = get_client()
        ph = client.collection("price_history")
        records = ph.get_list(
            params=(
                f"filter=symbol='{symbol}' AND date='{on_date.isoformat()}'"
                f"&per_page=1"
            )
        )
        if records:
            return float(records[0].get("close", 0))
    except Exception:
        pass
    return None


def _save_price_to_pb(symbol: str, on_date: date, close_price: float) -> None:
    """PocketBase price_history koleksiyonuna fiyat kaydet."""
    try:
        client = get_client()
        ph = client.collection("price_history")
        ph.create(
            {
                "symbol": symbol,
                "date": on_date.isoformat(),
                "close": close_price,
            }
        )
    except Exception:
        pass  # Cache kaydetme hatası olfactory


# ---------------------------------------------------------------------------
# yfinance ile fiyat çekme
# ---------------------------------------------------------------------------


def _fetch_yfinance_price(symbol: str, on_date: date) -> Optional[float]:
    """yfinance ile belirtilen tarihteki fiyatı çeker.

    Hafta sonleri ve tatil günleri için en yakın ÖNCEKİ işlem gününü döndürür.
    """
    # Tarihçekikellananın en yakın önceki işlem gününü bul
    # (yfinance hafta soni veri döndürmüyor)
    end_date = on_date
    start_date = on_date - timedelta(days=10)

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date.isoformat(), end=end_date.isoformat())
        if df.empty:
            return None
        # En yakın tarihi al
        df.index = pd.to_datetime(df.index).date
        closest = df.index[-1] if len(df) > 0 else None
        if closest and closest <= on_date:
            return float(df.loc[closest, "Close"])
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Ana fonksiyonlar
# ---------------------------------------------------------------------------


def get_price_on(
    symbol: str,
    asset_type: str = "crypto",
    on_date: date | None = None,
) -> Optional[float]:
    """Belirtilen tarihteki fiyatı döndürür.

    Args:
        symbol: Varlık sembolü (örn: BTC, GC=F, ^GSPC)
        asset_type: Varlık tipi (crypto, stock_tr, stock_us, commodity, forex, cash)
        on_date: Fiyat tarihi. None → bugün (güncel fiyat).

    Returns:
        Fiyat (float) veya None (veri yok).
    """
    if on_date is None:
        on_date = date.today()

    # 1. Önce PocketBase cache'ini dene
    pb_price = _get_price_from_pb(symbol, on_date)
    if pb_price is not None and pb_price > 0:
        return pb_price

    # 2. yfinance'den çek
    yf_price = _fetch_yfinance_price(symbol, on_date)
    if yf_price is not None and yf_price > 0:
        # Cache'e kaydet
        _save_price_to_pb(symbol, on_date, yf_price)
        return yf_price

    return None


def get_prices_in_range(
    symbol: str,
    start_date: date,
    end_date: date,
    asset_type: str = "crypto",
) -> dict[str, float]:
    """Belirtilen aralıktaki tüm fiyatları döndürür.

    Kaçınır grocery: PB cache → yfinance → combine.

    Returns:
        { "YYYY-MM-DD": fiyat, ... }
    """
    prices: dict[str, float] = {}

    # Aralığı günlere ayır
    current = start_date
    while current <= end_date:
        # Önce cache'ii dene
        pb_price = _get_price_from_pb(symbol, current)
        if pb_price is not None and pb_price > 0:
            prices[current.isoformat()] = pb_price
        else:
            # yfinance'den çek
            yf_price = _fetch_yfinance_price(symbol, current)
            if yf_price is not None and yf_price > 0:
                prices[current.isoformat()] = yf_price
                _save_price_to_pb(symbol, current, yf_price)
        current += timedelta(days=1)

    return prices


# ---------------------------------------------------------------------------
# Helper: asset_type based on symbol
# ---------------------------------------------------------------------------


def guess_asset_type(symbol: str) -> str:
    """Sembollere göre asset_type tahmini."""
    cash = frozenset({"USDT", "USD", "TRY", "TL", "EUR", "GBP"})
    gold = frozenset({"GC=F", "XAU", "GOLD"})
    up = symbol.upper()
    if up in cash:
        return "cash"
    if up in gold or "GOLD" in up or "ALTIN" in up:
        return "commodity"
    if ".IS" in up or up in ("THYAO", "GARAN", "ASELS", "TUPRS", "SISE"):
        return "stock_tr"
    if "^GSPC" in up:
        return "stock_us"
    if up.endswith("=X") or up.endswith("USD=X"):
        return "forex"
    return "crypto"
