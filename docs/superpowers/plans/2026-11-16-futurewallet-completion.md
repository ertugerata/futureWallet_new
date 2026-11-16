# FutureWallet Tamamlama & Düzeltme Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FutureWallet MVP v2/v3 mimarisine (PocketBase v0.40.6 + FastAPI + OpenRouter) tam uyum sağlayacak şekilde açık kalan tüm Prompt maddelerini (P4–P15) tamamlamak, test etmek ve dokümanları senkronize etmek.

**Architecture:** PocketBase (Auth + SQLite DB) arka uç veritabanı olarak çalışır; FastAPI hesaplama, zaman yolculuğu ve stres testlerini yürütür; OpenRouter (Claude/Gemini/DeepSeek fallback) karar retrospektifi ve AI risk anlatısı sunar; APScheduler periyodik makro veri çekimini ve vadesi dolan kararların EXPIRED yapılmasını yönetir.

**Tech Stack:** Python 3.11, FastAPI, PocketBase Python SDK 0.17.3, Pydantic v2, APScheduler, httpx, yfinance, ccxt, NumPy, Pandas, pytest.

**Spec:** `MVP.md`, `TODO.md`, `GUNCEL_IS_PLANI.md`, `FUTUREWALLET_DUZELTME_PROMPTLARI.md`

## Global Constraints

- Python bağımlılık ve paket yönetiminde daima `uv` kullanılmalıdır (`./bin/uv pip ...`).
- PocketBase SDK senkrondur: `get_full_list(...)`, `get_one(id)`, `create(body)`, `update(id, body)`, `delete(id)`.
- PB filtrelerinde f-string yerine `client.filter(raw, params)` kullanılmalıdır.
- Sır/anahtar kod içerisine sabit yazılmamalı, daima `config.py` üzerinden ortam değişkenlerinden okunmalıdır.
- Her adım sonunda `pytest tests/` çalıştırılarak regresyon oluşmadığı doğrulanmalıdır.

---

## Tasks

### Task 1: Depo Kalıntılarını Temizleme & Kod Tekrarlarını Giderme (P15)

**Files:**
- Create: `services/asset_types.py`
- Modify: `services/ledger_service.py`
- Modify: `services/decision_service.py`
- Modify: `api/app.py`
- Modify: `services/counterfactual_service.py`
- Delete: `db.py`
- Delete: `scripts/sanitize_symbols.py`
- Delete: `services/future_price.py`
- Delete: `services/pocketbase.py`
- Delete: `futurewallet.db` (git rm)

- [ ] `services/asset_types.py` modülü oluştur ve `_guess_asset_type(symbol: str) -> str` fonksiyonunu buraya koy.
- [ ] `services/ledger_service.py`, `services/decision_service.py`, `api/app.py` içindeki kopyaları kaldırıp `services.asset_types` modülünden içe aktar.
- [ ] `services/counterfactual_service.py` ve diğer servislerdeki `from services.pocketbase import ...` importlarını doğrudan `from services.pb import ...` yap.
- [ ] Eski `services/pocketbase.py`, `db.py`, `scripts/sanitize_symbols.py`, `services/future_price.py` dosyalarını sil.
- [ ] `futurewallet.db` dosyasını git takibinden çıkar ve diskten kaldır.
- [ ] `pytest tests/` çalıştır ve temizliği doğrula.

### Task 2: Konfigürasyon, Güvenlik & Kullanıcı İzolasyonu (P4, P6)

**Files:**
- Modify: `config.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `api/app.py`
- Test: `tests/test_security_auth.py`

- [ ] `config.py`: `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` (varsayılan: `https://openrouter.ai/api/v1`), `OPENROUTER_MODELS` (varsayılan: `anthropic/claude-3.5-sonnet,google/gemini-2.0-flash-001,deepseek/deepseek-r1`), `ENABLE_SCHEDULER` (varsayılan: `true`) ekle; `GOOGLE_API_KEY`, `GEMINI_MODEL`, `DATABASE_URL` değişkenlerini kaldır.
- [ ] `docker-compose.yml` ve `.env.example` dosyalarını yeni değişkenlerle güncelle.
- [ ] `api/app.py`: 64 KB istek boyutu kontrol middleware'i ekle (64 KB üzeri gövdede 413 Payload Too Large dön).
- [ ] `_extract_user_id`: `X-User-ID` başlığı kullanımını kaldır; kimliği yalnızca doğrulanmış `request.state.user_id` üzerinden al (eğer yoksa `verify_api_token` çağrılmadığı için 401).
- [ ] `DELETE /api/decisions/{id}` ve `DELETE /api/counterfactual/shadow-positions/{id}` için sahiplik doğrulaması ekle: kayıt bulunamazsa veya başka bir kullanıcıya aitse 404 fırlat.
- [ ] `tests/test_security_auth.py` içine 64 KB payload testi ve başka kullanıcının kararını silme (404) testleri ekle, çalıştır.

### Task 3: OpenRouter AI Servisi & Fallback Zinciri (P8)

**Files:**
- Modify: `services/ai_service.py`
- Modify: `services/decision_service.py`
- Modify: `api/app.py`
- Test: `tests/test_ai_service.py` (Yeni)

- [ ] `services/ai_service.py`: `google-genai` bağımlılığını kaldır; `httpx` ile OpenRouter REST API çağrısı yapan istemciyi oluştur.
- [ ] Modelleri `config.OPENROUTER_MODELS` listesine göre sırayla dene. 429 / 5xx / timeout durumunda sonraki modele geç. Tümü başarısızsa 502 `AIGenerationError`, API anahtarı boşsa 503 `AIUnavailableError` fırlat.
- [ ] Prompt güvenliği: kullanıcı notunu `<user_input>...</user_input>` etiketi içine al, 2000 karakterle sınırla, "Yatırım tavsiyesi değildir" uyarısını ekle.
- [ ] `services/decision_service.py`: `generate_ai_retrospective` çağrısında başarılı AI yanıtı sonrası kararın PocketBase kaydını `status: "REVIEWED"` ve `ai_retrospective` ile güncelle.
- [ ] `tests/test_ai_service.py` dosyasını oluştur: mock OpenRouter çağrısı ile model fallback, 502 ve 503 senaryolarını test et.

