# FutureWallet – Güncel İş Planı (v3 / PocketBase + FastAPI + OpenRouter)

> **Kaynak & Dayanak:** `FUTUREWALLET_DUZELTME_PROMPTLARI.md` (v3), `TODO.md` ve `SPRINT_PLANI_KALANLAR.md`.
> **Temel Kural (Prompt 0):** Yalnızca **gerçek PocketBase (v0.40.6)** entegrasyon testini geçen maddeler tamamlandı (`[x]`) sayılır. Kodda yazılmış görünse dahi derleme/import hatası veren veya gerçek PB'de 500/TypeError üreten maddeler **AÇIK** (`[ ]`) olarak listelenmiştir.

---

## 📊 Mevcut Durum Analizi (Doğrulanan Bulgular)

| Alan / Modül | Mevcut Durum | Neden Açık? |
|---|---|---|
| **Uygulama İçe Aktarımı** | ❌ Başarısız | `api/app.py`: `TransactionCreateRequest` endpoint'ten sonra tanımlı; pytest 45 toplama hatası veriyor |
| **`price_service.py`** | ❌ Başarısız | `SyntaxError`: `get_prices_in_range` fonksiyonunda varsayılanlı parametre zorunlulardan önce |
| **PocketBase Okuma Yolları** | ❌ Kırık | `get_list(params=...)` TypeError veriyor; `update(record)` hatalı; `transactions.get(id)` yok |
| **PB Şema ve Kurallar** | ❌ Kırık | `ensure_collections` PB v0.40.6'da HTTP 400 hatası veriyor; anonim okuma açık, kullanıcı kuralı yok |
| **Kimlik Doğrulama** | ❌ Eksik | Sahte `X-User-ID` ve statik `API_TOKEN` var; PB JWT auth ve kullanıcı izolasyonu yok |
| **Test Altyapısı** | ❌ Eksik | Testler in-memory SQLite ve etkisiz MagicMock'lara dayanıyor; gerçek PB test altyapısı yok |
| **Ledger Mantığı** | ⚠️ Eksik | Yetersiz stokta SELL için 409 Conflict yok; DIVIDEND `cash_received` eksik |
| **AI Entegrasyonu** | ⚠️ Eksik | OpenRouter yerine hatalı `genai` importu; 502/503 hata semantiği eksik |
| **Zamanlayıcı (Scheduler)**| ❌ Yok | APScheduler entegre edilmemiş; `auto_close_expired_decisions` çağrılmıyor |
| **Web Arayüzü** | ⚠️ Eksik | Giriş akışı / token saklama yok (tüm API istekleri 401); inline style CSP ihlali var |
| **Depo Kalıntıları** | ⚠️ Eksik | `futurewallet.db` git'te duruyor; `db.py` ve SQLAlchemy referansları temizlenmedi |

---

## 🗺️ Prompt Bazlı Güncel İş Planı (P0 – P15)

