"""
PocketBase İstemci Katmanı (Prompt 5)
======================================
PocketBase Python SDK (v0.17.3) senkron istemci sarmalayıcısı.

Fonksiyonlar:
  - get_admin_client(): Arka plan ve admin işlemleri için superuser istemcisi (thread-safe, auto-refresh).
  - get_user_client(token): İstek bazlı, kullanıcı JWT'si ile yetkilendirilmiş istemci.
  - CRUD yardımcıları: list_all, get_one, create_record, update_record, delete_record.
  - verify_collections(): Gerekli koleksiyonların varlığını doğrular.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from pocketbase import PocketBase
from pocketbase.models.record import Record

import config

logger = logging.getLogger(__name__)

_admin_lock = threading.Lock()
_admin_client: PocketBase | None = None

REQUIRED_COLLECTIONS = (
    "transactions",
    "decisions",
    "shadow_portfolios",
    "macro_data",
    "price_history",
)


def get_admin_client() -> PocketBase:
    """Superuser istemcisi (thread-safe singleton, otomatik token yenileme)."""
    global _admin_client
    with _admin_lock:
        if _admin_client is None or _admin_client.base_url != config.POCKETBASE_URL:
            _admin_client = PocketBase(config.POCKETBASE_URL)

        if not _admin_client.auth_store.is_valid:
            try:
                # PB v0.40.6'da superuser auth _superusers koleksiyonu üzerinden yapılır
                _admin_client.collection("_superusers").auth_with_password(
                    config.POCKETBASE_EMAIL, config.POCKETBASE_PASSWORD
                )
            except Exception as exc:
                logger.error("PocketBase superuser kimlik doğrulaması başarısız: %s", exc)
                raise
        return _admin_client


# Geriye dönük uyumluluk için alias
get_client = get_admin_client


def get_user_client(token: str) -> PocketBase:
    """Belirli bir kullanıcının JWT token'ı ile yetkilendirilmiş PocketBase istemcisi."""
    client = PocketBase(config.POCKETBASE_URL)
    if token:
        # PB auth header formatı için token kaydedilir
        client.auth_store.save(token, None)
    return client


def list_all(
    col: Any,
    filter_expr: str | None = None,
    sort: str | None = None,
    expand: str | None = None,
) -> list[Record]:
    """Koleksiyondaki tüm kayıtları çeker (sayfalamayı otomatik halleder)."""
    query_params: dict[str, Any] = {}
    if filter_expr:
        query_params["filter"] = filter_expr
    if sort:
        query_params["sort"] = sort
    if expand:
        query_params["expand"] = expand

    return col.get_full_list(batch=200, query_params=query_params)


def get_one(col: Any, record_id: str, expand: str | None = None) -> Record:
    """Tekil kayıt çeker."""
    query_params: dict[str, Any] = {}
    if expand:
        query_params["expand"] = expand
    return col.get_one(record_id, query_params=query_params)


def create_record(col: Any, body: dict[str, Any]) -> Record:
    """Kayıt oluşturur."""
    return col.create(body)


def update_record(col: Any, record_id: str, body: dict[str, Any]) -> Record:
    """Kayıt günceller."""
    return col.update(record_id, body)


def delete_record(col: Any, record_id: str) -> bool:
    """Kayıt siler."""
    return bool(col.delete(record_id))


def verify_collections(client: PocketBase | None = None) -> bool:
    """Uygulama açılışında gerekli koleksiyonların varlığını doğrular."""
    if client is None:
        client = get_admin_client()

    try:
        collections = client.collections.get_full_list()
        existing_names = {c.name for c in collections}
        missing = [c for c in REQUIRED_COLLECTIONS if c not in existing_names]
        if missing:
            raise RuntimeError(
                f"PocketBase koleksiyonları eksik: {missing}. "
                "Lütfen pb_migrations dizinindeki migration'ları uygulayın."
            )
        return True
    except Exception as exc:
        logger.error("Koleksiyon doğrulama hatası: %s", exc)
        raise
