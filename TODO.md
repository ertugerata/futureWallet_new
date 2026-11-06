# FutureWallet – TODO & Sprint Takip Listesi (v3 Uyumlu)

> **Kaynak & Dayanak:** `FUTUREWALLET_DUZELTME_PROMPTLARI.md` (v3).
> **Temel İlke (Prompt 0):** Yalnızca gerçek PocketBase entegrasyon testinden geçen maddeler `[x]` yapılabilir. Kodda yazılmış olsa bile derleme/import hatası veren veya gerçek PB'de 500/TypeError üreten maddeler `[ ]` (AÇIK) olarak işaretlenmiştir.

---

## 📊 Genel Durum Özeti (FUTUREWALLET_DUZELTME_PROMPTLARI.md Bölüm B)

| Alan / Konu | Gerçek Durum | TODO Durumu |
|---|---|---|
| `price_service.py` | Yazıldı ama **SyntaxError** içeriyor (`start_date` varsayılanlı parametreden sonra) | [ ] AÇIK |
| Yeni endpoint'ler (`value-series`, `benchmarks`, `stress-test`, `narrative`, shadow-positions, `stats`, `DELETE decision`) | Eklendi; ancak çağrıldığında çoğu **500 Internal Server Error** veriyor | [ ] AÇIK |
| PB Okuma Yolları | **Tamamı kırık** (`get_list(params=...)` TypeError, `transactions.get(id)` AttributeError, `update(record)` TypeError) | [ ] AÇIK |
| Auth & Kimlik Doğrulama | `X-User-ID` başlığı ve statik `API_TOKEN` kullanılıyor; kullanıcı izolasyonu yok, PB auth entegrasyonu yok | [ ] AÇIK |
| Şema & Erişim Kuralları | PB koleksiyonları HTTP 400 hatasıyla oluşturulamıyor (`ensure_collections` kırık); kurallar güvensiz/açık | [ ] AÇIK |
| Uygulama İçe Aktarımı & Testler | `api.app` import edilemiyor (`TransactionCreateRequest` sıra hatası); pytest 45 toplama hatası | [ ] AÇIK |
| Rate Limit Mantığı | Zaman penceresi sayacı düzeldi; ancak anahtar hâlâ (IP, token), kullanıcıya bağlı değil | [ ] Kısmen |
| GBM Drift | Düzeldi (mean log, varyans düzeltmesi yok) | [x] Tamamlandı |
| Monte Carlo Histogram | Eklendi (40 kutu) | [x] Tamamlandı |
| Temizlik & Bağımlılıklar | `futurewallet.db` git'te duruyor, `db.py` ve SQLAlchemy bağımlılıkları temizlenmedi | [ ] AÇIK |

---

## 🏃 Uygulama Sırası ve İş Listesi (Prompt 0 - Prompt 15)

### 🔴 Prompt 1: Uygulamayı Ayağa Kaldır, Lint / CI / Bağımlılıklar (Kritik)
*Bağımlılık: Yok*

