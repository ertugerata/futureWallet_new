"""
FutureWallet - Price Service (PocketBase Cache + yfinance + ccxt)
==================================================================
Varlık fiyatlarını PocketBase price_history önbelleğinden, yfinance veya ccxt'den çeker.
Hafta sonu/tatil günleri için geriye dönük arama (fallback) desteği sunar.

Prompt 9 ile uyumludur.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def _load_from_cache(symbol: str, on_date: date) -> Optional[float]:
    """PocketBase price_history koleksiyonundan fiyat oku."""
    try:
        from services.pb import get_admin_client

        client = get_admin_client()
        date_str = on_date.isoformat()
        records = client.collection("price_history").get_full_list(
            query_params={
                "filter": client.filter(
                    "symbol = {:symbol} && date ~ {:date}", {"symbol": symbol, "date": date_str}
                )
            }
        )
        if records:
            return float(records[0].price)
    except Exception as exc:
        logger.debug("Cache okuma hatası (%s, %s): %s", symbol, on_date, exc)
    return None


def _save_to_cache(symbol: str, on_date: date, price: float) -> None:
    """PocketBase price_history koleksiyonuna fiyat kaydet.

    Şemada olmayan alan PB'de sessiz düşer (asset_type yazımı e2e denetiminde
    kaldırıldı; provenance için şemadaki `source` alanı kullanılır).
    """
    try:
        from services.pb import get_admin_client

        client = get_admin_client()
        date_str = on_date.isoformat()
        client.collection("price_history").create(
            {
                "symbol": symbol,
                "date": f"{date_str} 00:00:00.000Z",
                "price": price,
            }
        )
    except Exception as exc:
        logger.debug("Cache kaydetme hatası (%s, %s): %s", symbol, on_date, exc)


def _fetch_from_yfinance(symbol: str, on_date: date) -> Optional[float]:
    """yfinance ile belirli bir tarihteki kapanış fiyatını al."""
    try:
        import yfinance as yf

        end = on_date + timedelta(days=1)
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=on_date.isoformat(), end=end.isoformat())
        if not df.empty and "Close" in df.columns:
            return float(df["Close"].iloc[-1])
    except Exception as exc:
        logger.debug("yfinance fiyat çekme hatası (%s, %s): %s", symbol, on_date, exc)
    return None


def _fetch_from_ccxt(symbol: str, on_date: date) -> Optional[float]:
    """ccxt ile kripto varlık fiyatını al."""
    # Çoğu kripto sembolü yfinance üzerinden de (örn. BTC-USD) çekilebilir
    return None


def get_price_on(
    symbol: str,
    asset_type: str,
    on_date: date,
    lookback_days: int = 4,
) -> Optional[float]:
    """
    Belirli bir tarihteki varlık fiyatını döner.
    1. PB cache
    2. yfinance / ccxt
    Hafta sonu/tatil durumunda geriye doğru lookback_days kadar gün arar.
    """
    curr_date = on_date
    for _ in range(lookback_days + 1):
        # 1. Cache kontrolü
        cached = _load_from_cache(symbol, curr_date)
        if cached is not None:
            return cached

        # 2. Dış servis kontrolü
        price = _fetch_from_yfinance(symbol, curr_date)
        if price is not None:
            _save_to_cache(symbol, curr_date, price)
            return price

        price = _fetch_from_ccxt(symbol, curr_date)
        if price is not None:
            _save_to_cache(symbol, curr_date, price)
            return price

        # Geriye dönük gün ara (hafta sonu / resmi tatil)
        curr_date -= timedelta(days=1)

    return None


def get_prices_in_range(
    symbol: str,
    asset_type: str,
    start_date: date,
    end_date: date,
) -> list[tuple[date, Optional[float]]]:
    """Belirtilen tarih aralığında her gün için (date, price) ikilisi döner."""
    delta = (end_date - start_date).days
    result: list[tuple[date, Optional[float]]] = []
    for i in range(delta + 1):
        d = start_date + timedelta(days=i)
        result.append((d, get_price_on(symbol, asset_type, d)))
    return result
