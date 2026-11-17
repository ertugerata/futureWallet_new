# FutureWallet – TODO & Sprint Takip Listesi (v5 – 2026-11-17 doğrulanmış durum)

> **Kaynak & Dayanak:** Durum tespiti Graphify bilgi grafiği (`graphify-out/`) ve gerçek PocketBase (v0.40.6) test koşusu ile yapıldı. Kapanan v3 denetiminin ham prompt dosyaları (`FUTUREWALLET_DUZELTME_PROMPTLARI.md`, `SPRINT_PLANI_KALANLAR.md`, `GUNCEL_IS_PLANI.md`) 2026-11-17'de arşivden kaldırıldı — geçmişleri git log'da.
> **Temel İlke (Prompt 0):** Yalnızca gerçek PocketBase entegrasyon testinden geçen maddeler `[x]` yapılabilir.
> **Doğrulama kanıtı:** `pytest tests` → **101/101 geçti** (tek oturum, gerçek PB sunucusu ile; P10+P11+P14 + P9-currency + EXPIRED-e2e + review-minörleri + PB şema-bütünlüğü turları dahil); `ruff check .` ve `ruff format --check .` temiz; `mypy api services config.py web_app` (gevşek mod) hatasız; `python -c "import api.app"` başarılı (CI'da ayrı duman adımı). P14 + para birimi seçicisinin MC `currency` alanına bağlanması canlı tarayıcı E2E ile doğrulandı (gerçek PB + uvicorn).

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
| Zamanlayıcı | APScheduler lifespan'a entegre, `ENABLE_SCHEDULER` ile kapatılabilir; EXPIRED job'ı uçtan uca PB testli (`tests/test_expiry_e2e.py`) | [x] Tamamlandı |
| Benchmark | `_upsert_to_pb`/`_get_pb_price` düzeltmeleri + `gold_try_gram` şema migration'ı + `refresh_macro` job'ı + `alpha` çıktısı; tek-kayıt/gold/alpha birim testleri geçiyor | [x] Tamamlandı |
| Monte Carlo / Stres | Kabul testleri yazıldı ve geçiyor; singular kovaryans çökmesi ve boş portföye NaN üreten hatalar düzeltildi; 3/6/12 ay tek çağrıda | [x] Tamamlandı |
| Web Arayüzü | PB login akışı + Bearer JWT + `auth-refresh` canlı tarayıcı E2E ile doğrulandı; innerHTML yok, inline style/script yok, Chart.js SRI, CSP `connect-src` PB origin'i içeriyor; MC `currency` alanı para birimi seçicisini otomatik USD/TRY bağlıyor | [x] Tamamlandı |
| Temizlik & Bağımlılıklar | `futurewallet.db`, `db.py`, `sanitize_symbols.py`, `future_price.py` silindi; `google-genai`/`schedule`/`sqlalchemy`/`pytest-mock` requirements'tan çıkarıldı, kilit uv ile yenilendi; dokümanlar v5; CI 5/5 yeşil (run `44056500353`) | [x] Tamamlandı |

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
- [x] CI'da ayrıca `python -c "import api.app"` duman adımı var (test job'ı, dummy PB env ile — 2026-11-17).
- **Kabul Kriteri:** ✅ `import api.app` ve `pytest --collect-only` 0 hata; `ruff check .` temiz.

