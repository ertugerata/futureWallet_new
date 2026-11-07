"""
Price Service – minimal stub implementation.
Provides functions to obtain asset prices from PocketBase cache, yfinance, and ccxt.
Only the signatures required by the codebase are implemented; full external API
calls are omitted for brevity.
"""

from datetime import date
from typing import List, Optional

# NOTE: In a full implementation this would import the PocketBase client and
# external price providers. Here we provide a lightweight stub that returns None
# for missing data so that the application can start without runtime errors.

def _load_from_cache(symbol: str, asset_type: str, on_date: date) -> Optional[float]:
    """Attempt to read a cached price from PocketBase.
    Returns ``None`` if the cache entry does not exist.
    """
    # Placeholder: real implementation would query the ``price_history`` collection.
    return None

def _fetch_from_yfinance(symbol: str, asset_type: str, on_date: date) -> Optional[float]:
    """Fetch price from yfinance. Stub returns ``None``.
    """
    return None

def _fetch_from_ccxt(symbol: str, asset_type: str, on_date: date) -> Optional[float]:
    """Fetch price from ccxt. Stub returns ``None``.
    """
    return None

def get_price_on(symbol: str, asset_type: str, on_date: date) -> Optional[float]:
    """Get the price for ``symbol`` on ``on_date``.
    The lookup order is:
    1. PocketBase cache
    2. yfinance
    3. ccxt
    If none provide a value, ``None`` is returned.
    """
    price = _load_from_cache(symbol, asset_type, on_date)
    if price is not None:
        return price
    price = _fetch_from_yfinance(symbol, asset_type, on_date)
    if price is not None:
        return price
    price = _fetch_from_ccxt(symbol, asset_type, on_date)
    return price

def get_prices_in_range(symbol: str, asset_type: str, start_date: date, end_date: date) -> List[tuple[date, Optional[float]]]:
    """Return a list of ``(date, price)`` tuples for the inclusive date range.
    This stub iterates day by day and calls :func:`get_price_on`.
    """
    delta = (end_date - start_date).days
    result: List[tuple[date, Optional[float]]] = []
    for i in range(delta + 1):
        d = start_date.fromordinal(start_date.toordinal() + i)
        result.append((d, get_price_on(symbol, asset_type, d)))
    return result
