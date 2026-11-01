"""
FutureWallet - Uygulama Yapılandırması

Tüm hassas değerler (API key'ler, DB URL'si) `.env` dosyasından okunur.
.env.example dosyası for documented varsayılanlar ve açıklamalar.

Prompt 1 (Auth), Prompt 7 (AI), Prompt 6 (DB) düzeltmeleri ile
senkronize edilmiştir.
"""

from os import environ
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Kimlik Doğrulama (Prompt 1)
# ---------------------------------------------------------------------------

# API_TOKEN: FutureWallet API'sine erişim token'ı.
#   - Authorization: Bearer <token> ile gönderilir.
#   - Boş ve DEBUG=false → uygulama başlamaz (fail-closed, Prompt 1).
API_TOKEN: str = environ.get("API_TOKEN", "")

# ALLOWED_ORIGINS: CORS'da izin verilen origin'ler (virgülle ayrılmış).
#   - Boş → CORS middleware eklenmez (yalnızca same-origin).
ALLOWED_ORIGINS: str = environ.get("ALLOWED_ORIGINS", "")

# ALLOWED_HOSTS: TrustedHostMiddleware için izin verilen Host değerleri.
#   - Boş → middleware eklenmez.
ALLOWED_HOSTS: str = environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1")


# ---------------------------------------------------------------------------
# Veritabanı (Prompt 6)
# ---------------------------------------------------------------------------

# DATABASE_URL: SQLAlchemy/DB URL'si.
#   - Varsayılan: ./data/futurewallet.db (SQLite; Docker kalıcılıkla).
#   - config.py'deki DB_URL → db.py tarafından kullanılır.
DATABASE_URL: str = environ.get("DATABASE_URL", "sqlite:///./data/futurewallet.db")


# ---------------------------------------------------------------------------
# Google Gemini / OpenRouter AI (Prompt 7)
# ---------------------------------------------------------------------------

# GOOGLE_API_KEY: Gemini/OpenRouter API anahtarı.
#   - Boşsa AI servisler 503 döner (api/app.py'deki pattern).
#   - Prompt 7: google-generativeai → google-genai SDK'sına geçildi.
GOOGLE_API_KEY: str = environ.get("GOOGLE_API_KEY", "")

# GEMINI_MODEL: LLM model adı (config'ten okunur, kodda SABİT DEĞİL).
#   - Prompt 7: "gemini-1.5-flash" sabiti kaldırıldı.
#   - OpenRouter model naming conventionına uygun.
GEMINI_MODEL: str = environ.get("GEMINI_MODEL", "google/gemini-2.0-flash")


# ---------------------------------------------------------------------------
# Piyasa Veri API'leri (benchmark_service için)
# ---------------------------------------------------------------------------

# TCMB_API_KEY: TCMB EVDS API anahtarı (TÜFE verisi).
#   - Yoksa TÜFE için "veri yok" döner; uydurma veri üretilmez (Prompt 11).
TCMB_API_KEY: str = environ.get("TCMB_API_KEY", "")

# FRED_API_KEY: US CPI verisi için FRED API anahtarı.
#   - Yoksa US CPI için fallback yok (Prompt 11: sentetik fallback kaldırıldı).
FRED_API_KEY: str = environ.get("FRED_API_KEY", "")


# ---------------------------------------------------------------------------
# Uygulama
# ---------------------------------------------------------------------------

# DEBUG: true|false. Production'da false olmalı.
DEBUG: bool = environ.get("DEBUG", "false").lower() == "true"

# APP_HOST: FastAPI bind adresi.
#   - Varsayılan 127.0.0.1 (Prompt 1: 0.0.0.0 kaldırıldı — bind'a dikkat).
#   - Docker'da reverse proxy ile exposure yapılmalı.
APP_HOST: str = environ.get("APP_HOST", "127.0.0.1")

# APP_PORT: FastAPI portu. Varsayılan 8000.
APP_PORT: int = int(environ.get("APP_PORT", "8000"))
