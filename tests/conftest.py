"""
FutureWallet pytest fixture'ları (Prompt 2).

Gerçek PocketBase (v0.40.6) binary'si ile test altyapısı sağlar.
SQLite / SQLAlchemy bağımlılıkları kaldırılmıştır.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pocketbase import PocketBase

# Proje kökünü sys.path'e ekle
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

PB_VERSION = "0.40.6"
PB_SHA256 = "0e1f609158ed945f809f8a02ae012aa0427129c66ebb63c1aee76f2c0309373f"
PB_DOWNLOAD_URL = (
    f"https://github.com/pocketbase/pocketbase/releases/download/"
    f"v{PB_VERSION}/pocketbase_{PB_VERSION}_linux_amd64.zip"
)


def _get_free_port() -> int:
    """Boş bir yerel TCP portu bulur."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _ensure_pb_binary() -> str:
    """PocketBase v0.40.6 binary'sini indirir, checksum doğrular ve yolunu döner."""
    cache_dir = os.path.join(_PROJECT_ROOT, ".pb_cache")
    os.makedirs(cache_dir, exist_ok=True)
    bin_path = os.path.join(cache_dir, "pocketbase")

    if os.path.exists(bin_path) and os.access(bin_path, os.X_OK):
        return bin_path

    zip_path = os.path.join(cache_dir, f"pocketbase_{PB_VERSION}.zip")
    if not os.path.exists(zip_path):
        urllib.request.urlretrieve(PB_DOWNLOAD_URL, zip_path)

    # Checksum doğrula
    sha256 = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    actual_hash = sha256.hexdigest()
    if actual_hash != PB_SHA256:
        os.remove(zip_path)
        raise RuntimeError(
            f"PocketBase binary checksum uyuşmazlığı! Beklenen: {PB_SHA256}, Alınan: {actual_hash}"
        )

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extract("pocketbase", cache_dir)

    os.chmod(bin_path, 0o755)
    return bin_path


