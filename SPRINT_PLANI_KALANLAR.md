# Sprint Planı – KALAN VE DÜZELTİLECEK İŞLER (v3)

> **Referans Belge:** `FUTUREWALLET_DUZELTME_PROMPTLARI.md` (v3).
> **Mimari Hedef:** PocketBase v0.40.6 (DB/Auth) + FastAPI (Hesaplama) + OpenRouter (LLM).
> **Durum:** Önceki sprintlerde tamamlandı sanılan birçok modül derleme hataları, kırık PB SDK çağrıları veya mock'lar arkasında kaldığı için gerçek PB ortamında çalışmamaktadır. İşler v3 uygulama sırasına göre sprintlere bölünmüştür.

---

## 📊 Gerçek Durum ve Mevcut Açıklar

| Modül / Alan | Mevcut Durum | Neden Açık? |
|---|---|---|
| **Uygulama İçe Aktarımı** | ❌ Kırık | `api/app.py`: `TransactionCreateRequest` endpoint'ten sonra tanımlı; pytest toplama 45 hata |
| **`price_service.py`** | ❌ Kırık | `SyntaxError`: varsayılanlı parametreden sonra zorunlu parametre (`start_date`) |
| **PocketBase Okuma Yolları** | ❌ Kırık | `get_list(params=...)` TypeError veriyor; `update(record)` hatalı; `transactions.get()` yok |
| **PB Şema & Kurallar** | ❌ Kırık | `ensure_collections` PB v0.40.6'da HTTP 400 ile patlıyor; anonim okuma açık, kullanıcı kuralı yok |
| **Auth & İzolasyon** | ❌ Eksik | `X-User-ID` sahte başlığı var; PB JWT auth yok; rate limit IP bazlı; gövde limiti yok |
| **Test Altyapısı** | ❌ Yanıltıcı | SQLAlchemy mock'ları ile geçiyor; gerçek PocketBase binary entegrasyon testi yok |
| **Ledger Mantığı** | ⚠️ Eksik | SELL işleminde stok yetersizliğinde 409 Conflict yok; DIVIDEND cash_received eksik |
| **AI Servisi** | ⚠️ Eksik | OpenRouter yerine kırık `genai` importu; AI hata semantiği (502/503) eksik |
| **Zamanlayıcı (Scheduler)**| ❌ Yok | APScheduler/schedule kurulu değil; `auto_close_expired_decisions` çağrılmıyor |
| **Web UI** | ⚠️ Eksik | Giriş akışı / token saklama yok (tüm istekler 401); inline style CSP ihlali |
| **Kalıntılar** | ⚠️ Eksik | `futurewallet.db` repoda duruyor; `db.py` ve SQLAlchemy bağımlılıkları temizlenmedi |

---

## 🗺️ Sprint Yol Haritası (Prompt 1 - Prompt 15)

### 🔴 Sprint 1: Uygulama Başlatma, CI/Lint ve Gerçek PocketBase Test Altyapısı
*Kapsam: Prompt 1 & Prompt 2*

1. **Uygulamayı Ayağa Kaldır ve Lint Hatalarını Gider (P1):**
   - [ ] `api/app.py`: Pydantic modellerini (`TransactionCreateRequest`) endpoint'lerin önüne taşı.
   - [ ] `services/price_service.py`: Sözdizimi hatasını düzelt (`start_date, end_date, asset_type="crypto"`).
   - [ ] Ruff hatalarını temizle (`timedelta`, `request`, `_guess_asset_type`, `decision_to_dict`, `Optional`).
   - [ ] `ruff.toml`: `line-length = 100` alanını düzelt; `ruff check .` sıfır hata.
   - [ ] `api/app.py` içinden SQLAlchemy/`db.py` importunu kaldır.
   - [ ] `lifespan`: fail-closed PB kontrolü ekle; `/health` endpoint'ine PB durumu bağla.
   - [ ] `requirements.txt`: `pocketbase==0.17.3`, `apscheduler`, `httpx` ekle.
2. **Gerçek PocketBase ile Test Altyapısı (P2):**
   - [ ] `tests/conftest.py`: PB v0.40.6 binary indiren ve çalıştıran `pb_server`, `pb_clean`, `make_user`, `api_client` fixture'larını kur.
   - [ ] SQLAlchemy/in-memory SQLite mock'larını sil.
   - [ ] GitHub Actions CI pipeline'ında PB binary cache ve `pytest -m pb` adımlarını zorunlu kıl.

---

### 🔴 Sprint 2: PB Şema/Migration, Güvenli Dağıtım ve PB İstemci Katmanı
*Kapsam: Prompt 3, Prompt 4 & Prompt 5*

