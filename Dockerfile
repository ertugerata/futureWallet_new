# =============================================================================
# FutureWallet - İki Aşamalı Dockerfile
# =============================================================================
# Aşama 1 (builder): Python bağımlılıklarını kurar
# Aşama 2 (runtime): Sadece gerekli dosyaları ve bağımlılıkları kopyalar
# =============================================================================

# -----------------------------------------------------------------------------
# Aşama 1: Bağımlılıkları Kur (Builder)
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Sistem bağımlılıkları (çoğu paket için gerekli)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Çalışma dizini
WORKDIR /app

# Gereksinimleri önce kopyala (katman önbelleği için)
COPY requirements.txt .

# Python paketlerini kur
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Aşama 2: Çalışma Imagı (Runtime)
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Çalışma dizini
WORKDIR /app

# Sistem bağımlılıkları (SQLite ve zaman dilimi gereksinimleri için)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Builder aşamasından Python paketlerini kopyala
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Uygulama kodunu kopyala
COPY . .

# .env.example varsayılan olarak kopyalanır (kullanıcı kendi .env dosyasını
# sağlamalı veya environment variable'lar ile geçemeli)
COPY .env.example .env

# Uygulama portu
EXPOSE 8000

# Etiket (opsiyonel, bilgi amaçlı)
LABEL maintainer="ertugerata"
LABEL description="FutureWallet - Akıllı Portföy ve Karar Günlüğü Sistemi"

# Uygulamanın başlatılması (uvicorn ile FastAPI sunucusu)
# APP_HOST ve APP_PORT environment variable'ları üzerinden yapılandırılabilir
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
