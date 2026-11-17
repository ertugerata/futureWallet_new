# FutureWallet – Güncel İş Planı (v5 – 2026-11-17, PocketBase + FastAPI + OpenRouter)

> **Kaynak & Dayanak:** `FUTUREWALLET_DUZELTME_PROMPTLARI.md` (v3), `TODO.md` (v5) ve `docs/plans/2026-11-17-mvp-remaining-work.md`.
> **Temel Kural (Prompt 0):** Yalnızca **gerçek PocketBase (v0.40.6)** entegrasyon testini geçen maddeler tamamlandı (`[x]`) sayılır.
> **Bu dokümanın durumu:** v3'teki "her şey kırık" analizi geçersizdir. Güncel doğrulama: `pytest tests/` → **100/100 geçti** (gerçek PB; P14 + P9 currency + EXPIRED-e2e + review minörleri turu dahil; UI canlı tarayıcı E2E ile); `ruff check .` + `ruff format --check .` temiz; `mypy api services config.py web_app` (gevşek) hatasız. Commits: `af9d5e1`…`10274b0` (P10/P11/P14), `feat/mvp-remaining-work` dalı `3b8bcb6`…(P9/EXPIRED/minörler/CI duman).

---

## 📊 Mevcut Durum Analizi (Doğrulanan)

| Alan / Modül | Mevcut Durum |
|---|---|
| **Uygulama İçe Aktarımı** | ✅ `import api.app` temiz; Pydantic model sırası doğru; 68 test toplanıp geçiyor |
| **`price_service.py`** | ✅ SyntaxError giderildi; `get_price_on` PB→yfinance→ccxt zinciri, hafta sonu/tatil fallback'i |
| **PocketBase Okuma Yolları** | ✅ `services/pb.py` senkron SDK sarmalayıcıları; tüm filtreler `client.filter(raw, params)` |
| **PB Şema ve Kurallar** | ✅ `pb_migrations/` 6 koleksiyon; RLS kullanıcı kuralları, benzersiz indeksler, `users` kapalı kayıt |
| **Kimlik Doğrulama** | ✅ PB JWT (`get_current_user` + `auth_refresh`); `X-User-ID`/`API_TOKEN` kaldırıldı; sahiplik 404'leri; kullanıcı+karar bazlı rate limit; 64 KB gövde limiti |
| **Test Altyapısı** | ✅ Gerçek PB binary fixture'ları; PB'yi taklit eden MagicMock yok |
| **Ledger Mantığı** | ✅ 409 yetersiz stok, kullanıcı kilidi, ortalama maliyet, unrealized PnL, `cash_received` (DIVIDEND) |
| **AI Entegrasyonu** | ✅ OpenRouter fallback zinciri + 502/503 semantiği + prompt injection etiketi; `google-genai` bağımlılığı kaldırıldı |
| **Zamanlayıcı** | ✅ APScheduler lifespan'de; `ENABLE_SCHEDULER`; EXPIRED job'ı uçtan uca PB testli (`tests/test_expiry_e2e.py`; testin bulduğu `_parse_pb_date`/`evaluate_decision` sessiz hataları düzeltildi) |
| **Monte Carlo / Stres** | ✅ Kabul testli: medyan yakınsama (%2), market_crash kalıcılığı, Cholesky determinizm, 40 kutu histogram, 3/6/12 ay tek çağrıda |
| **Web Arayüzü** | ✅ PB login (`/web/login` + `auth-with-password` + `auth-refresh`), Bearer JWT, canlı tarayıcı E2E; DOM API render (innerHTML yok), inline style/script yok, Chart.js SRI, CSP `connect-src` PB origin'li |
| **Kalan küçük açıklar** | Yok — P9 dinamik currency, EXPIRED job uçtan uca testi ve iki review minörü (shadow create sahipliği, PB ID girdi doğrulaması) 2026-11-17 turunda kapandı |

---

## 🗺️ Prompt Bazlı Güncel İş Planı