1. **PB Şema, Erişim Kuralları ve Migration (P3):**
   - [ ] `pb_migrations/` dizinini oluştur; 5 ana koleksiyonu (`transactions`, `decisions`, `shadow_portfolios`, `macro_data`, `price_history`) migration ile kur.
   - [ ] `RISK_REDUCTION` sentiment değerini koddan temizle; tek enum kaynağı (`services/enums.py`).
   - [ ] PB API Rules: list/view/create/update/delete için `user = @request.auth.id` kuralını doğrula.
2. **Docker Compose ve Güvenli Dağıtım (P4):**
   - [ ] `docker/pocketbase/Dockerfile` oluştur; PB sürümünü sabitle (0.40.6); root olmayan kullanıcı.
   - [ ] `docker-compose.yml`: `pb_data`'yı sadece PB konteynerine mount et; uygulama konteynerinden SQLite erişimini kes.
   - [ ] Sabit şifreleri (`changeme`, `admin@example.com`) kaldır; `${VAR:?zorunlu}` kullan.
   - [ ] `config.py` ve `.env.example` güncelle.
3. **Senkron PB İstemci Katmanı (P5):**
   - [ ] Yeni `services/pb.py` modülü yaz (`get_admin_client()`, `get_user_client(token)`, CRUD yardımcıları).
   - [ ] Kırık `get_list(params=...)` çağrılarını düzelt; `client.filter(raw, params)` ile filtre injection'ı engelle.
   - [ ] `transactions.get()` ve `update(record)` çağrılarını düzelt.
   - [ ] Sessiz `except Exception: records = []` yutmalarını kaldır; açık exception fırlat.

---

### 🔴 Sprint 3: Kullanıcı İzolasyonu, Ledger ve Karar Günlüğü Düzeltmeleri
*Kapsam: Prompt 6 & Prompt 7*

1. **Kimlik Doğrulama ve Kullanıcı İzolasyonu (P6):**
   - [ ] `X-User-ID` ve statik `API_TOKEN`'ı kaldır.
   - [ ] `get_current_user` dependency'si ile gelen PB Bearer token'ını doğrula (`auth_refresh`).
   - [ ] Tekil kaynak endpoint'lerinde sahiplik kontrolü (başkasının verisi -> 404).
   - [ ] Rate limit mekanizmasını kullanıcı kimliğine bağla.
   - [ ] 64 KB istek gövdesi limiti middleware'i ekle.
2. **Ledger ve Karar Günlüğü İş Mantığı (P7):**
   - [ ] `add_transaction`: yetersiz stok/bakiye durumunda **409 Conflict** fırlat.
   - [ ] Snapshot: ortalama maliyet (average_cost), gerçekleşmemiş K/Z, DIVIDEND `cash_received`, fee maliyet bazı.
   - [ ] `void_transaction`: soft-delete `voided=true`.
   - [ ] `decision_service`: `decision_date` geçmiş tarih kontrolü ve kaydı; transaction ilişkilendirmesi.
   - [ ] Route sırası düzeltmesi: `/api/decisions/stats` route'unu `/{decision_id}` route'undan önce tanımla.

---

### 🟠 Sprint 4: Fiyat Servisi, Time-Travel ve OpenRouter AI Entegrasyonu
*Kapsam: Prompt 8 & Prompt 9*

1. **AI Servisi: OpenRouter (P8):**
   - [ ] `google-genai` ve Gemini ayarlarını temizle.
   - [ ] OpenRouter fallback istemcisini yaz (`OPENROUTER_API_KEY`, `OPENROUTER_MODELS`).
   - [ ] Prompt güvenliği: `<user_input>` etiketleri, etiket temizleme, 2000 karakter sınırı.
   - [ ] Hata durumlarında 502/503 dönüşü; başarıda kararın `status: "REVIEWED"` yapılması.
2. **Price Service, Time-Travel ve Değerleme Serileri (P9):**
   - [ ] `services/price_service.py`: `get_price_on(symbol, asset_type, on_date)` fonksiyonunu PB cache + yfinance + ccxt ile kur.
   - [ ] Ledger `price_fn` imzasını `(symbol, asset_type, on_date)` olarak güncelle.
   - [ ] Time-Travel: `start_holdings` miktarını `T_target` tarihindeki fiyatla değerle.
   - [ ] `GET /api/portfolio/value-series`: max 400 nokta sınırı; gerçek haftalık/aylık adımlar; tek aralık sorgusu.
   - [ ] `GET /api/portfolio/real-valuation`: `nominal_end` yoksa `date_to` snapshot'ını kullan.

---

### 🟡 Sprint 5: Gölge Portföy, Makro/Benchmark, Stres Testi ve Zamanlayıcı
*Kapsam: Prompt 10, Prompt 11, Prompt 12 & Prompt 13*

1. **Gölge Portföy (Counterfactual Engine) (P10):**
   - [ ] SELL kararında `HELD_INSTEAD` kaydı oluşturma (`track_shadow=True`).
   - [ ] Alternatif fırsat maliyeti hesabı (`gölge - gerçek`).
   - [ ] `what_if_scenario` içerisindeki placeholder'ları kaldır; gerçek veriyi bağla.