### 🔴 Prompt 1: Uygulamayı Ayağa Kaldır, Lint / CI / Bağımlılıklar (Kritik)
- [ ] `api/app.py` Pydantic model tanımlama sırasını düzelt (`TransactionCreateRequest` endpoint'ten önce tanımlanmalı).
- [ ] `services/price_service.py` imza hatasını gider (`start_date, end_date, asset_type="crypto"`).
- [ ] Tanımsız isimleri düzelt (`timedelta`, `request`, `_guess_asset_type`, `Optional`).
- [ ] Çift tanımlı `decision_to_dict` fonksiyonunu tekleştir (yalnızca `services/decision_service.py` içinde).
- [ ] Kullanılmayan değişken ve importları temizle (`user_id`, `delete_decision`, `db.py` importları).
- [ ] `ruff.toml` dosyasını geçerli hâle getir (`line-length = 100` en üst seviyeye taşınmalı; `[format]` düzeltilmeli).
- [ ] `api/app.py` içinden `db` / SQLAlchemy (`from db import get_session`) importunu kaldır.
- [ ] `lifespan`: fail-closed yapılandırma doğrulaması, PB bağlantı ve koleksiyon kontrolü ekle; `/health` yanıtına `pb: ok|down` ekle.
- [ ] `requirements.txt`: `pocketbase==0.17.3`, `apscheduler`, `httpx` ekle; `pip-compile` ile kilit dosyası oluştur.
- [ ] CI pipeline'ına duman testi (`python -c "import api.app"`), ruff, mypy, pytest, pip-audit ekle.

---

### 🔴 Prompt 2: Gerçek PocketBase ile Test Altyapısı (Kritik Altyapı)
- [ ] `tests/conftest.py` dosyasını gerçek PocketBase (v0.40.6) binary'si ile çalışacak şekilde yeniden yaz.
- [ ] `pb_server` fixture'ı: PB v0.40.6 binary otomatik indirme, checksum doğrulama, geçici `--dir`, superuser oluşturma, test bitiminde kapatma.
- [ ] `pb_clean` fixture'ı: her test öncesi/sonrası koleksiyonları temizleme.
- [ ] `make_user(email)` fixture'ı: `(user_id, JWT)` üretimi.
- [ ] `api_client` fixture'ı: gerçek PB'ye bağlı FastAPI TestClient (PB mock'ı kaldırılacak).
- [ ] Dış servisler (yfinance, ccxt, OpenRouter, EVDS, FRED) için izole mock fixture'ları.
- [ ] SQLAlchemy / in-memory SQLite (`Base`, `db.py`) tabanlı eski fixture ve testleri sil.
- [ ] GitHub Actions'a PB binary önbellekleme ve `pytest -m pb` adımı ekle.

---

### 🔴 Prompt 3: PB Şema, Erişim Kuralları ve Migration (Kritik Güvenlik)
- [ ] PB Dev admin arayüzü ile geçerli şemaları oluştur ve `pb_migrations/` dizinini repoya ekle.
- [ ] `services/pocketbase.py` içindeki bozuk `ALL_COLLECTIONS`, `create_collection`, `ensure_collections` kodunu sil.
- [ ] Sentiment değerlerini eşitle: `FOMO`, `STRATEGIC`, `PANIC`, `DIVIDEND`, `OPPORTUNITY`. `RISK_REDUCTION`'ı tüm koddan kaldır.
- [ ] `decisions`: `transaction` relation alanı, `decision_date` (date), `outcome_*`, `target_hit` alanlarını ekle.
- [ ] `shadow_portfolios`: `user` relation (zorunlu), `decision` relation (cascadeDelete=true).
- [ ] Benzersiz indeksler: `price_history(symbol, date)`, `macro_data(date)`.
- [ ] API Kuralları: `transactions`, `decisions`, `shadow_portfolios` için `user = @request.auth.id` zorunlu kıl.
- [ ] `users` koleksiyonunda herkese açık kaydı kapat (`createRule: null`).

---

### 🔴 Prompt 4: PB Dağıtımı, Sırlar ve Docker Compose (Kritik Güvenlik)
- [ ] `docker/pocketbase/Dockerfile` oluştur (sabit PB 0.40.6, checksum, non-root user, `pb_migrations` COPY, `CMD ["serve", "--http=0.0.0.0:8090"]`, healthcheck).
- [ ] `docker-compose.yml` güncelle: PB için bağımsız build, `pb_data` yalnızca PB servisine mount edilsin.
- [ ] Sırları `${VAR:?zorunlu}` kalıbıyla zorunlu kıl; sabit şifreleri (`changeme`, `admin@example.com`) kaldır.
- [ ] `config.py`: `POCKETBASE_EMAIL` / `POCKETBASE_PASSWORD` varsayılanlarını kaldır; `OPENROUTER_*` ekle.
- [ ] `.env.example` dosyasını PB + OpenRouter değişkenleriyle güncelle.

---

### 🔴 Prompt 5: PB İstemci Katmanı (SDK Senkron Kullanımı & Okuma Yolları) (Kritik İşlevsel)
- [ ] `services/pb.py` (yeni modül; eski `services/pocketbase.py` silinecek):
  - `get_admin_client()`: macro_data, price_history ve zamanlanmış işler için superuser istemcisi.
  - `get_user_client(token)`: her istek için kullanıcı JWT'si ile yetkilendirilmiş istemci.
  - CRUD metodları: `list_all` (`get_full_list`), `get_one`, `create`, `update(id, body)`, `delete(id)`.
  - Sorgularda `client.filter(raw, params)` kullanımı (f-string ile enjeksiyona açık filtreleme yasak).
  - Hata dönüşümü: PB HTTP 400/401/403/404 hatalarını FastAPI exception handler'a bağla.
- [ ] Kırık tüm `get_list(params=...)` çağrılarını düzelt (ledger, decision, counterfactual, benchmark, price_service).
- [ ] `transactions.get(id)` yerine `get_one(id)` kullan.
- [ ] `update(record/dict)` imza hatalarını gider (`update(id, body)`).
- [ ] Ledger `_get_holdings_at_date` içindeki sessiz `except Exception: records = []` yutmasını kaldır.
- [ ] PB ve ağ çağrısı yapan endpoint'leri senkron `def` (veya run_in_threadpool) hâline getir.

---

### 🔴 Prompt 6: Kimlik Doğrulama ve Kullanıcı İzolasyonu (Kritik Güvenlik)
- [ ] `X-User-ID` ve statik `API_TOKEN` mekanizmasını kaldır.
- [ ] FastAPI `get_current_user` bağımlılığı oluştur (`Authorization: Bearer <PB_JWT>` doğrulaması).
- [ ] Tekil kaynak endpoint'lerinde kullanıcı sahiplik doğrulaması yap (başkasının verisine erişim -> 404).
- [ ] Liste ve özet uç noktalarını çağıran kullanıcıya göre filtrele.
- [ ] Rate limit mekanizmasını kullanıcı kimliği + endpoint bazında izole et.
- [ ] 64 KB istek gövdesi limiti middleware'i ekle.
- [ ] CORS ve OpenAPI üretim ayarlarını yapılandır.

---

### 🟠 Prompt 7: Ledger + Decision Düzeltmeleri (Yüksek)
- [ ] `add_transaction`: SELL ve CASH_OUT işlemlerinde yetersiz stok / bakiye durumunda **409 Conflict** fırlat.
- [ ] Kullanıcı bazlı süreç-içi kilit altında işlem kontrolü ve oluşturma uygula.
- [ ] `void_transaction`: `update(id, {"voided": true})` soft-delete yap.
- [ ] Snapshot hesaplaması: ortalama maliyet (average_cost), gerçekleşmemiş K/Z, `cash_received` (DIVIDEND), komisyon (fee) maliyet bazı eklemesi.
- [ ] `decision_service`: `decision_date` (gelecek tarih girilirse 422) kaydet ve oku; transaction bağlantısını doğrula; boş sayısal değerleri `None` döndür.
- [ ] Route sıralama hatasını düzelt: `GET /api/decisions/stats` route'unu `GET /api/decisions/{decision_id}` route'undan ÖNCE tanımla.
- [ ] Hataları HTTP 200 + `{"error": ...}` yerine standart HTTP hata kodlarıyla fırlat (404, 409, 422, 502, 503).

---

### 🟠 Prompt 8: AI Servisi: OpenRouter + Hata Semantiği (Yüksek)
- [ ] `google-genai` bağımlılığını ve `GOOGLE_API_KEY` / `GEMINI_MODEL` yapılandırmasını kaldır.
- [ ] OpenRouter istemcisi oluştur (`OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `OPENROUTER_MODELS` virgülle ayrılmış fallback zinciri).
- [ ] Modelleri sırayla dene; zaman aşımı / 5xx / 429 durumunda sonraki modele geç; tümü başarısızsa 502; anahtar eksikse 503.
- [ ] Prompt güvenliği: kullanıcı notunu `<user_input>...</user_input>` etiketleri arasına al; etiketleri kaçır ve 2000 karakterle sınırla.
- [ ] Başarılı retrospektifte kararın durumunu `status: "REVIEWED"` yap; hata durumunda DB'yi değiştirme.

---

### 🟠 Prompt 9: Price Service, Time-Travel ve Value-Series (Yüksek)
- [ ] `services/price_service.py` sözdizimi ve imza hatalarını düzelt; PB price_history cache kontrolünü `list_all` ile yap.
- [ ] `get_price_on(symbol, asset_type, on_date)`: PB -> yfinance -> ccxt sırasıyla ara; tatilde önceki iş gününü al; fiyat yoksa `None` ve `missing_prices` döndür.
- [ ] Ledger `price_fn` imzasını `(symbol, asset_type, on_date)` olarak güncelle.
- [ ] Time-Travel: `start_holdings` miktarını `T_target` fiyatlarıyla değerle.
- [ ] `GET /api/portfolio/value-series`: max 400 nokta sınırı (aşarsa 422); gerçek haftalık (7 gün) ve aylık adımlar; eksik `timedelta` importunu ekle.
- [ ] `GET /api/portfolio/real-valuation`: `nominal_end` yoksa `date_to` snapshot'ını kullan.
- [ ] Dinamik USD/TRY para birimi dönüşümünü bağla.

---

### 🟡 Prompt 10: Gölge Portföy (Counterfactual Engine) (Orta)
- [ ] `services/counterfactual_service.py` servisini yeni PB katmanına ve `CurrentUser` mimarisine taşı.
- [ ] `track_shadow`: SELL kararı için `HELD_INSTEAD`; vazgeçilen alım için `BOUGHT_INSTEAD`.
- [ ] Fırsat maliyeti hesabı: `gölge - gerçek`.
- [ ] `what_if_scenario` içerisindeki sahte placeholder kodunu kaldır; gerçek pozisyon ve tarihsel fiyat bağla.
- [ ] Kullanıcı izolasyonu: başkasının gölgesine erişim 404; karar silinince bağlı gölgeler cascade silinsin.

---

### 🟡 Prompt 11: Benchmark, Enflasyon ve Zamanlayıcı (Orta)
- [ ] `benchmark_service._upsert_to_pb` fonksiyonunu admin client ve `get_first_list_item` ile düzelt; `date` benzersiz indeksini kullan.
- [ ] EVDS ve FRED API isteklerini resmî dokümantasyona göre doğrula; anahtar yoksa sahte veri üretme.
- [ ] `gold_try_gram = (GC=F_USD / 31.1035) * USDTRY` hesaplaması.
- [ ] `APScheduler` (BackgroundScheduler) lifespan içine entegre et; günlük benchmark çekimi ve EXPIRED kontrolü çalıştır; env ile kapatılabilir yap (`ENABLE_SCHEDULER=false`).
- [ ] `GET /api/portfolio/benchmarks`: portföy, altın, S&P 500, TÜFE kıyaslaması ve alpha hesabı.

---

### 🟡 Prompt 12: Monte Carlo ve Stres Testi (Orta)
- [ ] `stress_test` fonksiyonundaki `session` parametresini kaldır; kimliği `CurrentUser`'dan al.
- [ ] `monte_carlo_endpoint` içindeki tanımsız `request` ve `_guess_asset_type` hatalarını gider.
- [ ] `market_crash` senaryosunda şok etkisini kalıcı hâle getir (tüm günlere tam şok).
- [ ] Varlık sınıfı duyarlılık tablosu ekle (hisse, kripto, emtia, nakit).
- [ ] Simülasyon horizonlarını tek çağrıda 63, 126 ve 252 gün olarak hesapla; 40 kutulu histogram ve p5/p50/p95 döndür.
- [ ] Cholesky korelasyonlu simülasyon, simülasyon sayısı üst sınırı 20.000.

---

### 🟡 Prompt 13: Karar Günlüğü: Stats, Outcome ve EXPIRED (Orta)
- [ ] `DELETE /api/decisions/{id}` endpoint'ini kullanıcı sahipliğiyle yetkilendir; PB cascade ile bağlı gölgelerin silindiğini doğrula.
- [ ] Vadesi dolmuş kararlar için `outcome_price`, `outcome_return_pct`, `target_hit` alanlarını `price_service` ile doldur.
- [ ] `POST /api/decisions/{id}/evaluate` manuel değerlendirme endpoint'i ekle.
- [ ] `GET /api/decisions/stats`: Python tarafında özet ve getiri metrikleri; n < 3 ise `insufficient_data: true` dön.
- [ ] Zamanlayıcı job'ı ile vadesi geçmiş `OPEN` kararları otomatik `EXPIRED` durumuna getir.

---

### 🟡 Prompt 14: Web Arayüzü: PB Girişi ve Paneller (Orta)
- [ ] Giriş ekranı (`/web/login`): PocketBase `users/auth-with-password` ile giriş, token'ı sessionStorage'a alma, `auth-refresh`, 401 durumunda login'e yönlendirme.
- [ ] `apiFetch` içine Bearer token ekle.
- [ ] CSP uyumu: `decision_form.html` içindeki inline style'ları CSS sınıflarına taşı; Chart.js'i yerel vendor dosyası yap veya SRI ekle.
- [ ] Paneller: Time-Travel, Karar Günlüğü, Gölge Portföy, Stres Testi (histogram + senaryolar), İşlem Ekleme.
- [ ] USD / TRY para birimi seçicisini dinamik API `currency` alanına bağla.
- [ ] "Yatırım tavsiyesi değildir" uyarısını tüm sayfa altbilgilerine ve AI çıktılarına ekle.

---

### 🟢 Prompt 15: Temizlik, Bağımlılıklar ve Doküman Senkronizasyonu (Düşük)
- [ ] Kalıntıları temizle: `futurewallet.db` dosyasını repodan sil (`git rm --cached`), `db.py`, `scripts/sanitize_symbols.py`, `services/future_price.py` silinsin.
- [ ] Bağımlılık temizliği: `requirements.in` + `pip-compile` ile kilit dosyası oluştur; `sqlalchemy`, `schedule`, `google-genai` paketlerini çıkar; `pocketbase==0.17.3`, `apscheduler`, `httpx` sabitle.
- [ ] Kod tekrarlarını gider: `_guess_asset_type` fonksiyonunu tek modüle (`services/asset_types.py`) taşı; `decision_to_dict` kopyasını kaldır.
- [ ] Dokümanları senkronize et: `MVP.md`, `README.md`, `TODO.md`, `SPRINT_PLANI_KALANLAR.md` ve `GUNCEL_IS_PLANI.md` dosyalarını son duruma göre eşitle.

---

## 📋 Hızlı Kontrol Listesi

```text
[ ] 1. python -c "import api.app" hatasız çalışıyor mu?
[ ] 2. ruff check . sıfır hata veriyor mu?
[ ] 3. Boş PB + migration sonrası 5 koleksiyon oluşuyor mu?
[ ] 4. İki farklı kullanıcı birbirinin verisini okuyamıyor mu?
[ ] 5. Repoda veya kodda changeme / admin@example.com kalmadı mı?
[ ] 6. Snapshot 2 işlem sonrası boş dönmüyor mu?
[ ] 7. Fazla SELL işleminde 409 Conflict fırlatılıyor mu?
[ ] 8. Time-travel BTC 30k->60k senaryosunda %100 PnL veriyor mu?
[ ] 9. OpenRouter fallback zinciri 502/503 hata semantiğine uyuyor mu?
[ ] 10. market_crash %50 şokunda portföy kalıcı olarak ≈ %50 düşüyor mu?
[ ] 11. Vadesi geçen kararlar zamanlayıcı ile EXPIRED yapılıyor mu?
[ ] 12. Web UI login -> dashboard akışı CSP ve konsol hatası olmadan çalışıyor mu?
[ ] 13. İş planlarındaki tüm maddeler gerçek PB entegrasyon testleriyle doğrulanmış mı?
```