- [ ] `api/app.py` Pydantic model tanımlama sırasını düzelt (`TransactionCreateRequest` endpoint'ten önce tanımlanmalı; satır 859 vs 880).
- [ ] `services/price_service.py` imza sözdizimi hatasını gider (`start_date, end_date, asset_type="crypto"`).
- [ ] Tanımsız ruff isimlerini düzelt: `timedelta` (app.py: ~506/513/519), `request` (monte-carlo endpoint'i: ~843), `_guess_asset_type` (~832), `Optional` (ledger_service.py: 246, 278).
- [ ] Çift tanımlı `decision_to_dict` fonksiyonunu tekleştir (yalnızca `services/decision_service.py` içinde olmalı).
- [ ] Kullanılmayan değişken ve importları temizle (`user_id`, `delete_decision`, `db.py` importları).
- [ ] `ruff.toml` dosyasını geçerli hâle getir (`line-length = 100` en üst seviyeye taşınmalı; geçersiz `[format]` alanı düzeltilmeli).
- [ ] `api/app.py` içinden `db` / SQLAlchemy (`from db import get_session`) importunu kaldır.
- [ ] `lifespan`: fail-closed yapılandırma doğrulaması, PB bağlantı ve koleksiyon kontrolü ekle; `@app.on_event` kaldır; `/health` yanıtına `pb: ok|down` ekle.
- [ ] `requirements.txt`: `pocketbase==0.17.3`, `apscheduler`, `httpx` ekle; `requirements.in` + `pip-compile` ile kilit dosyası oluştur.
- [ ] CI pipeline'ına duman testi (`python -c "import api.app"`), ruff, mypy, pytest, pip-audit ekle.
- [ ] **Kabul Kriteri:** `python -c "import api.app"` ve `pytest --collect-only -q` 0 hata; `ruff check .` temiz.

---

### 🔴 Prompt 2: Gerçek PocketBase ile Test Altyapısı (Kritik Altyapı)
*Bağımlılık: Prompt 1*

- [ ] `tests/conftest.py` dosyasını gerçek PocketBase (v0.40.6) binary'si ile çalışacak şekilde yeniden yaz.
- [ ] `pb_server` fixture'ı: PB v0.40.6 binary otomatik indirme, checksum doğrulama, geçici `--dir`, superuser oluşturma, test bitiminde kapatma.
- [ ] `pb_clean` fixture'ı: her test öncesi/sonrası koleksiyonları temizleme.
- [ ] `make_user(email)` fixture'ı: `(user_id, JWT)` üretimi.
- [ ] `api_client` fixture'ı: gerçek PB'ye bağlı FastAPI TestClient (PB mock'ı kaldırılacak).
- [ ] Dış servisler (yfinance, ccxt, OpenRouter, EVDS, FRED) için izole mock fixture'ları.
- [ ] SQLAlchemy / in-memory SQLite (`Base`, `db.py`) tabanlı eski fixture ve testleri sil.
- [ ] GitHub Actions'a PB binary önbellekleme ve `pytest -m pb` adımı ekle.
- [ ] **Kabul Kriteri:** `pytest -m pb` gerçek PB'ye karşı çalışır; kod tabanında PB'yi taklit eden MagicMock kalmaz.

---

### 🔴 Prompt 3: PB Şema, Erişim Kuralları ve Migration (Kritik Güvenlik)
*Bağımlılık: Prompt 2*

- [ ] PB Dev admin arayüzü ile geçerli şemaları oluştur ve `pb_migrations/` dizinini repoya ekle.
- [ ] `services/pocketbase.py` içindeki bozuk `ALL_COLLECTIONS`, `create_collection`, `ensure_collections` kodunu sil (uygulama yalnızca şema doğrulasın).
- [ ] Tek doğruluk kaynağı (MVP §5 uyumu):
  - Sentiment değerlerini eşitle: `FOMO`, `STRATEGIC`, `PANIC`, `DIVIDEND`, `OPPORTUNITY`. `RISK_REDUCTION`'ı tüm koddan kaldır (api, servis, validator). Tek enum modülü: `services/enums.py`.
  - `decisions`: `transaction` relation alanı, `decision_date` (date), `outcome_*`, `target_hit` alanlarını şemaya ekle.
  - `shadow_portfolios`: `user` relation (zorunlu), `decision` relation (cascadeDelete=true).
  - Benzersiz indeksler: `price_history(symbol, date)`, `macro_data(date)`.
  - Regex ve kısıtlar: `asset_symbol` (max 20, `^[A-Z0-9.=^\-/]{1,20}$`), `rationale` max 5000, `target_price > 0`.
- [ ] Erişim Kuralları (API Rules):
  - `transactions`, `decisions`, `shadow_portfolios`: list/view `user = @request.auth.id`, create `@request.auth.id != '' && @request.body.user = @request.auth.id`, update `user = @request.auth.id && @request.body.user:isset = false`, delete `user = @request.auth.id` (`transactions` için soft-delete voided).
  - `macro_data`, `price_history`: list/view `@request.auth.id != ''`, create/update/delete `null` (yalnızca admin).
  - `users`: herkese açık kayıt kapalı (`createRule: null`).
- [ ] **Kabul Kriteri:** Boş PB'ye migration uygulanınca 5 koleksiyon oluşur; Kullanıcı A, B'nin kaydını okuyamaz/değiştiremez; anonim erişim engellenir; `RISK_REDUCTION` 422 ve PB tarafından reddedilir.

---

### 🔴 Prompt 4: PB Dağıtımı, Sırlar ve Docker Compose (Kritik Güvenlik)
*Bağımlılık: Prompt 3*

- [ ] `docker/pocketbase/Dockerfile` oluştur (sabit PB 0.40.6, checksum, non-root user, `pb_migrations` COPY, `CMD ["serve", "--http=0.0.0.0:8090"]`, healthcheck).
- [ ] `docker-compose.yml` güncelle: PB için bağımsız build, `pb_data` yalnızca PB servisine mount edilsin (FastAPI uygulamasına SQLite veritabanı mount edilmeyecek).
- [ ] Sırları `${VAR:?zorunlu}` kalıbıyla zorunlu kıl; kod ve compose'dan sabit `admin@example.com` ve `changeme` değerlerini tamamen kaldır.
- [ ] `config.py`: `POCKETBASE_EMAIL` / `POCKETBASE_PASSWORD` varsayılanlarını kaldır (boşsa RuntimeError); `DATABASE_URL`, `GOOGLE_API_KEY`, `GEMINI_MODEL` ölü ayarlarını temizle; `OPENROUTER_*` ekle.
- [ ] `.env.example` dosyasını PB + OpenRouter değişkenleriyle güncelle; port haritasını dokümante et (8080 -> 8090).
- [ ] **Kabul Kriteri:** `docker compose config` parola verilmeden hata verir; repoda `changeme` kalmaz; app konteyneri PB veri dizinini görmez.

---

### 🔴 Prompt 5: PB İstemci Katmanı (SDK Senkron Kullanımı & Okuma Yolları) (Kritik İşlevsel)
*Bağımlılık: Prompt 3*

- [ ] `services/pb.py` (yeni modül; eski `services/pocketbase.py` silinecek):
  - `get_admin_client()`: macro_data, price_history ve zamanlanmış işler için superuser istemcisi (thread-safe, auto-refresh).
  - `get_user_client(token)`: her HTTP isteği için kullanıcı JWT'si ile yetkilendirilmiş istek-bazlı PocketBase istemcisi.
  - Yardımcı metodlar: `list_all` (`get_full_list`), `get_one`, `create`, `update(id, body)`, `delete(id)`.
  - Sorgularda `client.filter(raw, params)` kullanımı (f-string ile enjeksiyona açık filtreleme yasak).
  - Hata dönüşümü: PB HTTP 400/401/403/404 hatalarını FastAPI exception handler'a bağla.
- [ ] Kırık tüm `get_list(params=...)` çağrılarını düzelt (ledger, decision, counterfactual, benchmark, price_service).
- [ ] `transactions.get(id)` (AttributeError) yerine `get_one(id)` kullan.
- [ ] `update(record/dict)` imza hatalarını gider (`update(id, body)`).
- [ ] Ledger `_get_holdings_at_date` içindeki sessiz `except Exception: records = []` yutmasını kaldır.
- [ ] PB ve ağ çağrısı yapan endpoint'leri senkron `def` (veya run_in_threadpool) hâline getir (event loop bloklanmasını önle).
- [ ] **Kabul Kriteri:** 600+ kayıtlı koleksiyonda `list_all` sorunsuz döner; daha önce 500 veren list_decisions, get_decision, get_transactions, stats çalışır; filtre enjeksiyon testleri geçer.

---

### 🔴 Prompt 6: Kimlik Doğrulama ve Kullanıcı İzolasyonu (Kritik Güvenlik)
*Bağımlılık: Prompt 5*

- [ ] İstemci başlığından sahte kimlik alan `X-User-ID` ve statik `API_TOKEN` mekanizmasını tamamen kaldır.
- [ ] FastAPI `get_current_user` bağımlılığı oluştur: `Authorization: Bearer <PB_JWT>` başlığını al, `users.auth_refresh()` ile doğrula (geçersiz -> 401), kullanıcı bazlı PB istemcisini sağla (`CurrentUser(id, email, token, pb)`).
- [ ] Tekil kaynak endpoint'lerinde (decisions GET/PUT/DELETE/close/target-check/retrospective, shadow-positions, transactions void) kullanıcı sahiplik doğrulaması yap (başkasının verisine erişim -> 404).
- [ ] Liste ve özet uç noktalarını çağıran kullanıcıya göre filtrele.
- [ ] Rate limit mekanizmasını kullanıcı kimliği + endpoint bazında izole et; sayaç testlerde sıfırlanabilir olsun.
- [ ] 64 KB istek gövdesi limiti middleware'i ekle (büyük payload DoS koruması).
- [ ] CORS ve OpenAPI üretim ayarlarını yapılandır (üretimde `/docs` kapatılabilir).
- [ ] **Kabul Kriteri:** Token yoksa 401; Kullanıcı A, B'nin id'sini sorguladığında 404; Retrospective aynı karar için 60 sn içinde 2. istekte 429; 70 KB payload 413 döner.

---

### 🟠 Prompt 7: Ledger + Decision Düzeltmeleri (Yüksek)
*Bağımlılık: Prompt 5, Prompt 6*

- [ ] `add_transaction`: SELL ve CASH_OUT işlemlerinde yetersiz stok / bakiye durumunda **409 Conflict** fırlat.
- [ ] Kullanıcı bazlı süreç-içi kilit altında işlem kontrolü ve oluşturma uygula.
- [ ] `void_transaction`: `update(id, {"voided": true})` soft-delete ve idempotent yap.
- [ ] Snapshot hesaplaması: ortalama maliyet (average_cost), gerçekleşmemiş K/Z (unrealized PnL), `cash_received` (DIVIDEND), komisyon (fee) maliyet bazı eklemesi.
- [ ] `decision_service`: tekil `decision_to_dict`; `create_decision` içinde `decision_date` (gelecek tarih girilirse 422) kaydet ve oku; transaction bağlantısını doğrula; boş sayısal değerleri `None` döndür.
- [ ] Route sıralama hatasını düzelt: `GET /api/decisions/stats` route'unu `GET /api/decisions/{decision_id}` route'undan ÖNCE tanımla.
- [ ] Hataları HTTP 200 + `{"error": ...}` yerine standart HTTP hata kodlarıyla fırlat (404, 409, 422, 502, 503).
- [ ] **Kabul Kriteri:** 2 BUY + 1 SELL sonrası portföy ortalama maliyeti doğru; stok aşan SELL 409; void işlem snapshot'ı etkilemez; `GET /api/decisions/stats` 200 döner.

---

### 🟠 Prompt 8: AI Servisi: OpenRouter + Hata Semantiği (Yüksek)
*Bağımlılık: Prompt 7*

- [ ] `google-genai` bağımlılığını ve `GOOGLE_API_KEY` / `GEMINI_MODEL` yapılandırmasını kaldır.
- [ ] OpenRouter istemcisi oluştur (`OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `OPENROUTER_MODELS` virgülle ayrılmış fallback zinciri).
- [ ] HTTP istemcisi (httpx) ile fallback modeli: sırasıyla modelleri dene; zaman aşımı / 5xx / 429 durumunda sonraki modele geç; tümü başarısızsa `502 AIGenerationError`; API anahtarı eksikse `503 AIUnavailableError`.
- [ ] Prompt güvenliği: kullanıcı notunu `<user_input>...</user_input>` etiketleri arasına al; etiketleri kaçır ve 2000 karakterle sınırla; "Yatırım tavsiyesi değildir" uyarısını yanıta ekle.
- [ ] `generate_decision_retrospective` bağlamına karar tarihi/vade fiyatı ve duygu analizi verilerini ekle.
- [ ] Başarılı retrospektifte PB'deki karar kaydını `ai_retrospective` ve `status: "REVIEWED"` ile güncelle; hata durumunda DB'yi değiştirme.
- [ ] **Kabul Kriteri:** İlk model 500 verirse ikinciye geçer ve başarıda DB status "REVIEWED" olur; tüm modeller çökerse 502 döner; prompt injection etiket dışına çıkamaz.

---

### 🟠 Prompt 9: Price Service, Time-Travel ve Value-Series (Yüksek)
*Bağımlılık: Prompt 5, Prompt 7*

- [ ] `services/price_service.py` sözdizimi ve imza hatalarını düzelt; PB price_history cache kontrolünü `list_all` ile yap.
- [ ] `get_price_on(symbol, asset_type, on_date)` fonksiyonu: PB price_history -> yfinance -> ccxt sırasıyla ara; hafta sonu/tatilde önceki işlem gününü al; fiyat bulunamazsa `None` dön ve `missing_prices` listesine ekle.
- [ ] Ledger `price_fn` imzasını `(symbol, asset_type, on_date)` olarak güncelle.
- [ ] Time-Travel hesaplaması: `value_at_start = start_holdings × price(T_start)`, `value_at_target = start_holdings × price(T_target)`, `actual_value_at_target = snapshot(T_target)`; nominal ve yüzde K/Z hesapla.
- [ ] `GET /api/portfolio/value-series`: max 400 nokta sınırı (aşarsa 422); haftalık adım için gerçek 7 gün aralığı kullan; eksik `timedelta` importunu ekle; çoklu snapshot yerine toplu fiyat sorgusu yap.
- [ ] `GET /api/portfolio/real-valuation`: `nominal_end` verilmediğinde `date_to` snapshot'ını kullan (`date_from` hatasını gider).
- [ ] Para birimini varlık tabanına göre dinamik belirle (USD/TRY dönüşümü).
- [ ] **Kabul Kriteri:** BTC 5 adet 30k -> 60k testinde time-travel %100 PnL üretir; value-series 400+ noktada 422 verir; cache isabetinde dış API'ye gitmez.

---

### 🟡 Prompt 10: Gölge Portföy (Counterfactual Engine) (Orta)
*Bağımlılık: Prompt 7, Prompt 9*

- [ ] `services/counterfactual_service.py` servisini yeni PB katmanına ve `CurrentUser` mimarisine taşı.
- [ ] `track_shadow` mantığı: SELL kararı için `HELD_INSTEAD` (satılan miktar ve fiyatla); alternatif alım için `BOUGHT_INSTEAD`.
- [ ] Fırsat maliyeti hesabı: `HELD_INSTEAD` için gerçek = nakit gelir, gölge = miktar × güncel fiyat; `fırsat maliyeti = gölge - gerçek`.
- [ ] `what_if_scenario` içindeki sahte (`quantity=1.0`, `type="crypto"`) placeholder kodu kaldır; gerçek pozisyon ve tarihsel fiyat bağla.
- [ ] Kullanıcı izolasyonu: başkasının gölge pozisyonuna erişim 404; karar silinince bağlı gölgeler cascade silinsin.
- [ ] **Kabul Kriteri:** 10 BTC 50k'dan satıldı (500k): BTC 80k olunca fırsat maliyeti +300k, 40k olunca -100k hesaplanır; Kullanıcı B, A'nın kaydını göremez.

---

### 🟡 Prompt 11: Benchmark, Enflasyon ve Zamanlayıcı (Orta)
*Bağımlılık: Prompt 5, Prompt 9*

- [ ] `benchmark_service._upsert_to_pb` fonksiyonunu admin client ve `get_first_list_item` ile düzelt; `date` benzersiz indeksini kullan; sentetik sahte veri yazımını engelle.
- [ ] EVDS ve FRED API isteklerini resmî dokümantasyona göre doğrula; anahtar yoksa açık hata/boş dön (sahte veri üretme).
- [ ] `gold_try_gram` hesaplaması: `(GC=F_USD / 31.1035) * USDTRY` formülünü doğrula ve kaydet.
- [ ] Zamanlayıcı altyapısı: `APScheduler` (BackgroundScheduler) lifespan içine entegre et; günlük makro/benchmark güncellemesi ve otomatik EXPIRED kontrolü çalıştır; ortam değişkeni ile kapatılabilir yap (`ENABLE_SCHEDULER=false`).
- [ ] `GET /api/portfolio/benchmarks`: portföy getirisi, Altın (USD ve gram TL), S&P 500, TR/US TÜFE, reel getiri ve alpha (`portföy - benchmark`) çıktısı ver.
- [ ] **Kabul Kriteri:** Aynı tarih için iki upsert tek kayıt bırakır; zamanlayıcı kapalıyken job çalışmaz; alpha ve gold_try_gram birim testleri geçer.

---

### 🟡 Prompt 12: Monte Carlo ve Stres Testi (Orta)
*Bağımlılık: Prompt 7, Prompt 9*

- [ ] `stress_test` fonksiyonundaki `session` (SQLAlchemy kalıntısı) parametresini kaldır; kimliği `CurrentUser`'dan al.
- [ ] `monte_carlo_endpoint` içindeki tanımsız `request` ve `_guess_asset_type` hatalarını gider.
- [ ] `market_crash` senaryosundaki kalıcı etki hatasını düzelt (şok sonrası tüm günlere tam kriz çarpanı uygulanmalı, yalnızca tek gün %100 sonra %10 değil).
- [ ] Senaryolar için varlık sınıfı duyarlılık tablosu ekle (hisse, kripto, emtia, nakit farklı tepki vermeli).
- [ ] Simülasyon horizonlarını tek çağrıda 63, 126 ve 252 gün olarak hesapla; 40 kutulu histogram ve p5/p50/p95 döndür.
- [ ] Cholesky korelasyonlu simülasyon, simülasyon sayısı üst sınırı 20.000 (DoS engelleme).
- [ ] **Kabul Kriteri:** Sabit mu/sigma ile 20k yolda medyan teorik değere %2 yakın; market_crash %50 şokunda portföy ≈ %50 düşer; limit aşımı 422 döner.

---

### 🟡 Prompt 13: Karar Günlüğü: Stats, Outcome ve EXPIRED (Orta)
*Bağımlılık: Prompt 7, Prompt 9*

- [ ] `DELETE /api/decisions/{id}` endpoint'ini kullanıcı sahipliğiyle yetkilendir; PB cascade ile bağlı gölgelerin silindiğini doğrula.
- [ ] Vade tarihi dolmuş kararlar için sonuç ölçümü: `outcome_price`, `outcome_return_pct`, `target_hit` alanlarını `price_service` üzerinden doldur.
- [ ] `POST /api/decisions/{id}/evaluate` manuel değerlendirme endpoint'i ekle.
- [ ] `GET /api/decisions/stats`: duygu (sentiment) ve eylem (action) bazında adet, ortalama/medyan getiri ve başarı oranını Python'da hesapla; n < 3 ise `insufficient_data: true` dön.
- [ ] Zamanlayıcı job'ı ile vadesi geçmiş `OPEN` kararları otomatik `EXPIRED` durumuna getir ve sonuç alanlarını doldur.
- [ ] **Kabul Kriteri:** 3 FOMO BUY (-10, -12, -14) stats ortalamasında -12 çıkar; vadesi geçmiş karar EXPIRED olur; karar silinince gölgesi de silinir.

---

### 🟡 Prompt 14: Web Arayüzü: PB Girişi ve Paneller (Orta)
*Bağımlılık: Prompt 6, Prompt 9 - Prompt 13*

- [ ] Giriş ekranı (`/web/login`): PocketBase `users/auth-with-password` ile giriş, token'ı sessionStorage'a alma, `auth-refresh` yenileme, 401 durumunda login'e yönlendirme.
- [ ] `apiFetch` sarmalayıcısına otomatik `Authorization: Bearer <PB_JWT>` ekle.
- [ ] CSP uyumu: `decision_form.html` içindeki inline style'ları CSS sınıflarına taşı; Chart.js'i yerel vendor dosyası yap veya SRI ekle.
- [ ] Panellerin tamamlanması:
  - Time-Travel paneli (tarih seçimi, nominal/reel getiri, value-series grafiği, benchmark kıyaslama).
  - Karar günlüğü paneli (Retrospektif, Kapat, Sil butonları; AI metni `textContent` ile güvenli gösterim; duygu özet kartı).
  - Gölge portföy "Ne olurdu?" paneli.
  - Stres testi paneli (senaryo seçimi, histogram grafiği, p5/p50/p95 çizgileri, AI risk anlatısı).
  - İşlem ekleme formu ve işlem geçmişi listesi.
- [ ] USD / TRY para birimi seçicisini dinamik API `currency` alanına bağla.
- [ ] "Yatırım tavsiyesi değildir" uyarısını tüm sayfa altbilgilerine ve AI çıktılarına ekle.
- [ ] **Kabul Kriteri:** Login -> Dashboard akışı hatasız çalışır; CSP/konsol hatası olmaz; sunucu verisi hiçbir yerde `innerHTML` ile basılmaz.

---

### 🟢 Prompt 15: Temizlik, Bağımlılıklar ve Doküman Senkronizasyonu (Düşük)
*Bağımlılık: Tüm Promptlar*

- [ ] Kalıntıları temizle: `futurewallet.db` dosyasını repodan sil (`git rm --cached futurewallet.db`), `db.py`, `scripts/sanitize_symbols.py`, `services/future_price.py` silinsin.
- [ ] Bağımlılık temizliği: `requirements.in` üzerinden `pip-compile` ile kilit dosyası oluştur; `sqlalchemy`, `schedule`, `google-genai` paketlerini kaldır; `pocketbase==0.17.3`, `apscheduler`, `httpx` sabitle.
- [ ] Kod tekrarlarını gider: `_guess_asset_type` fonksiyonunu tek modüle (`services/asset_types.py`) taşı; `decision_to_dict` kopyasını kaldır.
- [ ] Dokümanları senkronize et: `MVP.md`, `README.md`, `TODO.md` ve sprint planlarını son duruma göre eşitle.
- [ ] **Kabul Kriteri:** Repoda `.db` veya `db.py` kalmaz; kodda `sqlalchemy` ve `google.genai` referansı kalmaz; CI yeşil yanar.