# ---------------------------------------------------------------------------
# Gerçek PocketBase Server Fixture (Session Scope)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pb_server() -> Generator[dict[str, str], None, None]:
    """
    Test session süresince çalışan gerçek PocketBase v0.40.6 sunucusu.
    """
    try:
        bin_path = _ensure_pb_binary()
    except Exception as exc:
        pytest.skip(f"PocketBase v0.40.6 temin edilemedi ({exc}). PB testleri atlandı.")

    pb_dir = tempfile.mkdtemp(prefix="pb_test_server_")
    port = _get_free_port()
    migrations_dir = os.path.join(_PROJECT_ROOT, "pb_migrations")

    admin_email = "test_admin@futurewallet.test"
    admin_password = "Passw0rd!Passw0rd"

    # Superuser oluştur
    subprocess.run(
        [
            bin_path,
            "superuser",
            "upsert",
            admin_email,
            admin_password,
            "--dir",
            pb_dir,
        ],
        check=True,
        capture_output=True,
    )

    # Sunucuyu başlat
    cmd = [
        bin_path,
        "serve",
        "--dir",
        pb_dir,
        "--migrationsDir",
        migrations_dir,
        "--http",
        f"127.0.0.1:{port}",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    base_url = f"http://127.0.0.1:{port}"

    # /api/health hazır olana kadar bekle (max 15 sn)
    start_time = time.time()
    ready = False
    while time.time() - start_time < 15:
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=1) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.1)

    if not ready:
        proc.terminate()
        proc.wait()
        shutil.rmtree(pb_dir, ignore_errors=True)
        pytest.fail("PocketBase test sunucusu 15 saniye içinde hazır olamadı.")

    server_info = {
        "url": base_url,
        "admin_email": admin_email,
        "admin_password": admin_password,
        "dir": pb_dir,
    }

    try:
        yield server_info
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(pb_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def pb_admin(pb_server: dict[str, str]) -> PocketBase:
    """Superuser yetkilerine sahip PocketBase istemcisi."""
    pb = PocketBase(pb_server["url"])
    pb.collection("_superusers").auth_with_password(
        pb_server["admin_email"], pb_server["admin_password"]
    )
    return pb


@pytest.fixture(scope="function")
def pb_clean(pb_admin: PocketBase) -> Generator[None, None, None]:
    """Her test öncesi/sonrası kullanıcı koleksiyonlarını temizler."""

    def _clean() -> None:
        for col_name in ["shadow_portfolios", "decisions", "transactions", "macro_data", "price_history"]:
            try:
                records = pb_admin.collection(col_name).get_full_list()
                for r in records:
                    pb_admin.collection(col_name).delete(r.id)
            except Exception:
                pass

        # Normal test kullanıcılarını temizle (default test kullanıcısı hariç)
        try:
            users = pb_admin.collection("users").get_full_list()
            for u in users:
                if getattr(u, "email", "") != "test_default@futurewallet.test":
                    pb_admin.collection("users").delete(u.id)
        except Exception:
            pass

    _clean()
    yield
    _clean()


@pytest.fixture(scope="function")
def make_user(pb_admin: PocketBase, pb_server: dict[str, str]):
    """Test kullanıcısı oluşturan ve (user_id, token, user_client) dönen fabrika."""

    def _factory(email: str = "user@test.local", password: str = "TestPass123!"):
        user_record = pb_admin.collection("users").create(
            {
                "email": email,
                "password": password,
                "passwordConfirm": password,
            }
        )
        user_client = PocketBase(pb_server["url"])
        auth_data = user_client.collection("users").auth_with_password(email, password)
        return user_record.id, auth_data.token, user_client

    return _factory


# ---------------------------------------------------------------------------
# Geriye Dönük Uyumluluk için Dummy DB Fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def test_db():
    """Eski testlerdeki test_db argümanını karşılamak için dummy fixture."""
    return None


# ---------------------------------------------------------------------------
# Dış Servis Mock'ları
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def mock_yfinance() -> Generator[MagicMock, None, None]:
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
    mock_model_instance = MagicMock()
    mock_model_instance.generate_content.return_value.text = "AI retrospective test çıktısı."
    mock_model = MagicMock()
    mock_model.GenerativeModel.return_value = mock_model_instance

    gm = MagicMock()
    gm.configure = MagicMock()
    gm.list_models = MagicMock(return_value=[])
    gm.GenerativeModel = mock_model.GenerativeModel

    with patch("services.ai_service.genai", gm, create=True):
        with patch("services.ai_service.google_genai", gm, create=True):
            yield gm


@pytest.fixture(scope="function")
def mock_evds_failure() -> Generator[MagicMock, None, None]:
    mock = MagicMock()
    mock.get = MagicMock(return_value=MagicMock(status_code=403, text=""))
    with patch("services.benchmark_service.requests", mock, create=True):
        yield mock


# ---------------------------------------------------------------------------
# FastAPI TestClient Fixture (Gerçek PocketBase ile Entegre)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def api_client(
    pb_server: dict[str, str],
    mock_yfinance,
    mock_ccxt,
    mock_gemini,
) -> Generator[TestClient, None, None]:
    """Gerçek PocketBase sunucusuna bağlı FastAPI TestClient."""
    import config as config_mod

    orig_pb_url = config_mod.POCKETBASE_URL
    orig_pb_email = config_mod.POCKETBASE_EMAIL
    orig_pb_pass = config_mod.POCKETBASE_PASSWORD
    orig_token = config_mod.API_TOKEN
    orig_origins = config_mod.ALLOWED_ORIGINS
    orig_hosts = config_mod.ALLOWED_HOSTS

    config_mod.POCKETBASE_URL = pb_server["url"]
    config_mod.POCKETBASE_EMAIL = pb_server["admin_email"]
    config_mod.POCKETBASE_PASSWORD = pb_server["admin_password"]
    config_mod.API_TOKEN = "test-secret-token"
    config_mod.ALLOWED_ORIGINS = "http://localhost:8000"
    config_mod.ALLOWED_HOSTS = "localhost,127.0.0.1,testserver"

    # services.pb'deki singleton'ı sıfırla
    import services.pb as pb_mod
    pb_mod._admin_client = None

    from api.app import app

    with TestClient(app) as client:
        yield client

    config_mod.POCKETBASE_URL = orig_pb_url
    config_mod.POCKETBASE_EMAIL = orig_pb_email
    config_mod.POCKETBASE_PASSWORD = orig_pb_pass
    config_mod.API_TOKEN = orig_token
    config_mod.ALLOWED_ORIGINS = orig_origins
    config_mod.ALLOWED_HOSTS = orig_hosts

    pb_mod._admin_client = None

    from api.app import _RETRO_RATE_LIMITS

    _RETRO_RATE_LIMITS.clear()