### ✅ Prompt 2: Gerçek PocketBase ile Test Altyapısı
- [x] `tests/conftest.py` gerçek PB v0.40.6 binary'si ile (otomatik indirme, geçici `--dir`, superuser, shutdown).
- [x] `pb_server`, `pb_clean` (koleksiyonlar + retrospektif hız sayaçları sıfırlanıyor), `make_user(email)` → `(user_id, JWT, user_client)`, `auth_headers` fixture'ları.
- [x] `api_client` gerçek PB'ye bağlı FastAPI TestClient.
- [x] Dış servisler için izole mock'lar (AI/HTTP); PB'yi taklit eden MagicMock kalmadı.
- [x] SQLAlchemy/SQLite tabanlı fixture ve testler silindi.
- [x] GitHub Actions: `pb_bin` önbellek adımı + `pytest -m pb` adımı.
- **Kabul Kriteri:** ✅ `pytest -m pb` gerçek PB'ye karşı koşuyor; tam suite 91/91 geçti.

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
- [x] `google-genai` paketi `requirements.in`/`requirements.txt`'den çıkarıldı (P15 turunda üretilen kilitte yalnız kaldırma notu satırı duruyor; bağımlılık yok).
- [x] OpenRouter istemcisi: `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `OPENROUTER_MODELS` fallback zinciri.
- [x] Zaman aşımı / 5xx / 429 → sonraki model; tümü düşerse 502; anahtar yoksa 503 (`AIUnavailableError`).
- [x] Uç nokta eşlemesi (P14 E2E'de bulundu): `/retrospective` ve `/simulation/narrative` yapılandırılmış `api_available:false`/`error` sözlüklerini artık **503/502 HTTP** kodlarına çeviriyor (test: `test_retrospective_endpoint_503_without_api_key`, `test_narrative_endpoint_503_without_api_key`).
- [x] Prompt güvenliği: `<user_input>` etiketi, kaçırma, 2000 karakter sınırı; "Yatırım tavsiyesi değildir" uyarısı.
- [x] Retrospektif bağlamı (karar tarihi/vade fiyatı, duygu) + başarıda `status: REVIEWED` güncellemesi.
- **Kabul Kriteri:** ✅ Fallback/502/503 testleri (`tests/test_ai_service.py`) geçiyor.

### ✅ Prompt 9: Price Service, Time-Travel ve Value-Series — tamamlandı
- [x] `price_service` sözdizimi/imza düzeltmeleri; PB cache `list_all` ile.
- [x] `get_price_on(symbol, asset_type, on_date)`: PB → yfinance → ccxt; hafta sonu/tatil önceki iş günü; yoksa `None` + `missing_prices`.
- [x] Ledger `price_fn` imzası `(symbol, asset_type, on_date)`.
- [x] Time-travel hesapları (`value_at_start`/`value_at_target`/nominal-yüzde PnL).
- [x] `/api/portfolio/value-series`: 400 nokta limiti (422), gerçek 7 günlük haftalık adım, `timedelta` importlu.
- [x] `/api/portfolio/real-valuation`: `nominal_end` yoksa `date_to` snapshot'ı kullanılıyor.
- [x] **Para birimi dinamik:** `services/asset_types.py` `base_currency`/`infer_portfolio_currency` (BIST/TL → TRY, diğer tabanlar → USD; karışık sepette çoğunluk, eşitlik/boş → TRY, `shortcut:` notlu); `value-series` tutulan sembollerden, Monte Carlo `asset_symbols`'dan `currency` üretiyor — `tests/test_price_valuation.py` 5 yeni test + `test_singular_covariance` USD assertion'ı.
- **Kabul Kriteri:** ✅ value-series 422 limiti testte; cache isabeti dış çağı kırpıyor.

### 🟡 Prompt 10: Gölge Portföy — ✅ tamamlandı
- [x] `counterfactual_service` yeni PB katmanı + `CurrentUser` mimarisinde; endpoint'ler kullanıcı filtreli.
- [x] `track_shadow=True` artık bağlı SELL işlemiyle gerçek açılır: `transaction_id`'den miktar+fiyat okunur; işlem ait değilse/başka sembolse/SELL değilse 400 (RED→GREEN: `test_track_shadow_uses_linked_transaction_quantity_and_price`, `test_track_shadow_rejects_foreign_transaction_link`). `transaction_id` verilmezse 1.0/target_price fallback (kodda `shortcut:` notu).
- [x] `HELD_INSTEAD`/`BOUGHT_INSTEAD` + fırsat maliyeti (gölge − gerçek) serviste.
- [x] `what_if_scenario` gerçek pozisyon/tarihsel fiyat bağlı.
- [x] İzolasyon: başkasının gölgesine erişim 404; cascade silme testli.
- **Kabul Kriteri:** ✅ 10 BTC 50k satış → 80k'de +300k hesabı servis testiyle doğrulanmış; kullanıcı izolasyonu PB testli.

### ✅ Prompt 11: Benchmark, Enflasyon, Zamanlayıcı — kabul testleri eklendi
- [x] `_upsert_to_pb` admin client + `date` benzersiz indeksi; **test: aynı tarih iki upsert → tek kayıt, ikinci değer güncel** (`test_upsert_same_date_keeps_single_record`).
- [x] EVDS/FRED anahtarsız sahte veri üretmiyor.
- [x] `gold_try_gram` **şema düzeltmesi:** `pb_migrations/1794054596` `gold_try` → `gold_try_gram` (PB, kodun yazdığı 14 `gold_try_gram` alanını şemada olmadığı için sessizce düşürüyordu); formül birim testi `compute_gold_try_gram` (2650 USD/ons, 34.5 USD/TL) geçiyor.
- [x] `_get_pb_price` `date <=` sınırı gün sonuna (`23:59:59.999Z`) düzeltildi — midnight kayıtlı macro satırları hiç bulunamıyordu (canlı E2E'de tespit).
- [x] APScheduler: `expire_decisions` + **yeni `refresh_macro` (24h)** job'ları; her ikisi de testli (`test_scheduler_registers_daily_macro_job`).
- [x] `GET /api/portfolio/benchmarks`: `compare_to_benchmark` artık **`alpha` (portföy − benchmark)** sözlüğü döndürüyor; altın/gram-altın/S&P satırlarıyla deterministik PB testi (`test_compare_to_benchmark_alpha`).
- **Kabul Kriteri:** ✅ upsert tek kayıt + gold/alpha birim testleri PB üzerinde geçiyor.

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

### ✅ Prompt 14: Web Arayüzü: PB Girişi ve Paneller
- [x] Giriş ekranı `/web/login` (`templates/login.html` + `static/login.js`): PB `auth-with-password`, token → `sessionStorage.pb_token`, açılışta `auth-refresh`, geçersiz/süresi dolmuş token → login yönlendirmesi (canlı tarayıcı E2E ile doğrulandı).
- [x] Tüm API çağrıları (`api()` sarmalayıcısı) Bearer PB JWT gönderir; 401 → login. (Eski `apiFetch` hiç Authorization taşımıyordu; GET parametreleri de `opts.params` yerine yanlış yerden geçiyordu — ikisi de düzeltildi.)
- [x] CSP uyumu: inline `<script>` ve inline `style=` tamamen kaldırıldı (`decision_form` sayfası `static/decision_form.js`'e taşındı); Chart.js SRI (`sha384-e6nUZ...`) ile yükleniyor; `connect-src`'e PocketBase origin'i eklendi (PB JWT akışı buna muhtaçtı — canlı testte CSP ilk başta login fetch'ini bloke etti, bulunup düzeltildi).
- [x] Sunucu verisi artık `innerHTML` ile değil DOM API (`textContent`/`createElement`/`replaceChildren`) ile basılıyor; `app.js` sıfırdan yazıldı (eski dosya JS içinde gömülü CSS blokları yüzünden sözdizimi hatası içeriyordu).
- [x] Paneller: Snapshot + **Time-Travel** (T_start/T_target), Karar Günlüğü (AI Retrospektif / Kapat / Sil butonları, `textContent` ile güvenli AI gösterimi, duygu özet kartı, outcome kolonu), Gölge Portföy ("Ne olurdu?" kıyaslaması + manuel BOUGHT_INSTEAD ekleme + silme), **İşlem Ekleme + İşlem Geçmişi (void)**, Monte Carlo (40 kutu canvas histogram + p5/p50/p95 kartları), Stres Testi (senaryo tablosu + en kötü vurgusu), AI risk anlatısı.
- [x] USD/TRY seçicisi API `currency` alanına bağlı: Monte Carlo cevabındaki `currency` `#currencySelect`'i ve `window._currency`'yi otomatik ayarlayıp tüm `.value-display` alanlarını yeniden biçimliyor (alan yoksa eski davranış korunur). Canlı tarayıcı E2E: `assets=BTC` simülasyonu → seçici USD, kartlar `$` formatında, konsol hatası yok.
- [x] "Yatırım tavsiyesi değildir" uyarısı dashboard ve karar sayfası altbilgilerinde + AI anlatısı altında.
- **Kabul Kriteri:** ✅ E2E (gerçek PB + tarayıcı): token'sız → `/web/login`; giriş → dashboard verili; işlem ekleme snapshot'ı günceller (nakit kovası 5500 = 2×250 temettü + 5000 CASH_IN doğru); MC 200 + histogram + stres tablosu (`market_crash` en kötü); AI'sız 503'in dürüst mesajı; çıkış → token temizlendi; konsol hatası yok.

