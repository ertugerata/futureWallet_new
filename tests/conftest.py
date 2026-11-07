"""
Test fixtures for FutureWallet using a real PocketBase instance.
The fixtures start a PocketBase binary (downloaded if missing), provide
clean‑up of collections, create test users, and expose a FastAPI TestClient.
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Generator, Tuple

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# PocketBase binary handling (Prompt 2)
# ---------------------------------------------------------------------------

POCKETBASE_VERSION = "0.40.6"
POCKETBASE_URL = f"https://github.com/pocketbase/pocketbase/releases/download/v{POCKETBASE_VERSION}/pocketbase_{{platform}}_{{arch}}.zip"
DEFAULT_PORT = 8090
PB_BINARY = Path("./pb_bin/pocketbase")

def _download_pocketbase() -> None:
    """Download and unzip the PocketBase binary for the current platform.
    The binary is stored under ``pb_bin/`` relative to the repository root.
    """
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

    url = POCKETBASE_URL.format(platform=plat, arch=arch)
    import io
    import urllib.request
    import zipfile

    zip_bytes = urllib.request.urlopen(url).read()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        z.extractall(PB_BINARY.parent)
    # Ensure executable permission on *nix
    PB_BINARY.chmod(0o755)

def _start_pocketbase() -> subprocess.Popen:
    """Start PocketBase as a subprocess.
    Returns the Popen object; the caller is responsible for termination.
    """
    _download_pocketbase()
    # Create a temporary directory for data storage
    data_dir = Path("./pb_data")
    data_dir.mkdir(exist_ok=True)
    proc = subprocess.Popen(
        [str(PB_BINARY), "serve", f"--http=0.0.0.0:{DEFAULT_PORT}", f"--dir={data_dir}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # Wait a few seconds for the server to be ready
    timeout = 20
    start = time.time()
    while time.time() - start < timeout:
        line = proc.stdout.readline()
        if "Server started" in line:
            break
        if proc.poll() is not None:
            raise RuntimeError("PocketBase failed to start")
    else:
        proc.terminate()
        raise RuntimeError("PocketBase did not become ready in time")
    return proc

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pb_server() -> Generator[None, None, None]:
    """Start a PocketBase server for the entire test session.
    The server is stopped after all tests have run.
    """
    proc = _start_pocketbase()
    try:
        yield
    finally:
        proc.terminate()
        proc.wait()

from services.pb import delete_record, get_admin_client, list_all

REQUIRED_COLLECTIONS = (
    "transactions",
    "decisions",
    "shadow_portfolios",
    "macro_data",
    "price_history",
)

@pytest.fixture(autouse=True)
def pb_clean(pb_server) -> None:
    """Delete all records from each required collection before each test.
    This ensures isolation between test cases.
    """
    client = get_admin_client()
    for col_name in REQUIRED_COLLECTIONS:
        col = client.collection(col_name)
        for rec in list_all(col):
            delete_record(col, rec.id)

@pytest.fixture(scope="session")
def make_user() -> Generator[Tuple[str, str], None, None]:
    """Create a test user and return ``(user_id, jwt)``.
    The user is created once per session; the JWT is obtained via
    ``auth_with_password`` and refreshed automatically by the client.
    """
    client = get_admin_client()
    email = "test_user@futurewallet.test"
    password = "TestPass123!@Pass"
    # Ensure user exists
    existing = client.collection("users").get_full_list(query_params={"filter": f"email = '{email}'"})
    if existing:
        user = existing[0]
    else:
        user = client.collection("users").create({"email": email, "password": password, "passwordConfirm": password})
    # Authenticate to obtain JWT
    auth = client.collection("users").auth_with_password(email, password)
    token = auth.token
    yield (str(user.id), token)
    # Cleanup: delete the user after the session
    client.collection("users").delete(user.id)

@pytest.fixture
def api_client(make_user) -> TestClient:
    """FastAPI TestClient that injects the test user's JWT into the
    ``Authorization`` header for each request.
    """
    from api.app import app
    user_id, token = make_user
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
