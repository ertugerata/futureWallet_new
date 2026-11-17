"""
FutureWallet – Uygulama Yapılandırması

Tüm hassas değerler (API key'ler, PB URL'si, DB URL'si) `.env` dosyasından okunur.
.env.example dosyası: dokumente varsayılanlar ve açıklamalar.

Prompt 1 (Auth/CORS/Host), Prompt 2 (XSS/CSP), Prompt 6 (DB/PocketBase),
Prompt 7 (AI/SDK geçiş) düzeltmeleri ile senkronize edilmiştir.
"""

from os import environ

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Kimlik Doğrulama / CORS (Prompt 1, 6)
# ---------------------------------------------------------------------------

# Kimlik doğrulama PB JWT iledir (Authorization: Bearer <PB_JWT>) — statik token yok.
# ALLOWED_ORIGINS: CORS'da izin verilen origin'ler (virgülle ayrılmış).
#   - Boş → CORS middleware eklenmez (yalnızca same-origin).
ALLOWED_ORIGINS: str = environ.get("ALLOWED_ORIGINS", "")

# ALLOWED_HOSTS: TrustedHostMiddleware için izin verilen Host değerleri.
#   - Boş → middleware eklenmez.
ALLOWED_HOSTS: str = environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1")


# ---------------------------------------------------------------------------
# PocketBase (Sprint 1.2 – PB geçişi)
# ---------------------------------------------------------------------------

# POCKETBASE_URL: PocketBase instance URL'si.
#   - Varsayılan: localhost:8080 (local); Docker içinde http://pocketbase:8090.
POCKETBASE_URL: str = environ.get("POCKETBASE_URL", "http://localhost:8080")

# POCKETBASE_PUBLIC_URL: tarayıcının (host'tan) eriştiği aynı PB adresi.
#   - Boşsa POCKETBASE_URL ile aynı varsayılır (tek-host kurulum).
#   - Docker Compose'ta POCKETBASE_URL ağ-internal (http://pocketbase:8090) olduğu
#     için login fetch'i ve CSP connect-src bu harici adresi kullanmak zorundadır.
POCKETBASE_PUBLIC_URL: str = environ.get("POCKETBASE_PUBLIC_URL", "")


def pb_browser_url() -> str:
    """Tarayıcı tarafı PB base'i (pb_base template + CSP connect-src)."""
    return POCKETBASE_PUBLIC_URL or POCKETBASE_URL

# POCKETBASE_EMAIL / POCKETBASE_PASSWORD: PB admin credential'ı (kollek. yönetim).
# PB admin credentials – must be provided via environment (no defaults).
_raw_email = environ.get("POCKETBASE_EMAIL")
if not _raw_email:
    raise RuntimeError("POCKETBASE_EMAIL environment variable is required")
POCKETBASE_EMAIL: str = _raw_email

_raw_password = environ.get("POCKETBASE_PASSWORD")
if not _raw_password:
    raise RuntimeError("POCKETBASE_PASSWORD environment variable is required")
POCKETBASE_PASSWORD: str = _raw_password


# ---------------------------------------------------------------------------
# OpenRouter AI (Prompt 8 – Multi-model fallback)
# ---------------------------------------------------------------------------

OPENROUTER_API_KEY: str = environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODELS: str = environ.get(
    "OPENROUTER_MODELS",
    "anthropic/claude-3.5-sonnet,google/gemini-2.0-flash-001,deepseek/deepseek-r1",
)

# ---------------------------------------------------------------------------
# Zamanlayıcı (APScheduler - Prompt 11, 13)
# ---------------------------------------------------------------------------

ENABLE_SCHEDULER: bool = environ.get("ENABLE_SCHEDULER", "true").lower() == "true"


# ---------------------------------------------------------------------------
# Piyasa Veri API'leri (benchmark_service için)
# ---------------------------------------------------------------------------

# TCMB_API_KEY: TCMB EVDS API anahtarı (TÜFE verisi, Prompt 11).
#   - Yoksa TÜFE için açıkça "veri yok" döner; uydurma veri üretilmez.
TCMB_API_KEY: str = environ.get("TCMB_API_KEY", "")

# FRED_API_KEY: US CPI verisi için FRED API anahtarı (Prompt 11).
#   - Yoksa US CPI için fallback yok.
FRED_API_KEY: str = environ.get("FRED_API_KEY", "")


# ---------------------------------------------------------------------------
# Uygulama
# ---------------------------------------------------------------------------

# DEBUG: true|false. Production'da false olmalı.
DEBUG: bool = environ.get("DEBUG", "false").lower() == "true"

# APP_HOST: FastAPI bind adresi.
#   - Varsayılan 127.0.0.1 (Prompt 1: 0.0.0.0 kaldırıldı — bind'a dikkat).
APP_HOST: str = environ.get("APP_HOST", "127.0.0.1")

# APP_PORT: FastAPI portu. Varsayılan 8000.
APP_PORT: int = int(environ.get("APP_PORT", "8000"))