### 🔴 Prompt 1 — Uygulama, Lint / CI / Bağımlılıklar ✅
Tüm maddeler tamam: import temiz, ruff/format/mypy CI'da, `requirements.in` sade (sqlalchemy/schedule/google-genai yok), uv ile üretilmiş kilit, lifespan fail-closed + `/health pb` alanı. Ayrı `import api.app` duman adımı 2026-11-17'de CI test job'ına eklendi (dummy PB env).

### 🔴 Prompt 2 — Gerçek PB Test Altyapısı ✅
`pb_server`/`pb_clean`/`make_user`/`auth_headers`/`api_client` fixture'ları gerçek PB v0.40.6 üzerinde; CI'da `pb_bin` önbelleği + `pytest -m pb`.

### 🔴 Prompt 3 — PB Şema, Erişim Kuralları, Migration ✅
6 koleksiyon migration'ı, RLS kuralları, benzersiz indeksler, `shadow_portfolios.decision` cascade, `users` createRule null; `RISK_REDUCTION` kod + web'den tamamen çıkarıldı.

### 🔴 Prompt 4 — PB Dağıtımı, Sırlar, Compose ✅
`docker/pocketbase/Dockerfile` + entrypoint (migrate + serve), compose'ta `${VAR:?required}`, sabit parola/emlak yok, `.env.example` PB+OpenRouter+scheduler.

### 🔴 Prompt 5 — PB İstemci Katmanı ✅
`services/pb.py` (admin singleton + user client), `get_list(params=)` hataları ve `benchmark._get_pb_price` sessiz yutması düzeltildi, f-string filtre kalmadı, endpoint'ler senkron `def` → threadpool (commit `b5fca94`).

### 🔴 Prompt 6 — Auth & Kullanıcı İzolasyonu ✅
JWT-only kimlik; liste/özet uçları kullanıcıya filtreli; tekil uçlarda sahiplik 404; retrospektif limiti kullanıcı+karar bazında 60 sn/1 ve `reset_rate_limits()`; 413/401/404/429 kabul testleri geçiyor.

### 🟠 Prompt 7 — Ledger + Decision ✅
409, kilit, idempotent soft-delete, ortalama maliyet, unrealized PnL, `cash_received`, `decision_date` gelecek→422, route sırası, standart hata kodları — hepsi testli.

### 🟠 Prompt 8 — AI: OpenRouter + Hata Semantiği ✅
Fallback zinciri, 502/503, `<user_input>` güvenliği, REVIEWED güncellemesi testli.

### 🟢 Prompt 9 — Price / Time-Travel / Value-Series ✅ (tamam)
Değerleme zinciri, 400 nokta limiti, `date_to` snapshot düzeltmesi tamam. `currency` dinamik: `services/asset_types.py` `base_currency`/`infer_portfolio_currency` (BIST/TL→TRY, diğer tabanlar→USD, karışıkta çoğunluk); value-series tutulan sembollerden, Monte Carlo varlık listesinden üretiyor; P14 seçicisi bağlandı.

### 🟡 Prompt 10 — Gölge Portföy ✅
Servis PB katmanında, izolasyon+cascade testli, `what_if` placeholder'ı kaldırıldı. `track_shadow` artık kararın bağlı SELL işleminden gerçek miktar/fiyatı okuyor (`transaction_id` sahiplik+sembol+tip doğrulamasıyla; hatalı link 400); link yoksa 1.0/target_price fallback.

### 🟡 Prompt 11 — Benchmark, Enflasyon, Zamanlayıcı ✅ (kabul testli)
Upsert tek kayıt testiyle doğrulandı; EVDS/FRED sahte veri yok; `gold_try_gram` şema migration'ı (`gold_try`→`gold_try_gram`, kodun yazdığı alan şemada eksikti ve PB sessizce düşürüyordu) + formül birim testi; `_get_pb_price` gün-sonu `date <=` düzeltmesi; APScheduler'da `expire_decisions` + `refresh_macro` (24h) job'ları kayıt testiyle; `compare_to_benchmark` `alpha` sözlüğü döndürüyor (deterministik PB testi).

