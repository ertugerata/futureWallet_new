"""
FutureWallet - Varlık Türü ve Sembol Yardımcıları
==================================================
Sembol adına göre varlık türü tahmini tek doğruluk kaynağı (Prompt 15).
"""

from __future__ import annotations

from collections.abc import Sequence

_CASH_SYMBOLS = frozenset({"USDT", "USD", "TRY", "TL", "EUR", "GBP"})
_GOLD_SYMBOLS = frozenset({"GC=F", "XAU", "GOLD"})


def guess_asset_type(symbol: str) -> str:
    """Sembol adına göre varlık türü tahmini."""
    up = symbol.upper() if symbol else ""
    kind = "crypto"
    if up in _CASH_SYMBOLS:
        kind = "cash"
    elif up in _GOLD_SYMBOLS or "GOLD" in up or "ALTIN" in up:
        kind = "commodity"
    elif ".IS" in up or up in ("THYAO", "GARAN", "ASELS", "TUPRS", "SISE"):
        kind = "stock_tr"
    elif "^GSPC" in up:
        kind = "stock_us"
    elif up.endswith("=X"):
        kind = "forex"
    return kind


# Geriye dönük uyumluluk alias'ı
_guess_asset_type = guess_asset_type


def base_currency(symbol: str) -> str:
    """Varlığın taban para birimi: BIST/TL → TRY; kripto, ABD hissesi, emtia, forex → USD."""
    up = (symbol or "").upper()
    if up in ("TRY", "TL") or guess_asset_type(up) == "stock_tr":
        return "TRY"
    return "USD"


def infer_portfolio_currency(symbols: Sequence[str]) -> str:
    """Sepetin gösterim para birimi: USD çoğunlukta ise USD; eşitlik veya boş küme TRY.

    shortcut: karışık sepet tek currency olarak çoğunluğa göre etiketlenir; fiyatlar
    taban para biriminde toplandığı için gerçek çoklu-currency değerlemesi gelince
    bu tek-değer gösterimi kaldırılmalı.
    """
    try_n = sum(1 for s in symbols if base_currency(s) == "TRY")
    usd_n = len(symbols) - try_n
    return "USD" if usd_n > try_n else "TRY"
