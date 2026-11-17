# FutureWallet – Güncel İş Planı (v4 – 2026-11-16, PocketBase + FastAPI + OpenRouter)

> **Kaynak & Dayanak:** `FUTUREWALLET_DUZELTME_PROMPTLARI.md` (v3), `TODO.md` (v4) ve `docs/superpowers/plans/2026-11-16-futurewallet-completion.md`.
> **Temel Kural (Prompt 0):** Yalnızca **gerçek PocketBase (v0.40.6)** entegrasyon testini geçen maddeler tamamlandı (`[x]`) sayılır.
> **Bu dokümanın durumu:** v3'teki "her şey kırık" analizi geçersizdir. Güncel doğrulama: `pytest tests/` → **76/76 geçti** (tek oturum, gerçek PB); `ruff check .` + `ruff format --check .` temiz; `mypy api services config.py` (gevşek) hatasız. Commits: `af9d5e1`, `b5fca94`, `5a63210`, `47b77f4`, `e1baf9c` (final-review fix pass: simülasyon hücre bütçeleri, chunked 64 KB limiti, günlük makro job, CASH cüzdanı semantiği).

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
| **Zamanlayıcı** | ✅ APScheduler lifespan'de; `ENABLE_SCHEDULER`; EXPIRED otomatik job (uçtan uca test henüz yok — bkz. P13 notu) |
| **Monte Carlo / Stres** | ✅ Kabul testli: medyan yakınsama (%2), market_crash kalıcılığı, Cholesky determinizm, 40 kutu histogram, 3/6/12 ay tek çağrıda |
| **Web Arayüzü** | ⚠️ Login akışı yok (eski statik token'ı gönderiyor → P6 sonrası 401 beklenir); `innerHTML`/inline style CSP borcu — **P14 açık** |
| **Kalan küçük açıklar** | `track_shadow` miktarı hâlâ 1.0 sabiti (P10); `value-series` para birimi sabit TRY (P9); gold/alpha birim testi yok (P11) |

---

## 🗺️ Prompt Bazlı Güncel İş Planı

### 🔴 Prompt 1 — Uygulama, Lint / CI / Bağımlılıklar ✅
Tüm maddeler tamam: import temiz, ruff/format/mypy CI'da, `requirements.in` sade (sqlalchemy/schedule/google-genai yok), uv ile üretilmiş kilit, lifespan fail-closed + `/health pb` alanı. Tek açık uç: ayrı `import api.app` duman adımı (pytest zaten import ediyor; düşük öncelik).

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

### 🟠 Prompt 9 — Price / Time-Travel / Value-Series ✅ (tek alt madde açık)
Değerleme zinciri, 400 nokta limiti, `date_to` snapshot düzeltmesi tamam. **Açık:** `value-series` `currency` alanı sabit `"TRY"`; varlık tabanına göre dinamik USD/TRY bağlanacak (P14 seçicisiyle birlikte).

### 🟡 Prompt 10 — Gölge Portföy ✅ (tek alt madde açık)
Servis PB katmanında, izolasyon+cascade testli, `what_if` placeholder'ı kaldırıldı. **Açık:** `api/app.py` `track_shadow=True` dalı gölgeyi `quantity=1.0`/`entry_price=target_price` sabitleriyle açıyor; kararın bağlı transaction'ının gerçek miktar/fiyatı kullanılmalı.

### 🟡 Prompt 11 — Benchmark, Enflasyon, Zamanlayıcı ✅ (test eksiği)
Upsert tek kayıt, EVDS/FRED sahte-veri yok, `gold_try_gram` formülü, günlük+EXPIRED job'ları, benchmarks/alpha ucu çalışıyor (`_get_pb_price` düzeltmesiyle). **Eksik:** `gold_try_gram`/alpha deterministik birim testi; EXPIRED job'ının uçtan uca PB testi (`tests/test_scheduler_and_outcomes.py` planlanmıştı, yazılmadı).

### 🟡 Prompt 12 — Monte Carlo & Stres ✅
`tests/test_simulation_stress.py` 6/6: medyan teorik ±%2 (20k yol), market_crash −%50 kalıcı, singular kovaryans çökmüyor (eigen clip 1e-12), Cholesky deterministik, 422 limitleri, 63/126/252 tek çağrıda. Boş portföy NaN hatası giderildi.

### 🟡 Prompt 13 — Karar Günlüğü ✅
DELETE+cascade testli, outcome alanları `evaluate`, stats + `insufficient_data`, zamanlayıcı EXPIRED (job kurulumu; uçtan uca test P11 eksiği ile aynı madde).

### ❌ Prompt 14 — Web Arayüzü (AÇIK — tek büyük dilim)
- `/web/login`: PB `auth-with-password`, sessionStorage'da PB JWT, `auth-refresh`, 401→login yönlendirmesi.
- `apiFetch`'e Bearer PB JWT (mevcut `app.js` eski `apiToken`'ı gönderiyor → tüm web çağrıları 401).
- `app.js:379` `innerHTML` → DOM API/`textContent`; `decision_form.html` inline style → CSS sınıfı; Chart.js yerel vendor/SRI.
- Paneller: Time-Travel, Karar Günlüğü (Retrospektif/Kapat/Sil), Gölge, Stres, İşlem Ekleme; USD/TRY seçicisi; yasal uyarı satır altları.

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
[ ] 8. Time-travel 30k→60k senaryo testi yazılmadı.
[x] 9. OpenRouter 502/503 semantiği testli.
[x] 10. market_crash %50 kalıcılık testi geçiyor.
[ ] 11. EXPIRED job uçtan uca test edilmedi.
[ ] 12. Web UI login akışı yok (P14).
[ ] 13. Kalan küçük açıklar: track_shadow miktarı, dinamik currency, gold/alpha birim testi.
```

## 🔜 Sıradaki İş Sırası

1. **P14 web arayüzü** — en büyük ve tek blok eden dilim (login olmadan web kullanılamaz).
2. P10 `track_shadow` gerçek miktar/fiyat · P11 scheduler/outcome testleri · P9 dinamik currency · P8-hızlı-kontrol 8 time-travel senaryo testi.
3. Push + CI yeşil doğrulaması.
