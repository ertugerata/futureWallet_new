"""
FutureWallet – Ortak Enum Tanımları
====================================
Tüm model, şema ve servisler için tek doğruluk kaynağı (Prompt 3).
"""

from enum import Enum


class Sentiment(str, Enum):
    FOMO = "FOMO"
    STRATEGIC = "STRATEGIC"
    PANIC = "PANIC"
    DIVIDEND = "DIVIDEND"
    OPPORTUNITY = "OPPORTUNITY"


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class DecisionStatus(str, Enum):
    OPEN = "OPEN"
    EXPIRED = "EXPIRED"
    REVIEWED = "REVIEWED"
    CLOSED = "CLOSED"


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    CASH_IN = "CASH_IN"
    CASH_OUT = "CASH_OUT"


class ShadowType(str, Enum):
    HELD_INSTEAD = "HELD_INSTEAD"
    BOUGHT_INSTEAD = "BOUGHT_INSTEAD"


SENTIMENT_ALLOWED = frozenset(s.value for s in Sentiment)
ACTION_ALLOWED = frozenset(a.value for a in Action)
STATUS_ALLOWED = frozenset(d.value for d in DecisionStatus)

SENTIMENT_LABELS = {
    Sentiment.FOMO.value: "FOMO (Fırsatı Kaçırma Korkusu)",
    Sentiment.STRATEGIC.value: "Stratejik Analiz",
    Sentiment.PANIC.value: "Panik Satışı",
    Sentiment.DIVIDEND.value: "Temettü/Gelir",
    Sentiment.OPPORTUNITY.value: "Fırsat",
}
