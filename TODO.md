# FutureWallet – TODO & Sprint Takip Listesi (v4 – 2026-11-16 doğrulanmış durum)

> **Kaynak & Dayanak:** `FUTUREWALLET_DUZELTME_PROMPTLARI.md` (v3); durum tespiti Graphify bilgi grafiği (`graphify-out/`, commit `45b1fcbe` + working tree) ve gerçek PocketBase (v0.40.6) test koşusu ile yapıldı.
> **Temel İlke (Prompt 0):** Yalnızca gerçek PocketBase entegrasyon testinden geçen maddeler `[x]` yapılabilir.
> **Doğrulama kanıtı:** `pytest tests` → **68/68 geçti** (tek oturum, gerçek PB sunucusu ile; final-review fix pass sonrası); `ruff check .` ve `ruff format --check .` temiz; `mypy api services config.py` (gevşek mod) hatasız; `python -c "import api.app"` başarılı.

---

## 📊 Genel Durum Özeti

| Alan / Konu | Gerçek Durum | TODO Durumu |
|---|---|---|
| Uygulama import / derleme | `api.app` sorunsuz import ediliyor; Pydantic model sırası düzeltildi | [x] Tamamlandı |
| `price_service.py` | SyntaxError giderildi; `get_price_on` PB→yfinance→ccxt zinciri çalışıyor | [x] Tamamlandı |
| PB Okuma Yolları | `services/pb.py` sarmalayıcıları (`get_full_list`/`get_one`/`update(id, body)`); tüm filtreler `client.filter(raw, params)` parametreli | [x] Tamamlandı |
| Auth & Kimlik Doğrulama | `X-User-ID` ve statik `API_TOKEN` tamamen kaldırıldı; `get_current_user` PB JWT doğrulaması + sahiplik kontrolleri canlı | [x] Tamamlandı |
| Şema & Erişim Kuralları | `pb_migrations/` 6 koleksiyon, RLS kuralları, benzersiz indeksler (`price_history(symbol,date)`, `macro_data(date)`), kullanıcı izolasyonu test edildi | [x] Tamamlandı |
| Test Altyapısı | Gerçek PB binary fixture'ları; PB'yi taklit eden MagicMock yok (yalnızca dış AI/HTTP mock'ları) | [x] Tamamlandı |
| Ledger | 409 yetersiz stok, kullanıcı bazlı kilit, ortalama maliyet, unrealized PnL, `cash_received` (DIVIDEND) | [x] Tamamlandı |
| AI Servisi | OpenRouter fallback zinciri + 502/503 semantiği + prompt injection etiketi | [x] Tamamlandı |
| Zamanlayıcı | APScheduler lifespan'a entegre, `ENABLE_SCHEDULER` ile kapatılabilir, EXPIRED otomatik job'ı | [x] Tamamlandı |
| Benchmark | `_upsert_to_pb` ve `_get_pb_price` düzeltildi (bozuk `get_list(params=)` kalıntısı temizlendi); alpha/gold birim testi YOK | [ ] Kısmen |
| Monte Carlo / Stres | Kabul testleri yazıldı ve geçiyor; singular kovaryans çökmesi ve boş portföye NaN üreten hatalar düzeltildi; 3/6/12 ay tek çağrıda | [x] Tamamlandı |
| Web Arayüzü | PB login akışı yok; `innerHTML` kullanımı ve inline style (CSP) duruyor | [ ] AÇIK |
| Temizlik & Bağımlılıklar | `futurewallet.db`, `db.py`, `sanitize_symbols.py`, `future_price.py` silindi; `google-genai`/`schedule` requirements'tan çıkarıldı, kilit uv ile yenilendi; v3+v4 çalışma commit'lendi | [x] Tamamlandı |

---

## 🏃 İş Listesi (Prompt 1 – Prompt 15)

### ✅ Prompt 1: Uygulamayı Ayağa Kaldır, Lint / CI / Bağımlılıklar
- [x] `api/app.py` Pydantic model tanımlama sırası düzeltildi.
- [x] `services/price_service.py` imza sözdizimi hatası giderildi.
- [x] Tanımsız isimler temizlendi (ruff F821 yok; `guess_asset_type` tek modüle taşındı).
- [x] `decision_to_dict` tekilleştirildi (yalnızca `services/decision_service.py`).
- [x] Kullanılmayan değişken/import temizliği (`ruff check .` 0 hata).
- [x] `ruff.toml` geçerli; `ruff check` + `ruff format --check` CI'da koşuyor.
- [x] SQLAlchemy `from db import` kaldırıldı; `db.py` silindi.
- [x] `lifespan` fail-closed (PB credential zorunluluğu `config.py` import'unda), koleksiyon doğrulama + migration koşumu, `/health` `pb: ok|down` alanı.
- [x] `pocketbase==0.17.3`, `apscheduler`, `httpx` sabitlendi; `requirements.txt` pip-compile kilidi.
- [ ] CI'ya ayrıca `python -c "import api.app"` duman adımı ekle (pytest zaten import ediyor; öncelik düşük).
- **Kabul Kriteri:** ✅ `import api.app` ve `pytest --collect-only` 0 hata; `ruff check .` temiz.

### ✅ Prompt 2: Gerçek PocketBase ile Test Altyapısı
- [x] `tests/conftest.py` gerçek PB v0.40.6 binary'si ile (otomatik indirme, geçici `--dir`, superuser, shutdown).
- [x] `pb_server`, `pb_clean` (koleksiyonlar + retrospektif hız sayaçları sıfırlanıyor), `make_user(email)` → `(user_id, JWT, user_client)`, `auth_headers` fixture'ları.
- [x] `api_client` gerçek PB'ye bağlı FastAPI TestClient.
- [x] Dış servisler için izole mock'lar (AI/HTTP); PB'yi taklit eden MagicMock kalmadı.
- [x] SQLAlchemy/SQLite tabanlı fixture ve testler silindi.
- [x] GitHub Actions: `pb_bin` önbellek adımı + `pytest -m pb` adımı.
- **Kabul Kriteri:** ✅ `pytest -m pb` gerçek PB'ye karşı koşuyor; tam suite 68/68 geçti.

### ✅ Prompt 3: PB Şema, Erişim Kuralları ve Migration
- [x] `pb_migrations/` repoda (users güncellemesi + macro_data, price_history, transactions, decisions, shadow_portfolios).
- [x] Bozuk `ensure_collections`/`create_collection` kodu silindi (`services/pocketbase.py` yok).
- [x] Sentiment enum'ı eşitlendi: `FOMO, STRATEGIC, PANIC, DIVIDEND, OPPORTUNITY`; `RISK_REDUCTION` API, servis, web şablon ve CSS'inden kaldırıldı; tek enum modülü `services/enums.py`.
- [x] `decisions`: `transaction` relation, `decision_date`, `outcome_*`, `target_hit` alanları.
- [x] `shadow_portfolios`: `user` relation zorunlu, `decision` relation `cascadeDelete=true`.
- [x] Benzersiz indeksler: `idx_price_history_symbol_date`, `idx_macro_data_date`.
- [x] Erişim kuralları migration'larda: kullanıcı bazlı list/view/create/update/delete; `macro_data`/`price_history` yalnız admin yazma; `users` createRule `null`.
- **Kabul Kriteri:** ✅ Migration + iki kullanıcılı izolasyon testleri (404) geçiyor; `RISK_REDUCTION` 422.

### ✅ Prompt 4: PB Dağıtımı, Sırlar ve Docker Compose
- [x] `docker/pocketbase/Dockerfile` + `entrypoint.sh` (PB 0.40.6, `pb_migrations` COPY, healthcheck).
- [x] `docker-compose.yml`: PB bağımsız servis; `pb_data` yalnız PB'de; `API_TOKEN` env satırı kaldırıldı.
- [x] Sırlar `${VAR:?required}`; `changeme` / `admin@example.com` yok.
- [x] `config.py`: PB credential'ları boşsa RuntimeError (fail-closed); `DATABASE_URL`/`GOOGLE_API_KEY`/`GEMINI_MODEL` temizlendi; `OPENROUTER_*` tanımlı.
- [x] `.env.example` PB + OpenRouter + scheduler değişkenleriyle güncel.
- **Kabul Kriteri:** ✅ `docker compose config` parola olmadan hata veriyor.

### ✅ Prompt 5: PB İstemci Katmanı
- [x] `services/pb.py`: `get_admin_client()` (thread-safe singleton, otomatik yenileme), `get_user_client(token)`, `list_all/get_one/create_record/update_record/delete_record`, `verify_collections`.
- [x] Tüm f-string filtreler `client.filter(raw, params)` parametreli hâle getirildi (ledger ×3, counterfactual, benchmark ×3, decision).
- [x] Kırık `get_list(params=...)` çağrıları düzeltildi (`benchmark_service._get_pb_price` — benchmarks'i hep boş döndüren sessiz yutma giderildi).
- [x] `transactions.get(id)` → `get_one(id)`; `update(record)` → `update(id, body)`.
- [x] `_get_holdings_at_date` sessiz `except: records = []` yutması kaldırıldı (log + Python taraflı yedek sorgu).
- [x] PB/ağ çağıran tüm endpoint handler'ları senkron `def`'e çevrildi; FastAPI bunları threadpool'da çalıştırıyor, event loop bloklanmıyor. `await` yalnız lifespan/middleware'de kaldı (commit `b5fca94`).
- **Kabul Kriteri:** ✅ liste/tekil uçlar testte dönüyor; filtre enjeksiyonu parametreli.

### ✅ Prompt 6: Kimlik Doğrulama ve Kullanıcı İzolasyonu
- [x] `X-User-ID` ve statik `API_TOKEN` mekanizması kaldırıldı (kod, config, `.env.example`, compose).
- [x] `get_current_user` bağımlılığı: `Authorization: Bearer <PB_JWT>` → `users.auth_refresh()` (geçersiz → 401); `CurrentUser(id, email, token, pb)`; kullanıcı bazlı PB istemcisi `request.state`'te.
- [x] Tekil kaynak uçlarında sahiplik kontrolü → 404 (decisions GET/PUT/DELETE/close/target-check/evaluate/retrospective, shadow-positions, transactions void).
- [x] Liste/özet uçları çağıran kullanıcıya filtreli (`/api/decisions` sızıntısı bu turda kapatıldı; `/api/counterfactual` sahiplik kontrolü eklendi).
- [x] Rate limit kullanıcı + endpoint(karar) bazında: retrospektif 60 sn'de 1; `reset_rate_limits()` ile testlerde sıfırlanabilir.
- [x] 64 KB gövde limiti middleware'i (Content-Length → 413).
- [x] CORS/TrustedHost + üretim OpenAPI ayarı (`DEBUG=false` → `/docs`, `/redoc`, `/openapi.json` kapalı).
- **Kabul Kriteri:** ✅ Token yok → 401; A→B → 404; aynı karar 2. retrospektif → 429; 65 KB → 413 (testlerle kanıtlı).

### ✅ Prompt 7: Ledger + Decision Düzeltmeleri
- [x] SELL/CASH_OUT yetersiz stok/bakiye → `InsufficientBalanceError` → HTTP 409.
- [x] Kullanıcı bazlı süreç içi kilit (`_user_locks`) altında stok kontrolü + kayıt.
- [x] `void_transaction` soft-delete (`voided=true`), tekrarlı çağrıda aynı durum (idempotent).
- [x] Snapshot: `average_cost`, `unrealized_pnl`/`pnl_pct`, **`cash_received`** (DIVIDEND nakit birikimi; nakit için fiyat araması yapılmaz) — bu turda eklendi.
- [x] `decision_date` gelecek tarih → **422** (Pydantic validator; servis tarafı ValueError koruması da duruyor); transaction bağlantısı ve boş sayısal → `None`.
- [x] Route sırası: `/api/decisions/stats` `{decision_id}`'den önce tanımlı.
- [x] Hatalar standart HTTP kodlarıyla (404/409/422/400/500; `{"error"}` 200 kalıntısı `target-check`/`counterfactual` uçlarında JSONResponse 404'e bağlandı).
- **Kabul Kriteri:** ✅ 2 BUY + 1 SELL ortalama maliyet testi, aşan SELL 409, void snapshot dışı, stats 200, DIVIDEND `cash_received` — hepsi test suite'inde geçiyor.

### ✅ Prompt 8: AI Servisi: OpenRouter + Hata Semantiği
- [ ] `google-genai` paketi `requirements.in`/`requirements.txt`'den çıkarılacak (kod artık kullanmıyor; bağımlılık çöpü — Prompt 15 ile birlikte).
- [x] OpenRouter istemcisi: `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `OPENROUTER_MODELS` fallback zinciri.
- [x] Zaman aşımı / 5xx / 429 → sonraki model; tümü düşerse 502; anahtar yoksa 503 (`AIUnavailableError`).
- [x] Prompt güvenliği: `<user_input>` etiketi, kaçırma, 2000 karakter sınırı; "Yatırım tavsiyesi değildir" uyarısı.
- [x] Retrospektif bağlamı (karar tarihi/vade fiyatı, duygu) + başarıda `status: REVIEWED` güncellemesi.
- **Kabul Kriteri:** ✅ Fallback/502/503 testleri (`tests/test_ai_service.py`) geçiyor.

### 🟠 Prompt 9: Price Service, Time-Travel ve Value-Series — tek eksik para birimi
- [x] `price_service` sözdizimi/imza düzeltmeleri; PB cache `list_all` ile.
- [x] `get_price_on(symbol, asset_type, on_date)`: PB → yfinance → ccxt; hafta sonu/tatil önceki iş günü; yoksa `None` + `missing_prices`.
- [x] Ledger `price_fn` imzası `(symbol, asset_type, on_date)`.
- [x] Time-travel hesapları (`value_at_start`/`value_at_target`/nominal-yüzde PnL).
- [x] `/api/portfolio/value-series`: 400 nokta limiti (422), gerçek 7 günlük haftalık adım, `timedelta` importlu.
- [x] `/api/portfolio/real-valuation`: `nominal_end` yoksa `date_to` snapshot'ı kullanılıyor.
- [ ] **Para birimi dinamik değil:** `value-series` yanıtında `"currency": "TRY"` sabit; `simulation_service` dinamik `currency` üretiyor. Varlık tabanına göre USD/TRY seçimi bağlanmalı (P14 seçiciyle de bağlantılı).
- **Kabul Kriteri:** ✅ value-series 422 limiti testte; cache isabeti dış çağı kırpıyor.

### 🟠 Prompt 10: Gölge Portföy — `track_shadow` gerçeğe bağlanacak
- [x] `counterfactual_service` yeni PB katmanı + `CurrentUser` mimarisinde; endpoint'ler kullanıcı filtreli.
- [ ] `track_shadow=True` hâlâ **`quantity=1.0` ve `entry_price=body.target_price`** sahte değeriyle gölge açıyor (`api/app.py:692`); SELL'e bağlı transaction'ın gerçek miktar/fiyatı kullanılmalı (kararın `transaction_id` relation'ından çözülür).
- [x] `HELD_INSTEAD`/`BOUGHT_INSTEAD` tipleri + fırsat maliyeti (gölge − gerçek) hesabı serviste.
- [x] `what_if_scenario` gerçek pozisyon/tarihsel fiyat bağlı (sahte placeholder serviste kalmadı).
- [x] İzolasyon: başkasının gölgesine erişim 404; karar silinince `cascadeDelete` ile gölgeler siliniyor (`test_decision_and_shadow_portfolio_cascade` geçiyor).
- **Kabul Kriteri:** ⚠️ Kısmen — miktar/fiyat bağı gerçek veriye bağlanınca tamamlanacak.

### 🟠 Prompt 11: Benchmark, Enflasyon, Zamanlayıcı — test eksiği
- [x] `_upsert_to_pb` admin client + `date` benzersiz indeksi ile; sentetik sahte veri yazımı yok.
- [x] EVDS/FRED anahtarsızken sahte veri üretmiyor (açık `None` / `data_quality` bayrağı).
- [x] `gold_try_gram = (GC=F_USD / 31.1035) × USDTRY` hesaplaması serviste.
- [x] APScheduler lifespan'de; günlük benchmark + `auto_close_expired_decisions`; `ENABLE_SCHEDULER=false` ile kapanıyor.
- [x] `/api/portfolio/benchmarks` portföy/altın/S&P/TÜFE + alpha döndürüyor (`_get_pb_price` hatası bu turda düzeltildi — önceden hep boştu).
- [ ] **Kabul kriteri birim testleri eksik:** `gold_try_gram`, alpha ve `_upsert_to_pb` tek-kayıt davranışı için deterministik testler yazılmalı.

### ✅ Prompt 12: Monte Carlo ve Stres Testi
- [x] `stress_test` `session` parametresi kaldırıldı; uçlar JWT kimliğiyle.
- [x] `monte_carlo_endpoint` tanımsız `request`/`_guess_asset_type` hataları giderildi; 15 varlık / 20.000 simülasyon üst sınırları (422) uygulanıyor ve test edildi.
- [x] `market_crash` şok kalıcılığı testi: %50 özel şokta vade medyanı ≈ −%50 (`tests/test_simulation_stress.py`).
- [x] Varlık sınıfı duyarlılık tablosu `DEFAULT_STRESS_SCENARIOS.asset_impacts` içinde; `worst_case`/`loss_pct` sözleşmesi testli.
- [x] 63/126/252 çoklu horizon tek çağrıda (`days` verilmezse `horizons` sözlüğü döner) + 40 kutu histogram + p5/p50/p95; sabit mu/sigma ile 20k yolda medyan teorik GBM değerine %2 içinde.
- [x] Cholesky determinizm ve tekil kovaryans dayanıklılığı: eigen-değer clipping `0.0` yerine `1e-12`'e çekildi — verisi olmayan varlıklarda `LinAlgError` çökmesi düzeltildi; aynı seed aynı çıktı.
- [x] Boş portföyde `use_ledger` miktarı `0`'a düşürüp NaN üretiyordu; snapshot döngü dışına alındı ve istekte gelen miktar korunuyor.
- **Kabul Kriteri:** ✅ `tests/test_simulation_stress.py` 6/6 geçti.

### ✅ Prompt 13: Karar Günlüğü: Stats, Outcome, EXPIRED
- [x] `DELETE /api/decisions/{id}` sahiplik + PB cascade (testli).
- [x] Vadesi dolmuş kararlarda `outcome_price`, `outcome_return_pct`, `target_hit` `price_service` üzerinden dolduruluyor (`evaluate_decision`).
- [x] `POST /api/decisions/{id}/evaluate` manuel değerlendirme ucu.
- [x] `GET /api/decisions/stats` sentiment/status sayıları + outcome ortalama/medyan; `n < 3` → `insufficient_data: true`.
- [x] Zamanlayıcı job'ı vadesi geçmiş OPEN kararları EXPIRED yapıyor.
- **Kabul Kriteri:** ✅ Route/istatistik testleri geçiyor.

### ❌ Prompt 14: Web Arayüzü: PB Girişi ve Paneller (hepsi AÇIK)
- [ ] Giriş ekranı `/web/login`: `users/auth-with-password`, sessionStorage'da PB JWT, `auth-refresh`, 401 → login yönlendirmesi. **Mevcut `app.js` hâlâ `sessionStorage.apiToken` (eski statik token) gönderiyor; P6 sonrası tüm web API çağrıları 401 alacak — P14, P6'nın planlı ardılıdır.**
- [ ] `apiFetch`'e Bearer PB JWT entegrasyonu (login akışıyla birlikte).
- [ ] CSP: `decision_form.html` inline style'ları CSS'e; Chart.js yerel vendor veya SRI (`dashboard.html` CDN kullanıyor).
- [ ] `app.js:379` `card.innerHTML = html` → sunucu verisi `textContent`/DOM API ile basılmalı (XSS).
- [ ] Paneller: Time-Travel, Karar Günlüğü (Retrospektif/Kapat/Sil), Gölge Portföy, Stres Testi (histogram + p5/p50/p95 + AI anlatı), İşlem Ekleme/Geçmişi.
- [ ] USD/TRY seçicisini API `currency` alanına bağla (P9'daki dinamik para birimiyle eş zamanlı).
- [ ] "Yatırım tavsiyesi değildir" uyarısı tüm altbilgilerde ve AI çıktılarında.
- **Kabul Kriteri:** ❌ Login → dashboard akışı CSP/konsol hatasız kurulamadı.

### 🟡 Prompt 15: Temizlik, Bağımlılıklar, Doküman Senkronizasyonu
- [x] `futurewallet.db`, `db.py`, `scripts/sanitize_symbols.py`, `services/future_price.py` silindi (çalışma ağacında).
- [x] Kod tekrarı giderildi: `_guess_asset_type`/`guess_asset_type` tek modül (`services/asset_types.py`), `decision_to_dict` tekilliği.
- [x] Doküman senkronu tamamlandı (2026-11-16): `TODO.md` v4, `GUNCEL_IS_PLANI.md` v4, `README.md` (PB JWT auth, uv kurulumu, env tablosu, test adımları), `MVP.md` (durum notu, mimari ağaç, sprint durumları); `SPRINT_PLANI_KALANLAR.md` geçersizlik banner'ı ile arşivlendi.
- [x] `requirements.in` sadeleştirildi (`google-genai`, `schedule`, `sqlalchemy`, kullanılmayan `pytest-mock` çıkarıldı); `requirements.txt` `uv pip compile` ile yeniden üretildi (86 paket).
- [ ] CI'ın uzaktan (GitHub Actions) yeşil koşması: push sonrası `gh run list` ile doğrulanacak.
- [x] Tüm v3+v4 çalışma commit'lendi: `af9d5e1` (P2–P7 + P15 bağımlılık temizliği), `b5fca94` (P5 threadpool), P12 testleri ayrıca commit'lendi; çalışma ağacı temiz.
- **Kabul Kriteri:** ⚠️ Kısmen — repoda `.db`/`db.py` kalmadı, `sqlalchemy`/`google.genai` referansı yok, dokümanlar v4'e senkron, commit tamam; tek açık: CI'ın uzaktan yeşil koşması push sonrası doğrulanmalı.

---

## 📋 Hızlı Kontrol Listesi

```text
[x] 1. python -c "import api.app" hatasız.
[x] 2. ruff check . + ruff format --check . sıfır hata.
[x] 3. Boş PB + migration → 6 koleksiyon; izolasyon testleri geçiyor.
[x] 4. İki farklı kullanıcı birbirinin verisini okuyamıyor (404).
[x] 5. Repoda changeme / admin@example.com / API_TOKEN yok.
[x] 6. Snapshot 2 işlem sonrası dolu; cash_received DIVIDEND'i sayıyor.
[x] 7. Fazla SELL → 409 Conflict.
[ ] 8. Time-travel BTC 30k→60k %100 PnL senaryo testi yok (fonksiyon doğrulanmadı).
[x] 9. OpenRouter fallback 502/503 semantiği testli.
[x] 10. market_crash %50 kalıcı şok testi geçiyor.
[ ] 11. EXPIRED zamanlayıcı job'ı PB üzerinde uçtan uca test edilmedi.
[ ] 12. Web UI login akışı yok (P14).
[ ] 13. mypy gevşek mod temiz; ancak P10/P11/P12 kabul kriterlerinin bir kısmı hâlâ test edilmedi.
```

## 🔜 Öncelik Sırası

1. **P10 `track_shadow` gerçek miktar/fiyat** (küçük, doğruluk).
2. **P11 gold/alpha birim testi**, P9 dinamik currency.
3. **P14 web arayüzü** (login → paneller; P6 sonrası web akışının çalışması için zorunlu — en büyük kalan dilim).
4. **P15 kalanı:** push sonrası CI'ın uzaktan yeşil koştuğunun doğrulanması.
