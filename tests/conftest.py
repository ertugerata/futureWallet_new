"""
FutureWallet pytest fixture'ları.

Her test için bağımsız bir in-memory SQLite veritabanı ve
mock edilmiş dış servisler (yfinance, ccxt, EVDS, Gemini) sağlar.
"""

from __future__ import annotations

import os as _os

# Proje kökünü sys.path'te olmak zorunda (api/app.py zaten yapıyor ama
# pytest salt tests/ dizininden çalışırken db/service importları için gerekli).
import sys
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# In-memory SQLite engine (her test fonksiyonu için sıfır oluyor)
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite:///:memory:"


def _make_test_engine() -> object:
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=False,
    )
    # SQLite için PRAGMA'lar — gerçek bağlantıda her session başı uygulanır
    # ama in-memory testlerde engine başlangıcında tek sefer yeterli.
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        conn.exec_driver_sql("PRAGMA journal_mode = WAL")
    return engine


@pytest.fixture(scope="function")
def test_engine() -> Generator[object, None, None]:
    eng = _make_test_engine()
    yield eng
    eng.dispose()


@pytest.fixture(scope="function")
def test_db(test_engine) -> Generator[Session, None, None]:
    """Bakım içi session: test başı yeni, test sonu rollback/close."""
    from db import Base

    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Uygulama fixture'ı — TestClient + mock'lar
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def mock_yfinance() -> Generator[MagicMock, None, None]:
    """yfinance.Ticker().history() → boş DataFrame döndürür (test hızlı olsun)."""
    mock = MagicMock()
    mock.Ticker = MagicMock()
    mock.Ticker.return_value.history.return_value = MagicMock(
        __class__=type("EmptyDF", (), {"empty": True})
    )
    with patch("services.benchmark_service.yfinance", mock, create=True):
        with patch("services.ledger_service.yfinance", mock, create=True):
            with patch("services.simulation_service.yfinance", mock, create=True):
                yield mock


@pytest.fixture(scope="function")
def mock_ccxt() -> Generator[MagicMock, None, None]:
    mock = MagicMock()
    mock.binance = MagicMock()
    mock.binance.return_value.fetch_ticker.return_value = {
        "last": 50000.0,
        "high": 51000.0,
        "low": 49000.0,
        "bid": 49900.0,
        "ask": 50100.0,
    }
    mock.binance.return_value.load_markets.return_value = {}
    mock.binance.return_value.timeout = 10000
    with patch("services.multi_asset_manager.ccxt", mock, create=True):
        with patch("services.ledger_service.ccxt", mock, create=True):
            with patch("services.simulation_service.ccxt", mock, create=True):
                yield mock


@pytest.fixture(scope="function")
def mock_gemini() -> Generator[MagicMock, None, None]:
    """
    google-genai / google.generativeai mock'ı.
    Varsayılan: basit metin dönüyor. Testlerde patch.setattr ile
    generate_content.side_effect = Exception(...) ile hata scenaroları testlenir.
    """
    mock_model_instance = MagicMock()
    mock_model_instance.generate_content.return_value.text = (
        "AI retrospective test çıktısı."
    )
    mock_model = MagicMock()
    mock_model.GenerativeModel.return_value = mock_model_instance

    # google.generativeai (eski SDK) ile google.genai (yeni SDK) ikisini de
    # mock'la — kod hangisini kullanırsa kullansin çalışır.
    gm = MagicMock()
    gm.configure = MagicMock()
    gm.list_models = MagicMock(return_value=[])
    gm.GenerativeModel = mock_model.GenerativeModel

    with patch("services.ai_service.genai", gm, create=True):
        with patch("services.ai_service.google_genai", gm, create=True):
            yield gm


@pytest.fixture(scope="function")
def mock_evds_failure() -> Generator[MagicMock, None, None]:
    """EVDS API'si her istekte HTTP 403/boş döner (test anahtarsız çalışsın)."""
    mock = MagicMock()
    mock.get = MagicMock(return_value=MagicMock(status_code=403, text=""))
    with patch("services.benchmark_service.requests", mock, create=True):
        yield mock


@pytest.fixture(scope="function")
def mock_pocketbase() -> Generator[MagicMock, None, None]:
    """
    PocketBase client mock — testlerde gerçek PB sunucusuna bağlanmak zorunda kalmaz.
    get_client() → MagicMock(collection(...).create/get_list/retrieve/update/delete).
    """
    mock_client = MagicMock()

    def _make_collection(name: str) -> MagicMock:
        col = MagicMock()
        col.create.return_value = {
            "id": "mock-id",
            "create_time": "2024-01-01T00:00:00Z",
        }
        col.get_list.return_value = []
        col.retrieve.return_value = None
        col.update.return_value = {"id": "mock-id"}
        col.delete.return_value = True
        return col

    mock_client.collection.side_effect = _make_collection
    mock_client.collection_exists.return_value = True

    with patch("services.pocketbase.get_client", return_value=mock_client, create=True):
        with patch(
            "services.pocketbase.PocketBaseClient",
            return_value=mock_client,
            create=True,
        ):
            yield mock_client


# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def api_client(
    test_db,
    mock_yfinance,
    mock_ccxt,
    mock_gemini,
    mock_pocketbase,
) -> Generator[TestClient, None, None]:
    """
    Tam test istemcisi: in-memory DB + tüm dış servisler mock'lanmış.
    search_params'da mock'ların scope'ı test fonksiyonu boyutunda (function)
    olduğu için her test yeni mock başlangıcı alır.
    """
    # API_TOKEN varsayılan içinde mock token ayarla — testlerde
    # gerçek token beklenmez; auth tests'i kendi fixture'larıyla mock'lar.

    # Config'u test token ile geçici olarak aş
    import config as config_mod

    _orig_token = config_mod.API_TOKEN
    _orig_origins = config_mod.ALLOWED_ORIGINS
    _orig_hosts = config_mod.ALLOWED_HOSTS
    _orig_db_url = config_mod.DATABASE_URL

    config_mod.API_TOKEN = "test-secret-token"
    config_mod.ALLOWED_ORIGINS = "http://localhost:8000"
    config_mod.ALLOWED_HOSTS = "localhost,127.0.0.1,testserver"
    config_mod.DATABASE_URL = "sqlite:///:memory:"
    from api.app import app

    with TestClient(app) as client:
        yield client

    # Config'u geri yükle
    config_mod.API_TOKEN = _orig_token
    config_mod.ALLOWED_ORIGINS = _orig_origins
    config_mod.ALLOWED_HOSTS = _orig_hosts
    # Rate limit state'ini temizle (testler arasında kalıcık önle)
    from api.app import _RETRO_RATE_LIMITS

    _RETRO_RATE_LIMITS.clear()