### 🟡 Prompt 15: Temizlik, Bağımlılıklar, Doküman Senkronizasyonu
- [x] `futurewallet.db`, `db.py`, `scripts/sanitize_symbols.py`, `services/future_price.py` silindi (çalışma ağacında).
- [x] Kod tekrarı giderildi: `_guess_asset_type`/`guess_asset_type` tek modül (`services/asset_types.py`), `decision_to_dict` tekilliği.
- [x] Doküman senkronu tamamlandı (2026-11-16): `TODO.md` v4, `GUNCEL_IS_PLANI.md` v4, `README.md` (PB JWT auth, uv kurulumu, env tablosu, test adımları), `MVP.md` (durum notu, mimari ağaç, sprint durumları); `SPRINT_PLANI_KALANLAR.md` geçersizlik banner'ı ile arşivlendi.
- [x] `requirements.in` sadeleştirildi (`google-genai`, `schedule`, `sqlalchemy`, kullanılmayan `pytest-mock` çıkarıldı); `requirements.txt` `uv pip compile` ile yeniden üretildi (86 paket).
- [x] CI uzaktan yeşil: run `44056500353` (commit `7103827`) — Ruff Lint, Mypy, Pytest (gerçek PB binary indirmeli), **Pip Audit** (`soupsieve` 4.1.1 bumpı sonrası temiz), Docker Build; 5/5 success.
- [x] Tüm v3+v4 çalışma commit'lendi: `af9d5e1` (P2–P7 + P15 bağımlılık temizliği), `b5fca94` (P5 threadpool), P12 testleri ayrıca commit'lendi; çalışma ağacı temiz.
- **Kabul Kriteri:** ✅ Repoda `.db`/`db.py` yok; `sqlalchemy`/`google.genai`/`schedule` referansı ve paket bağımlılığı yok; dokümanlar v4; tüm çalışma commit'li; CI yeşil.

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
[x] 8. Time-travel 5 BTC 30k→60k %100 PnL senaryo testi geçiyor (`test_time_travel_double_price_yields_100_pct_pnl`).
[x] 9. OpenRouter fallback 502/503 semantiği testli.
[x] 10. market_crash %50 kalıcı şok testi geçiyor.
[x] 11. EXPIRED job'ı PB üzerinde uçtan uca testli (`tests/test_expiry_e2e.py`: price_history cache seed → `auto_close_expired_decisions()` → EXPIRED + outcome_price/%20; vadesi gelmemiş karar OPEN kalıyor).
[x] 12. Web UI login → dashboard akışı CSP/konsol hatası olmadan tarayıcıda doğrulandı (P14).
[x] 13. P1–P14 kabul testlerinin tamamı geçiyor (100/100, 2026-11-17; kalan madde yok).
```

## 🔜 Öncelik Sırası

Kalan iş yok — üç madde de 2026-11-17 turunda kapandı (`feat/mvp-remaining-work`, plan: `docs/plans/2026-11-17-mvp-remaining-work.md`):

1. ~~P9 dinamik currency~~ → `base_currency`/`infer_portfolio_currency` + value-series/MC/web-çıkışı bağlama.
2. ~~EXPIRED job uçtan uca PB testi~~ → `tests/test_expiry_e2e.py`; test iki sessiz hatayı buldu ve düzeltildi: `_parse_pb_date` boşluklu PB timestamp/`created` datetime karşısında None'a düşüyordu (job hiçbir karar göremiyordu) ve `evaluate_decision` giriş temeli olarak `created` kullanıyordu (geçmiş kararların P&L'i bugünkü dış fiyattan hesaplanıyordu — `decision_date` temele alındı).
3. ~~Review minörleri~~ → shadow-positions create karar sahipliği (yabancı/olmayan karar → 400); PB kayıt ID'leri `^[a-z0-9]{15}$` path/query/body doğrulaması (biçimsiz → 422, servise inmez).
4. ~~Sessiz alan düşürme denetimi~~ (e2e bulgusunun sınıfı, 2026-11-17 ek tur) → tüm PB write payload'ları 6 koleksiyon şemasına karşı denetlendi: `macro_data` şemasına `source`/`is_estimate` eklendi (migration `1794054597`; `_upsert_to_pb` yazıkları artık gerçekten kalıcı — RED→GREEN testi `test_upsert_persists_source_and_is_estimate`) ve okunmayan şema-dışı `user_id` threading'i ölü kod olarak kaldırıldı; `price_history.asset_type` yazımı (şemada yok, hiçbir okuyucu yok) `_save_to_cache`'den ve test seed'lerinden çıkarıldı.
