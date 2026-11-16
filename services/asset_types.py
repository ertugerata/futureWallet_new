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