2. **Benchmark, Enflasyon ve APScheduler (P11):**
   - [ ] `benchmark_service._upsert_to_pb`: tekil kayıt garantisi; sahte/sentetik veriyi engelle.
   - [ ] `gold_try_gram = (GC=F / 31.1035) * USDTRY` hesaplaması.
   - [ ] Lifespan içine `APScheduler` (BackgroundScheduler) ekle; günlük benchmark çekimi ve EXPIRED kontrolü.
   - [ ] `GET /api/portfolio/benchmarks`: portföy, altın, S&P 500, TÜFE kıyaslaması ve alpha hesabı.
3. **Monte Carlo ve Stres Testi İyileştirmeleri (P12):**
   - [ ] `session` parametresini kaldır; kimliği `CurrentUser`'dan al.
   - [ ] `market_crash` senaryosunda şok etkisini kalıcı hâle getir (tek gün değil, tüm günlere tam şok).
   - [ ] Tek çağrıda 63, 126 ve 252 günlük horizonlar, 40 kutulu histogram ve p5/p50/p95.
4. **Karar Günlüğü: Outcome ve Otomatik EXPIRED (P13):**
   - [ ] `GET /api/decisions/stats`: Python tarafında özet ve getiri metrikleri; n < 3 için yetersiz veri kontrolü.
   - [ ] Vadesi geçen kararları zamanlayıcı job'ı ile `EXPIRED` durumuna getir ve sonuç fiyat/getirilerini doldur.

---

### 🟡 Sprint 6: Web Arayüzü, Temizlik ve Yayına Alma
*Kapsam: Prompt 14 & Prompt 15*

1. **Web Arayüzü Tamamlama (P14):**
   - [ ] `/web/login` ekranı ve PB auth entegrasyonu (`auth_with_password`, token saklama, refresh, 401 yönlendirme).
   - [ ] `apiFetch` içine Bearer token ekleme.
   - [ ] CSP uyumu: inline `style=` özelliklerini CSS sınıflarına taşı; Chart.js'i yerelleştir veya SRI ekle.
   - [ ] Paneller: Time-Travel, Karar Günlüğü, Gölge Portföy, Stres Testi (histogram + senaryolar), İşlem Ekleme.
   - [ ] Dinamik para birimi (USD/TRY) seçici ve yasal uyarı notları.
2. **Kalıntı Temizliği ve Doküman Senkronu (P15):**
   - [ ] `futurewallet.db` dosyasını repodan sil (`git rm --cached`).
   - [ ] `db.py`, `scripts/sanitize_symbols.py`, `services/future_price.py` dosyalarını kaldır.
   - [ ] `requirements.in` + `pip-compile` ile kilit dosyası oluştur; `sqlalchemy` ve `google-genai` paketlerini çıkar.
   - [ ] `_guess_asset_type` fonksiyonunu tek modüle taşı; `decision_to_dict` kopyasını sil.
   - [ ] Dokümanları senkronize et (`MVP.md`, `README.md`, `TODO.md`).

---

## 📋 Kabul Kriterleri Doğrulama Kontrol Listesi

```text
[ ] 1. import api.app hatasız çalışır; ruff check . sıfır hata verir.
[ ] 2. Boş PB + migration uygulandığında 5 koleksiyon oluşur; anonim okuma/yazma 403 döner.
[ ] 3. İki farklı kullanıcı birbirinin işlem/karar/gölge verisini okuyamaz veya değiştiremez.
[ ] 4. Repoda veya kodda sabit şifre/kullanıcı adı ("changeme", "admin@example.com") kalmaz.
[ ] 5. Snapshot iki işlemden sonra boş dönmez; PB hatasında sessiz boş yerine 503 döner.
[ ] 6. Eldeki miktardan fazla SELL yapıldığında 409 Conflict döner; void işlem snapshot'ı etkilemez.
[ ] 7. Time-travel BTC 30k -> 60k testinde %100 PnL verir; value-series max 400 nokta sınırı uygular.
[ ] 8. AI servisinde ilk model 500 verirse ikincisi çalışır; tümü çökerse 502 döner; prompt injection önlenir.
[ ] 9. market_crash %50 şokunda sonuç portföy yaklaşık %50 düşer; horizonlar ve histogram doğru üretilir.
[ ] 10. Gölge portföy fırsat maliyeti senaryolarında doğru farkı üretir.
[ ] 11. Zamanlayıcı (APScheduler) vadesi dolan kararları EXPIRED yapar; ortam değişkeni ile kapatılabilir.
[ ] 12. Web arayüzünde giriş yapılır, paneller yüklenir, CSP ve konsol hatası oluşmaz.
[ ] 13. TODO ve plan belgelerinde işaretli her [x] gerçek bir teste dayanır.
```
