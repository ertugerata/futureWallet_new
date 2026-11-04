"""
PocketBase Async Client ve Collection Yönetimi
================================================
Veritabanı katmanı için PocketBase Async Python SDK.

Veri modelleri:
  - transactions    (event-sourced işlem defteri)
  - decisions       (karar günlüğü)
  - shadow_portfolios  (gölge portföy)
  - macro_data      (TÜİK/FRED/benchmark cache)
  - price_history   (fiyat cache, Prompt 9)

--- migrazione / migration stratejisi ----
PB embedde SQLite ile gelir; collection şemaları application start-up'da
ensure_collections() tarafından otomatik oluşturulur.
Alembic gerekmez; PB'nin kendi schema yönetimi yeterli.

--- kullanım ----
from services.pocketbase import get_client, init_pocketbase_collections, shutdown_pocketbase

client = get_client()                       # lazy singleton
await init_pocketbase_collections()         # app lifespan
txs = client.client.collection("transactions")
records = txs.get_list("page=1&per_page=50")
await txs.create({"user": "abc123", "asset_symbol": "BTC/USDT", ...})
await shutdown_pocketbase()                 # app shutdown
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from config import POCKETBASE_EMAIL, POCKETBASE_PASSWORD, POCKETBASE_URL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Koleksiyon şemaları (Prompt 5.2 – MVP.md §5)
# ---------------------------------------------------------------------------

TRANSACTIONS_SCHEMA: Dict[str, Any] = {
    "name": "transactions",
    "type": "base",
    "listRule": "",
    "viewRule": "",
    "createRule": "@request.auth.id != ''",
    "updateRule": "@request.auth.id != ''",
    "deleteRule": "@request.auth.id != ''",
    "fields": [
        {
            "name": "user",
            "type": "relation",
            "required": True,
            "maxSelect": 1,
            "relation": {"collection": "users", "cascadeDelete": False, "maxSelect": 1},
        },
        {
            "name": "asset_symbol",
            "type": "text",
            "required": True,
            "max": 50,
        },
        {
            "name": "type",
            "type": "select",
            "required": True,
            "options": ["BUY", "SELL", "DIVIDEND", "CASH_IN", "CASH_OUT"],
        },
        {
            "name": "quantity",
            "type": "number",
            "required": True,
            "min": 0,
        },
        {
            "name": "price",
            "type": "number",
            "required": True,
            "min": 0,
        },
        {
            "name": "fee",
            "type": "number",
            "min": 0,
            "default": 0,
        },
        {
            "name": "timestamp",
            "type": "date",
            "required": True,
        },
        {
            "name": "voided",
            "type": "bool",
            "default": False,
        },
    ],
}

DECISIONS_SCHEMA: Dict[str, Any] = {
    "name": "decisions",
    "type": "base",
    "listRule": "",
    "viewRule": "",
    "createRule": "@request.auth.id != ''",
    "updateRule": "@request.auth.id != ''",
    "deleteRule": "@request.auth.id != ''",
    "fields": [
        {
            "name": "user",
            "type": "relation",
            "required": True,
            "maxSelect": 1,
            "relation": {"collection": "users", "cascadeDelete": False, "maxSelect": 1},
        },
        {
            "name": "asset_symbol",
            "type": "text",
            "required": True,
            "max": 50,
        },
        {
            "name": "action",
            "type": "select",
            "required": True,
            "options": ["BUY", "SELL", "HOLD"],
        },
        {
            "name": "sentiment",
            "type": "select",
            "required": True,
            "options": ["FOMO", "PANIC", "STRATEGIC", "DIVIDEND", "OPPORTUNITY"],
        },
        {
            "name": "rationale",
            "type": "text",
            "max": 5000,
        },
        {
            "name": "target_price",
            "type": "number",
            "min": 0,
        },
        {
            "name": "target_date",
            "type": "date",
        },
        {
            "name": "status",
            "type": "select",
            "options": ["OPEN", "EXPIRED", "REVIEWED", "CLOSED"],
            "default": "OPEN",
        },
        {
            "name": "ai_retrospective",
            "type": "text",
        },
        {
            "name": "outcome_return_pct",
            "type": "number",
        },
        {
            "name": "decision_date",
            "type": "date",
        },
        {
            "name": "outcome_price",
            "type": "number",
        },
        {
            "name": "target_hit",
            "type": "bool",
        },
    ],
}

SHADOW_PORTFOLIOS_SCHEMA: Dict[str, Any] = {
    "name": "shadow_portfolios",
    "type": "base",
    "listRule": "",
    "viewRule": "",
    "createRule": "@request.auth.id != ''",
    "updateRule": "@request.auth.id != ''",
    "deleteRule": "@request.auth.id != ''",
    "fields": [
        {
            "name": "decision",
            "type": "relation",
            "maxSelect": 1,
            "relation": {"collection": "decisions", "cascadeDelete": True, "maxSelect": 1},
        },
        {
            "name": "user",
            "type": "relation",
            "required": True,
            "maxSelect": 1,
            "relation": {"collection": "users", "cascadeDelete": False, "maxSelect": 1},
        },
        {
            "name": "asset_symbol",
            "type": "text",
            "required": True,
            "max": 50,
        },
        {
            "name": "shadow_type",
            "type": "select",
            "required": True,
            "options": ["HELD_INSTEAD", "BOUGHT_INSTEAD"],
        },
        {
            "name": "entry_price",
            "type": "number",
            "required": True,
            "min": 0,
        },
        {
            "name": "quantity",
            "type": "number",
            "required": True,
            "min": 0,
        },
        {
            "name": "entry_date",
            "type": "date",
            "required": True,
        },
        {
            "name": "exit_date",
            "type": "date",
        },
        {
            "name": "asset_type",
            "type": "text",
        },
    ],
}

MACRO_DATA_SCHEMA: Dict[str, Any] = {
    "name": "macro_data",
    "type": "base",
    "listRule": "",
    "viewRule": "",
    "createRule": "",
    "updateRule": "",
    "deleteRule": "",
    "fields": [
        {
            "name": "date",
            "type": "date",
            "required": True,
        },
        {
            "name": "gold_try",
            "type": "number",
        },
        {
            "name": "gold_usd",
            "type": "number",
        },
        {
            "name": "sp500",
            "type": "number",
        },
        {
            "name": "tr_cpi",
            "type": "number",
        },
        {
            "name": "us_cpi",
            "type": "number",
        },
        {
            "name": "source",
            "type": "text",
        },
        {
            "name": "is_estimate",
            "type": "bool",
            "default": False,
        },
    ],
}

PRICE_HISTORY_SCHEMA: Dict[str, Any] = {
    "name": "price_history",
    "type": "base",
    "listRule": "",
    "viewRule": "",
    "createRule": "",
    "updateRule": "",
    "deleteRule": "",
    "fields": [
        {
            "name": "symbol",
            "type": "text",
            "required": True,
            "max": 50,
        },
        {
            "name": "date",
            "type": "date",
            "required": True,
        },
        {
            "name": "close",
            "type": "number",
            "required": True,
        },
        {
            "name": "currency",
            "type": "text",
        },
        {
            "name": "source",
            "type": "text",
        },
    ],
}

ALL_COLLECTIONS: List[Dict[str, Any]] = [
    TRANSACTIONS_SCHEMA,
    DECISIONS_SCHEMA,
    SHADOW_PORTFOLIOS_SCHEMA,
    MACRO_DATA_SCHEMA,
    PRICE_HISTORY_SCHEMA,
]


# ---------------------------------------------------------------------------
# PocketBaseClient (lazy singleton)
# ---------------------------------------------------------------------------

class PocketBaseClient:
    """Lazy singleton Async PocketBase client.

    PB admin API'si ile koleksiyon yönetimi.
    Bu client'ın `client` özelliği pocketbase.PocketBase instance'ıdır;
    business servislerde collection() → list/create/update/delete işlemleri için kullanılır.
    """

    _instance: "PocketBaseClient | None" = None

    def __init__(self) -> None:
        try:
            import pocketbase
        except ImportError as e:
            raise ImportError(
                "pocketbase paketi yüklenemedi. `pip install pocketbase` ile kurulum yapın."
            ) from e

        self._pb = pocketbase.PocketBase(POCKETBASE_URL)

        # Admin servis: kollek. yönetim için; uygulama auth'sı ayrı FastAPI token
        self._admin = self._pb.admins
        try:
            self._admin.auth_with_password(POCKETBASE_EMAIL, POCKETBASE_PASSWORD)
            logger.info("PocketBase admin authenticated (collection management).")
        except Exception as exc:
            logger.warning(
                "PocketBase admin login failed (collections may not be managed automatically): %s",
                exc,
            )

        # İş mantığı client'ı ayrı olacak (user auth ile); bu admin client sadece şema/yönetim.
        self._business_client: pocketbase.PocketBase | None = None

    def collection(self, name: str):
        """PB collection accessor (servis pattern: client.collection('decisions').get_list(...))."""
        return self._pb.collection(name)

    @property
    def client(self) -> Any:
        """İş mantığı client'ı (her istekte auth yoksa token-less; servisler kendi auth'ı ekler)."""
        if self._business_client is None:
            self._business_client = type(self._pb)(POCKETBASE_URL)  # ayrı instance
        return self._business_client

    @classmethod
    async def get_instance(cls) -> "PocketBaseClient":
        """Async factory (event loop'a bağlı olabileceği için async)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def collection_exists(self, name: str) -> bool:
        """İlgili koleksiyon PB'de var mı?"""
        try:
            self._pb.collections.get_one(name)
            return True
        except Exception:
            return False

    async def create_collection(self, schema: Dict[str, Any]) -> bool:
        """Koleksiyon oluştur. Zaten varsa True döner, hata durumunda False."""
        name = schema.get("name", "<no-name>")
        if await self.collection_exists(name):
            logger.debug("Collection '%s' already exists.", name)
            return True
        try:
            self._pb.collections.create(body_params=schema)
            logger.info("Collection '%s' created.", name)
            return True
        except Exception as exc:
            logger.error("Failed to create collection '%s': %s", name, exc)
            return False

    async def ensure_collections(self) -> None:
        """Tüm koleksiyonları yoksa oluştur (Prompt 6 ve MVP.md §5)."""
        for schema in ALL_COLLECTIONS:
            await self.create_collection(schema)

    async def close(self) -> None:
        """Client bağlantılarını kapat."""
        if self._business_client is not None:
            await self._business_client.client.close()
            self._business_client = None
        if self._pb is not None:
            await self._pb.client.close()
            self._pb = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Global erişim (lazy)
# ---------------------------------------------------------------------------

_client: PocketBaseClient | None = None


def get_client() -> PocketBaseClient:
    """Lazy singleton PB client."""
    global _client
    if _client is None:
        _client = PocketBaseClient()
    return _client


async def init_pocketbase_collections() -> None:
    """Uygulama başlangıcında koleksiyonları yönet."""
    await get_client().ensure_collections()


async def shutdown_pocketbase() -> None:
    """Uygulama kapanınca temiz."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