### 🟡 Prompt 12 — Monte Carlo & Stres ✅
`tests/test_simulation_stress.py` 6/6: medyan teorik ±%2 (20k yol), market_crash −%50 kalıcı, singular kovaryans çökmüyor (eigen clip 1e-12), Cholesky deterministik, 422 limitleri, 63/126/252 tek çağrıda. Boş portföy NaN hatası giderildi.

### 🟡 Prompt 13 — Karar Günlüğü ✅
DELETE+cascade testli, outcome alanları `evaluate`, stats + `insufficient_data`, zamanlayıcı EXPIRED (job kurulumu; uçtan uca test P11 eksiği ile aynı madde).

### ❌→✅ Prompt 14 — Web Arayüzü ✅ (canlı tarayıcı E2E ile)
`/web/login` + `static/login.js` (PB `auth-with-password` → `sessionStorage.pb_token`, açılışta `auth-refresh`, 401→login); `app.js` sıfırdan: tek `api()` katmanı Bearer JWT + `opts.params` (eski dosyada GET parametreleri hiç gönderilmiyordu ve JS içine gömülü CSS blokları sözdizimi hatasıydı); tüm render DOM API (`textContent`), sunucu verisi `innerHTML` yok; `decision_form` inline script/style'dan arındırıldı; Chart.js SRI; CSP `connect-src`'e PB origin eklendi (olmazsa login fetch'i CSP bloke ediyor — E2E'de yakalandı); paneller: Snapshot+Time-Travel, İşlem Ekleme/Geçmişi(void), Karar Günlüğü (AI/Kapat/Sil + outcome + duygu özeti), Gölge (kıyaslama + ekleme/silme), MC (40-kutu canvas histogram + p5/p50/p95), Stres tablosu (en kötü vurgusu), AI anlatısı + disclaimer; para birimi seçicisi Monte Carlo API `currency` alanına bağlı (canlı E2E: `assets=BTC` → seçici USD, kartlar `$`, konsol hatası yok).

### 🟢 Prompt 15 — Temizlik, Bağımlılıklar, Doküman ✅
Kalıntı dosyalar silindi ve commit'lendi; `services/asset_types.py` tekilleştirme tamam; `requirements.in` temizliği + uv kilidi tamam; `TODO.md`/`GUNCEL_IS_PLANI.md`/`README.md`/`MVP.md` v4'e senkronlandı; `SPRINT_PLANI_KALANLAR.md` geçersizlik banner'ı ile arşivlendi; **CI 5/5 yeşil** (run `44056500353`, pip-audit dahil). P15 kapandı.

---

## 📋 Hızlı Kontrol Listesi

```text
[x] 1. import api.app hatasız.
[x] 2. ruff check + format --check sıfır hata.
[x] 3. Boş PB + migration → 6 koleksiyon.
[x] 4. İki kullanıcı birbirinin verisini okuyamıyor (404).
[x] 5. changeme / admin@example.com / API_TOKEN yok.
[x] 6. Snapshot zengin (average_cost, unrealized, cash_received).
[x] 7. Fazla SELL → 409.
[x] 8. Time-travel 30k→60k %100 PnL senaryo testi geçiyor.
[x] 9. OpenRouter 502/503 semantiği testli.
[x] 10. market_crash %50 kalıcılık testi geçiyor.
[x] 11. EXPIRED job PB üzerinde uçtan uca testli (`tests/test_expiry_e2e.py`).
[x] 12. Web UI login → dashboard akışı tarayıcı E2E ile doğrulandı.
[x] 13. Kalan üç madde (P9 currency, EXPIRED e2e, review minörleri) kapandı — suite 100/100.
```

## 🔜 Sıradaki İş Sırası

Kalan iş yok. Uygulama içi tek not: `infer_portfolio_currency` karışık sepette çoğunluk para birimini etiketler (`shortcut:` — gerçek çoklu-currency değerlemesi gelince kaldırılacak).
