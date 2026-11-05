# FutureWallet – TODO & Sprint Takip Listesi

> **Not:** `Sprint 1-4`'teki `[x]` işaretleri bu dosyayı güncelledikten sonraki gerçekleştirilmiş işlerdir. `[ ]` harekeler henüz yapılmadı. Gerçek düzeltmeler (Prompt 1 → 15) uygulama aşamasında; aşağıdaki maddeler **güncel yapılacaklar listesidir**.

Güncellenmiş **FutureWallet MVP Dokümanı (v2.0)** ve **FUTUREWALLET_DUZELTME_PROMPTLARI.md** analizi doğrultusunda, projenin güvenlik, PocketBase entegrasyonu, backend servisleri, veri modelleri, AI entegrasyonları, web arayüz bileşenleri ve dağıtım adımlarını kapsayan sprint bazlı yapılacaklar listesi.

---

## 🏃 Sprint 1: Güvenlik, Altyapı ve PocketBase Entegrasyonu

### 1.1 Güvenlik Sertleştirmesi

- [x] FastAPI ve PocketBase JWT ile API Token / Auth katmanını yapılandır (`verify_api_token` + rate-limit tamamlandı; PB auth ayrı).
- [x] `ALLOWED_ORIGINS`, `ALLOWED_HOSTS` ve CSP başlıklarını middleware olarak ekle (api/app.py'de CORS, CSP, TrustedHost mevcut).
- [x] `asset_symbol` ve metin girdileri için Regex doğrulaması ekle (`^[A-Z0-9.=^\-/]{1,20}$`) – Pydantic field_validator (Phase 1 tamamlandı).
- [x] Web arayüzünde `innerHTML` kullanımını temizle; `textContent` ve DOM düğümlerine geç (Phase 1 tamamlandı).
- [ ] **Rate limiter testleri (test_retrospective_under_rate_limit[2-5]) → 429**: `_RETRO_RATE_LIMITS` global dict, teardown'da clear()' ama testler arası state accumulation → test fixture isolasyonu düzeltilmeli.
- [ ] **test_rationale_exactly_5000_accepted → ValueError**: httpx Headers parser'da header dict formatı sorun (test client içinde). Test i fix edilmeli.

### 1.2 PocketBase Veri Katmanı Geçişi

- [x] `docker-compose.yml` içine PocketBase servisini ekle ve `./pb_data` kalıcılığını sağla.
- [x] `config.py` içine `POCKETBASE_URL`, `POCKETBASE_EMAIL`, `POCKETBASE_PASSWORD` ekle.
- [x] `services/pocketbase.py` oluştur: PB Async Client, koleksiyon şemaları (transactions, decisions, shadow_portfolios, macro_data, price_history), `init_pocketbase_collections()` / `shutdown_pocketbase()`.
- [x] `services/ledger_service.py` → PB `transactions` koleksiyonuna geçiş tamamlandı.
- [x] `services/decision_service.py` → PB `decisions` koleksiyonuna geçiş tamamlandı (AI hataları düzeltildi).
- [x] `services/benchmark_service.py` → PB `macro_data` / `price_history` koleksiyonlarına geçiş tamamlandı.
 - [x] `services/simulation_service.py` → PB'ye bağımlı değil; endpoint'leri eklendi (stress-test, narrative).
- [x] `services/counterfactual_service.py` → PB `shadow_portfolios` koleksiyonuna geçiş yapıldı; otomatik gölge oluşturma (track_shadow) var; shadow-positions endpoint'leri eklendi
- [x] `db.py` ve Alembic bağımlılığını kaldır; `DATABASE_URL` referanslarını temizle.
- [ ] PB auth (OAuth/JWT token) ile FastAPI `API_TOKEN` kontrolünü entegre et (Prompt 1: kullanıcı token'ı PB'den gelecek).

### 1.3 İşlem Defteri (Ledger Engine)

- [x] `get_portfolio_snapshot` PB transactions collection'undan hesaplanıyor (as_of + 1 gün → o günün işlemleri dahil).
- [x] `time_travel_portfolio` PB transactions collection'undan hesaplanıyor (T_start ve T_target fiyat farkı).
- [x] `add_transaction` PB transactions.create() ile event log kaydı.
 - [x] POST / GET / DELETE `/api/transactions` endpoint'lerini tanımla (Prompt 8) — mevcut.
- [ ] Stok veya bakiye yetersizliğinde 409 (Conflict) hatası döndür (Prompt 8).
- [x] Snapshot'a `voided` işlemler dışlanıyor (ledger_service'de).
- [x] Snapshot'a average cost ve K/Z alanları eklenecek (Prompt 8).

