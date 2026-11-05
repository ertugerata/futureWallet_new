"""
Alembic migration ortamı — FutureWallet.

Uygulama başlangıcında `alembic upgrade head` çalıştırılır
(geliştirme_modunda create_all ile fall-back imkanı var).

DATABASE_URL env değişkeni kullanılmazsa varsayılan:
    sqlite:///./data/futurewallet.db
"""

from __future__ import annotations

import logging
import os

# Bu dosyanın bulunduğu dizin (alembic/) — buradan bir üst seviyeye çık
# ve proje köküne sys.path eklenir (db, config importları için).
import sys
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

_ALEMBIC_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _ALEMBIC_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from db import Base

# ---------------------------------------------------------------------------
# Loglama
# ---------------------------------------------------------------------------
logger = logging.getLogger("alembic")

# ---------------------------------------------------------------------------
# Migration Context Configuration
# ---------------------------------------------------------------------------

# Bu fonksiyon, alembic.ini'deki [alembic] bölümünü okur.
# sqlalchemy.url placeholder; env.py → os.environ.get("DATABASE_URL", ...) ile
# geçerli değeri ayarlar.
config = context.config

# Bu projedeki modeller (-> autogenerate için gerekli)
# Base.metadata'ı context.metadata'ya ata.
target_metadata = Base.metadata


def get_database_url() -> str:
    """DATABASE_URL env değişkeni yoksa varsayılan sqlite path."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    # Development varsayılanı — kalıcı SQLite (Prompt 6)
    data_dir = _PROJECT_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{data_dir / 'futurewallet.db'}"


def run_migrations_offline() -> None:
    """
    'offline' mod: sadece SQL script'i üretir, DB bağlantısı açmaz.
    alembic --offline veya --sql kullanımında çalışır.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    'online' mod: gerçek DB bağlantısı açar, migration'ları uygular.
    """
    # Config'deki URL'yi env'den gelen gerçek URL ile override et.
    # Alembic config ensuite sqlalchemy.url'ı bularak engine oluşturur.
    config.set_main_option("sqlalchemy.url", get_database_url())

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite ALTER TABLE için gerekli
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
