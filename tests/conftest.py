"""
Test fixtures for FutureWallet using a real PocketBase instance.
The fixtures start a PocketBase binary (downloaded if missing), provide
clean-up of collections, create test users, and expose a FastAPI TestClient.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Setup test environment variables before importing app/config
# ---------------------------------------------------------------------------

DEFAULT_PORT = 8090
os.environ["POCKETBASE_EMAIL"] = "test_admin@futurewallet.test"
os.environ["POCKETBASE_PASSWORD"] = "TestPass123!@Pass"
os.environ["POCKETBASE_URL"] = f"http://127.0.0.1:{DEFAULT_PORT}"
os.environ["API_TOKEN"] = "test-secret-token"
os.environ["DEBUG"] = "true"
os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:8000"

import config
from services.pb import delete_record, get_admin_client, get_user_client, list_all

config.POCKETBASE_EMAIL = os.environ["POCKETBASE_EMAIL"]
config.POCKETBASE_PASSWORD = os.environ["POCKETBASE_PASSWORD"]
config.POCKETBASE_URL = os.environ["POCKETBASE_URL"]
config.API_TOKEN = os.environ["API_TOKEN"]
config.DEBUG = True
config.ALLOWED_HOSTS = os.environ["ALLOWED_HOSTS"]
config.ALLOWED_ORIGINS = os.environ["ALLOWED_ORIGINS"]

# ---------------------------------------------------------------------------
# PocketBase binary handling (Prompt 2)
# ---------------------------------------------------------------------------

POCKETBASE_VERSION = "0.40.6"
PB_BINARY = Path("./pb_bin/pocketbase")
PB_TEST_DIR = Path("./pb_test_data")


def _download_pocketbase() -> None:
    """Download and unzip the PocketBase binary for the current platform."""
    if PB_BINARY.is_file():
        return
    platform = sys.platform
    arch = "amd64" if sys.maxsize > 2**32 else "386"
    if platform.startswith("linux"):
        plat = "linux"
    elif platform == "darwin":
        plat = "darwin"
    elif platform.startswith("win"):
        plat = "windows"
    else:
        raise RuntimeError(f"Unsupported platform: {platform}")

    url = f"https://github.com/pocketbase/pocketbase/releases/download/v{POCKETBASE_VERSION}/pocketbase_{POCKETBASE_VERSION}_{plat}_{arch}.zip"
    import io
    import zipfile

    PB_BINARY.parent.mkdir(parents=True, exist_ok=True)
    zip_bytes = urllib.request.urlopen(url).read()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        z.extractall(PB_BINARY.parent)
    PB_BINARY.chmod(0o755)


def _start_pocketbase() -> subprocess.Popen:
    """Start PocketBase as a subprocess."""
    _download_pocketbase()
    PB_TEST_DIR.mkdir(parents=True, exist_ok=True)

    admin_email = config.POCKETBASE_EMAIL
    admin_password = config.POCKETBASE_PASSWORD

    # Upsert superuser first so admin credentials always exist
    subprocess.run(
        [
            str(PB_BINARY),
            "superuser",
            "upsert",
            admin_email,
            admin_password,
            f"--dir={PB_TEST_DIR}",
            "--migrationsDir=./pb_migrations",
        ],
        check=True,
    )

    proc = subprocess.Popen(
        [
            str(PB_BINARY),
            "serve",
            f"--http=127.0.0.1:{DEFAULT_PORT}",
            f"--dir={PB_TEST_DIR}",
            "--migrationsDir=./pb_migrations",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    timeout = 20
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            raise RuntimeError(f"PocketBase failed to start with returncode {proc.returncode}")
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{DEFAULT_PORT}/api/health", timeout=1
            ) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.2)
    else:
        proc.terminate()
        raise RuntimeError("PocketBase did not become ready in time")
    return proc


@pytest.fixture(scope="session")
def pb_server() -> Generator[None, None, None]:
    """Start a PocketBase server for the entire test session."""
    proc = _start_pocketbase()
    try:
        yield
    finally:
        proc.terminate()
        proc.wait()
        if PB_TEST_DIR.exists():
            shutil.rmtree(PB_TEST_DIR, ignore_errors=True)


REQUIRED_COLLECTIONS = (
    "transactions",
    "decisions",
    "shadow_portfolios",
    "macro_data",
    "price_history",
)


@pytest.fixture
def pb_admin(pb_server):
    """Superuser client fixture."""
    return get_admin_client()


@pytest.fixture(autouse=True)
def pb_clean(pb_server) -> None:
    """Delete all records from each required collection before each test."""
    from api.app import _RETRO_RATE_LIMITS

    _RETRO_RATE_LIMITS.clear()

    client = get_admin_client()
    for col_name in REQUIRED_COLLECTIONS:
        try:
            col = client.collection(col_name)
            for rec in list_all(col):
                delete_record(col, rec.id)
        except Exception:
            pass


@pytest.fixture
def test_db(pb_clean):
    """Compatibility fixture for tests expecting test_db."""
    return pb_clean


@pytest.fixture(scope="session")
def make_user(pb_server):
    """Callable fixture to create a test user and return (user_id, token, user_client)."""
    created_user_ids: list[str] = []

    def _maker(email: str = "test_user@futurewallet.test", password: str = "TestPass123!@Pass"):
        client = get_admin_client()
        existing = client.collection("users").get_full_list(
            query_params={"filter": f'email = "{email}"'}
        )
        if existing:
            user = existing[0]
        else:
            user = client.collection("users").create(
                {"email": email, "password": password, "passwordConfirm": password}
            )
        created_user_ids.append(str(user.id))

        user_client = get_user_client("")
        auth = user_client.collection("users").auth_with_password(email, password)
        token = auth.token
        return str(user.id), token, user_client

    yield _maker

    client = get_admin_client()
    for uid in created_user_ids:
        try:
            client.collection("users").delete(uid)
        except Exception:
            pass


@pytest.fixture
def api_client(pb_server) -> TestClient:
    """FastAPI TestClient without default auth headers."""
    from api.app import app

    return TestClient(app)