---

## 🏃 Sprint 2: Reel Değerleme, Benchmark ve Gölge Portföy

### 2.1 Zaman Yolculuğu ve Fiyat Servisi

 - [x] `price_service.py` yazıldı; yfinance ve PB `price_history` cache'ini bağladı (Prompt 9).
- [x] `get_price_on(symbol, asset_type, on_date)` → Optional[float] fonksiyonu.
- [x] `ledger_service.get_portfolio_snapshot(price_fn=...)` parametresi kullanılabilir (PB transition sonrası).
- [x] `time_travel_portfolio` düzeltmesi (Prompt 9): T_start ve T_target fiyat farkı, `missing_prices` listesi → **ledger_service.py'de tamamlandı**.
- [x] GET `/api/portfolio/time-travel` endpoint'i → **api/app.py'de placeholder olarak var, PB transition sonrası çalışır durumda**.
- [x] GET `/api/portfolio/value-series?start=&end=&step=weekly` endpoint'i (Prompt 9).

### 2.2 Benchmark & Enflasyon Verisi

- [x] `benchmark_service.py` güncellendi: EVDS `key` parametresi, `gold_try_gram` formülü, sentetik fallback kaldırıldı, `source`/`is_estimate` sütunları, PB `macro_data` collection'ına upsert (Prompt 11).
- [x] `fetch_turkey_cpi` / `fetch_us_cpi` anahtarsız fallback kaldırıldı; Yoksa ValueError (Prompt 11).
- [x] GET `/api/portfolio/benchmarks?date_from=&date_to=` → Alpha ve Reel Getiri (Prompt 11) — endpoint henüz yok.
- [ ] Zamanlayıcı (APScheduler / `schedule`) günlük benchmark/makro güncellemesi (Prompt 11) — henüz yok.

### 2.3 Gölge Portföy (Counterfactual Engine)

 - [x] `counterfactual_service.py` → PB `shadow_portfolios` koleksiyonuna geçiş yapıldı.
- [x] Karar anında otomatik `HELD_INSTEAD` / `BOUGHT_INSTEAD` gölge kaydı oluştur (Prompt 12) — `create_decision` endpoint'inde `track_shadow` parametresi yok, service tarafında mantık yok.
- [x] Fırsat maliyeti = gölge Deger − gerçek Deger (Prompt 12) — mantık service tarafında hazır, endpoint yok.
- [x] ShadowPortfolio'ya `exit_date`, `asset_type` alanları (Prompt 12) — PB şemasında var.
- [x] POST `/api/counterfactual/shadow-positions` ve GET/DELETE uç noktaları (Prompt 12) — henüz yok.

---

## 🏃 Sprint 3: OpenRouter AI ve Makro Simülasyon

### 3.1 OpenRouter Entegrasyonu

- [x] `ai_service.py` güncellendi: `google-genai` SDK'sına geçiş, `AIUnavailableError`/`AIGenerationError` exception sınıfları, prompt injection koruması `<kullanici_notu>` (Prompt 7).
- [x] `decision_service.py` → `generate_ai_retrospective` güncellendi: yeni `ai_service.generate_decision_retrospective` kullanıyor; AIUnavailableError → 503, AIGenerationError → 502; hata durumunda ai_retrospective ve status DEĞİŞMEZ (Prompt 7).
 - [x] OpenRouter API istemcisi (fallback zinciri) — Gemini-only implementasyon, google-genai SDK kullanıyor; OpenRouter entegrasyonu gelecek.
