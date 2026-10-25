"""
FutureWallet - Uygulama Yapılandırması

Tüm hassas değerler (API key'ler, DB URL'si) `.env` dosyasından okunur.
"""

from os import environ
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Google Gemini AI
# ---------------------------------------------------------------------------
GOOGLE_API_KEY: str = environ.get("GOOGLE_API_KEY", "")
# Boşsa AI servisler 503 döner (api/app.py'deki pattern)


# ---------------------------------------------------------------------------
# Veritabanı
# ---------------------------------------------------------------------------
DB_URL: str = environ.get("DATABASE_URL", "sqlite:///futurewallet.db")


# ---------------------------------------------------------------------------
# Piyasa veri API'leri (benchmark_service için)
# ---------------------------------------------------------------------------
TCMB_API_KEY: str = environ.get("TCMB_API_KEY", "")     # EVDS API (varsa)
FRED_API_KEY: str = environ.get("FRED_API_KEY", "")     # US CPI için FRED (varsa)


# ---------------------------------------------------------------------------
# Uygulama
# ---------------------------------------------------------------------------
DEBUG: bool = environ.get("DEBUG", "false").lower() == "true"
APP_HOST: str = environ.get("APP_HOST", "0.0.0.0")
APP_PORT: int = int(environ.get("APP_PORT", "8000"))
