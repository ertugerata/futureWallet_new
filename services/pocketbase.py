"""
services.pocketbase (Eski modül -> services.pb yönlendiricisi)
==============================================================
Prompt 3 & 5: Schema yönetimi pb_migrations/ ile PocketBase'e devredilmiştir.
Tüm PB işlemleri services.pb üzerinden yapılır.
"""

from __future__ import annotations

from typing import Any

from services.pb import (
    create_record,
    delete_record,
    get_admin_client,
    get_client,
    get_one,
    get_user_client,
    list_all,
    update_record,
    verify_collections,
)

__all__ = [
    "create_record",
    "delete_record",
    "get_admin_client",
    "get_client",
    "get_one",
    "get_user_client",
    "init_pocketbase_collections",
    "list_all",
    "shutdown_pocketbase",
    "update_record",
    "verify_collections",
]


async def init_pocketbase_collections() -> bool:
    """Açılışta koleksiyonları doğrular."""
    try:
        return verify_collections()
    except Exception:
        return False


async def shutdown_pocketbase() -> None:
    """Temizlik (gerekirse)."""
    pass