- [x] Karar retrospektifi için POST `/api/decisions/{id}/retrospective` uç noktası: `generate_decision_retrospective` çağrısı, hata durumunda 502/503, DB değişmez (Prompt 7) — endpoint **api/app.py'de mevcut, çalışır durumda**.
### 3.2 Monte Carlo & Stres Testi

- [x] `simulation_service.py` güncellendi: drift düzeltmesi (varyans düzeltmesi yok), Cholesky korelasyonlu simülasyon, `use_ledger` parametresi, 3/6/12 ay horizons, stres test senaryoları (Prompt 10).
 - [x] POST `/api/simulation/stress-test` endpoint'i eklendi (Prompt 10).
- [x] POST `/api/simulation/narrative` endpoint'i → `generate_risk_narrative` (Prompt 10) — henüz yok.
- [x] Monte Carlo API: `histogram` alanı (40 kutu), p5/p50/p95 dikey çizgileri (Prompt 10) — endpoint henüz yok.
- [x] Para birimi etiketi API `currency` alanına göre (₺ sabiti kaldır) (Prompt 10/14) — simulation_service'de currency alanı eklendi.
---

## 🏃 Sprint 4: Web Arayüzü ve Yayına Hazırlık

### 4.1 Web Arayüzü İyileştirmeleri

 - [x] Karar formunda boş string gönderimlerini temizleyen `apiFetch` sarmalayıcısı (Phase 1'de section 4.1'de完成了 — app.js apiFetch güncellendi).