### Task 4: Portföy Değerleme, Value-Series & Fiyat Fallback (P9)

**Files:**
- Modify: `api/app.py`
- Modify: `services/price_service.py`
- Test: `tests/test_price_valuation.py` (Yeni)

- [ ] `api/app.py` `/api/portfolio/value-series`: `step` hesaplamasında max 400 nokta sınırı uygula (aşarsa 422 dön). Haftalık adımda gerçek 7 gün adımı kullan.
- [ ] `api/app.py` `/api/portfolio/real-valuation`: `nominal_end` verilmediğinde `date_to` snapshot'ını kullan (`date_from` hatasını düzelt).
- [ ] `services/price_service.py`: Hafta sonu / tatil günlerinde `get_price_on` için önceki işlem gününü arama fallback'i ekle.
- [ ] Birim ve entegrasyon testlerini ekle ve çalıştır.

### Task 5: Gölge Portföy (Counterfactual Engine) İyileştirmeleri (P10)

**Files:**
- Modify: `services/counterfactual_service.py`
- Modify: `api/app.py`
- Test: `tests/test_counterfactual.py` (Yeni)

- [ ] `services/counterfactual_service.py`: `services.pb` fonksiyonlarını kullan.
- [ ] `what_if_scenario`: sahte `quantity=1.0` placeholder'ı kaldır; gerçek pozisyon ve tarihsel fiyatları bağla.
- [ ] Fırsat maliyeti hesabı: `HELD_INSTEAD` için `gölge - gerçek_nakit`, `BOUGHT_INSTEAD` için `gölge - gerçek_getiri`.
- [ ] Gölge pozisyon listeleme ve silmede kullanıcı izolasyonunu doğrula (başkasının gölgesi 404).

### Task 6: Benchmark & APScheduler Zamanlayıcı Entegrasyonu (P11, P13)

**Files:**
- Modify: `services/benchmark_service.py`
- Modify: `services/decision_service.py`
- Modify: `api/app.py`
- Test: `tests/test_scheduler_and_outcomes.py` (Yeni)

- [ ] `services/benchmark_service.py`: `compute_gold_try_gram = (GC=F_USD / 31.1035) * USDTRY` formülünü doğrula ve `date` tekil indeksiyle PB macro_data'ya kaydet.
- [ ] `services/decision_service.py`: `auto_close_expired_decisions` içinde vadesi dolmuş kararların `outcome_price`, `outcome_return_pct`, `target_hit` alanlarını `price_service` ile hesaplayıp güncelle.
- [ ] `api/app.py`: `POST /api/decisions/{id}/evaluate` manuel değerlendirme endpoint'i ekle.
- [ ] `api/app.py`: `lifespan` içine `APScheduler` (BackgroundScheduler) entegre et. `config.ENABLE_SCHEDULER` false ise zamanlayıcı başlatma.
- [ ] Zamanlayıcı işleri: günlük makro veri güncellemesi ve saatlik/günlük `auto_close_expired_decisions`.

### Task 7: Monte Carlo & Stres Testi Güncellemeleri (P12)

**Files:**
- Modify: `services/simulation_service.py`
- Modify: `api/app.py`
- Test: `tests/test_simulation.py` (Yeni)

- [ ] `services/simulation_service.py`: `session: Any = None` parametresini kaldır.
- [ ] `market_crash` senaryosunda şok etkisinin kalıcı olmasını sağla (kriz günü ve sonrasındaki tüm günlere tam kriz çarpanı).
- [ ] `n_simulations` üst sınırını 20,000 olarak doğrula.

### Task 8: Web Arayüzü: Login & Auth & CSP (P14)

**Files:**
- Create: `web_app/templates/login.html`
- Modify: `web_app/__init__.py`
- Modify: `web_app/templates/dashboard.html`
- Modify: `web_app/templates/decision_form.html`
- Modify: `web_app/static/app.js`

- [ ] `web_app/templates/login.html` şablonu oluştur (PocketBase ile kullanıcı adı/şifre girişi, token alma).
- [ ] `web_app/__init__.py` içinde `/web/login` rotasını tanımla.
- [ ] `web_app/static/app.js`: `apiFetch` içine `sessionStorage.getItem('pb_token')` ile Bearer token ekle; 401 hatası alındığında `/web/login` sayfasına yönlendir.
- [ ] Tüm şablonların altbilgisine "Bu platformdaki veriler ve AI çıktıları yatırım tavsiyesi niteliğinde değildir." uyarısını ekle.
- [ ] `decision_form.html` ve diğer şablonlardaki inline style'ları temizle (CSP uyumu).

### Task 9: Dokümantasyon, TODO Senkronizasyonu & Son Doğrulama (P0, P15)

**Files:**
- Modify: `TODO.md`
- Modify: `GUNCEL_IS_PLANI.md`
- Modify: `MVP.md`
- Modify: `README.md`

- [ ] Tüm test paketini çalıştır (`pytest tests/`).
- [ ] Yalnızca testten geçen maddeleri `TODO.md` ve `GUNCEL_IS_PLANI.md` içinde `[x]` olarak işaretle.
- [ ] `git status` ve `git diff` ile istenmeyen dosya kalmadığını teyit et.
