"""
FutureWallet - Varlık Türü ve Sembol Yardımcıları
==================================================
Sembol adına göre varlık türü tahmini tek doğruluk kaynağı (Prompt 15).
"""

from __future__ import annotations

_CASH_SYMBOLS = frozenset({"USDT", "USD", "TRY", "TL", "EUR", "GBP"})
_GOLD_SYMBOLS = frozenset({"GC=F", "XAU", "GOLD"})


def guess_asset_type(symbol: str) -> str:
    """Sembol adına göre varlık türü tahmini."""
    if not symbol:
        return "crypto"
    up = symbol.upper()
    if up in _CASH_SYMBOLS:
        return "cash"
    if up in _GOLD_SYMBOLS or "GOLD" in up or "ALTIN" in up:
        return "commodity"
    if ".IS" in up or up in ("THYAO", "GARAN", "ASELS", "TUPRS", "SISE"):
        return "stock_tr"
    if "^GSPC" in up:
        return "stock_us"
    if up.endswith("=X") or up.endswith("USD=X"):
        return "forex"
    return "crypto"


# Geriye dönük uyumluluk alias'ı
_guess_asset_type = guess_asset_type