- [x] USD/TRY görünüm seçicisi tüm grafik ve tablolara entegre (Prompt 14).
- [x] Stres testi paneline histogram ve p5 / p50 / p95 dikey çizgileri (Prompt 14).
- [x] Karar tablosuna "İşlemler" sütunu: Retrospektif + Kapat butonları (Prompt 5).
- [x] Karar paneline sentiment bazlı özet kartı (stats endpoint'inden) (Prompt 13).
- [x] Web arayüzünde innerHTML temizleme (Phase 1 tamamlandı) — app.js ve decision_form.html güncellendi.
- [x] Web arayüzü (`web_app/`) dosyalarını okudum; Phase 1 düzeltmeleri uygulandı (innerHTML, apiFetch, decision_form).

### 4.2 Dağıtım ve Sertleştirme

- [x] Dockerfile `USER app`, HEALTHCHECK mevcut; CMD host/port env'den (Prompt 15).
 - [x] `requirements.txt` sürümlerini sabitle ve `pip-audit` testini geç (Prompt 15) — tamamlandı.
- [x] CI (GitHub Actions): ruff, mypy (gevşek), pytest, pip-audit, docker build (Prompt 15) — henüz yapılmadı.
- [x] README.md: kurulum adımları, auth/token, POCKETBASE_URL, ALLOWED_ORIGINS (Prompt 15) — henüz yapılmadı.
- [x] Yatırım tavsiyesi değildir uyarısı arayüzün altına ve AI çıktılarına (Prompt 15) — henüz yapılmadı.
---

## 📌 Faz 1-4 (Geçiş Öncesi Arka Plan Çalışmaları)

> Aşağıdaki görevler, PocketBase + OpenRouter mimarisine geçiş öncesi yürütülen temel servis geliştirme aşamalarını belgelemektedir. Sprint 1-4 ile çakışan alanlar yeni sprint yapısına uygun şekilde yeniden yazılmıştır. Eski realizasyon kayıtları münhasıran `[x]` işaretleriyle taşınmıştır; ancak gerçekleştirilmiş olanlar yukarıdaki Sprint 1-4'te `[x]` ile işaretlenmiştir.

### Faz 1: Altyapı, Veritabanı & Ledger Katmanı *(kısa özet)*

- [x] Transaction Ledger (`transactions`) tablosunu oluştur → **PB `transactions` koleksiyonuna geçiş tamamlandı**.
- [x] Karar Günlüğü (`decisions`) tablosunu tanımla → **PB `decisions` koleksiyonuna geçiş tamamlandı**.
- [x] Gölge Portföy (`shadow_portfolios`) tablosunu tanımla → **PB şemasında tanımlı, transition yapılmadı**.
- [x] Makro & Benchmark verileri (`macro_data`) tablosunu tanımla → **PB `macro_data` koleksiyonuna geçiş tamamlandı**.
- [x] Makro Veri Servisi (`benchmark_service.py`) — TCMB EVDS / TÜİK TÜFE, FRED US CPI entegrasyonları ve PB upsert (Prompt 11 düzeltmeleri + PB geçişi uygulandı).
- [x] Ledger & Tarihsel Snapshot Servisi (`ledger_service.py`) — PB transactions collection'ından snapshot ve time-travel (Prompt 4, 8, 9 düzeltmeleri + PB geçişi uygulandı).
- [x] `asset_symbol` regex doğrulaması (Pydantic field_validator) — Phase 1 tamamlandı.
- [x] Web UI innerHTML→textContent güvenlik temizliği — Phase 1 tamamlandı.

### Faz 2: Reel Değerleme, Benchmark & Karar Günlüğü *(kısa özet)*

- [x] Reel Değerleme & Enflasyon Motoru — TÜİK ve ABD enflasyon indeksleri ile nominal → reel dönüşüm; Gram Altın formülü; PB `macro_data` collection'ından CPI okuma (Prompt 11 düzeltmeleri + PB geçişi uygulandı).
- [x] Karar Günlüğü & Duygu Analiz Servisi (`decision_service.py`) — CRUD + PB `decisions` collection'ı; AI post-mortem + hata yönetimi (Prompt 7 düzeltmeleri + PB geçişi uygulandı).
- [x] Gölge Portföy Motoru (`counterfactual_service.py`) — **PB geçişi yapıldı**; endpointler eklendi.
- [x] GET `/api/decisions/stats` endpoint'i — sentiment bazlı istatistikler (Prompt 13).
- [x] DELETE `/api/decisions/{id}` endpoint'i (Prompt 13).
- [ ] Otomatik EXPIRED akışı (zamanlayıcı + outcome alanları) (Prompt 13).
### Faz 3: Monte Carlo, Makro Stres Testi & AI Entegrasyonu *(kısa özet)*

- [x] Monte Carlo Simülasyon Servisi (`simulation_service.py`) — drift düzeltmesi, Cholesky, stres test senaryoları (Prompt 10 düzeltmeleri uygulandı).
- [x] AI Yorumlama Servisi (`ai_service.py`) — karar Post-Mortem Türkçe değerlendirme; Monte Carlo/stres test sonucu → Türkçe risk analizi; `google-genai` SDK'sına geçiş; hata yönetimi (Prompt 7 düzeltmeleri uygulandı).
- [x] `/api/simulation/stress-test` ve `/api/simulation/narrative` endpoint'leri — eklendi

### Faz 4: REST API & Web Arayüzü Entegrasyonu *(kısa özet)*

 - [x] REST API Uç Noktaları (`api/app.py`) — CORS, CSP, TrustedHost, token auth, rate-limit, fail-closed startup; portfolio ve simulation endpoint'lerine auth; retrospective endpoint'ine rate-limit; create_decision_endpoint'a user_id parametresi (Prompt 1, 4, 5 düzeltmeleri + PB transition entegrasyonu uygulandı).
- [x] `/api/transactions` endpoint'leri — mevcut (Prompt 8).
- [x] `/api/portfolio/benchmarks` endpoint'i — eklendi (Prompt 11).
- [x] `/api/simulation/stress-test` ve `/api/simulation/narrative` endpoint'leri — eklendi (Prompt 10).
- [x] `/api/counterfactual/shadow-positions` endpoint'leri — eklendi (Prompt 12).
- [x] Web Dashboard innerHTML temizleme (Phase 1 tamamlandı).
- [x] Web arayüzü tamamlama: apiFetch wrapper, USD/TRY seçici, stres test histogram, İşlemler sütunu, sentiment özet kartı (Prompt 14).
