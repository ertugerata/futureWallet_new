# FutureWallet - Güncel İş Planı (PocketBase Backend)

## 📊 Mevcut Durum Özeti

### ✅ TAMAMLANANLAR (Prompt 1-15)

| Prompt | Konu | Durum | Notlar |
|--------|------|-------|--------|
| 0 | Ortak kurallar | ✅ | Testler, pytest, mock kullanımı |
| 1 | Kimlik doğrulama, CORS, Host | ✅ | API_TOKEN, ALLOWED_ORIGINS, CSP, TrustedHost, rate-limit |
| 2 | Stored XSS, girdi doğrulama | ✅ | asset_symbol regex, innerHTML→textContent, CSP |
| 3 | Kaynak tüketimi/DoS | 🔄 | Simulation limitleri var, AssetManager singleton, Monte Carlo vektörize |
| 4 | Snapshot date hatası | ✅ | as_of parametresi düzeltildi |
| 5 | Karar formu boş alan/badge | ✅ | apiFetch, işlemler sütunu, boş→None |
| 6 | DB yolu, Docker kalıcılığı | 🔄 | db.py sımplifikasyon, Alembic kaldırıldı, PB entegre |
| 7 | AI servisi hata yutma | ✅ | google-genai, AIUnavailableError, prompt injection |
| 8 | Transaction API + ledger | 🔄 | Endpoint'ler var, average cost ve K/Z eklendi, 409 hâlâ eksik |
| 9 | Gerçek tarihsel fiyatla Time-Travel | ✅ | price_service.py, historical fiyatlar, missing_prices, value-series |
| 10 | Monte Carlo + Stres testi | ✅ | Endpoint'ler eklendi (stress-test, narrative), histogram, p5/p50/p95 |
| 11 | Benchmark / enflasyon | ✅ | Endpoint eklendi, EVDS/TÜFE/FRED, gold_try_gram |
| 12 | Gölge portföy (counterfactual) | ✅ | PB kullanıyor, endpoint'ler eklendi, track_shadow implementasyonlu |
| 13 | Karar günlüğü eksikleri | ✅ | stats endpoint, DELETE endpoint, OPPORTUNITY eklendi |
| 14 | Web arayüzü tamamlama | ✅ | İşlemler sütunu, sentiment kartı, USD/TRY seçici, histogram |
| 15 | Docker sertleştirme, CI, docs | ✅ | requirements.txt, GitHub Actions, README, disclaimer |

---

## ❌ KALAN DEĞİŞİKLİKLER

### Kritik / Yüksek Öncelik

#### Prompt 1 - Rate Limiter Testleri
- [ ] `test_retrospective_under_rate_limit[2-5]` → 429 hâlâ fail ediyor
  - **Sebep**: `_RETRO_RATE_LIMITS` global dict, testler arası state accumulation
  - **Çözüm**: Test fixture isolasyonu veya rate limiter mock'lanmalı

#### Prompt 3 - Kaynak Tüketimi/DoS (Eksik kısımlar)
- [ ] Request body size limit middleware'i yok (64KB sınırı)
- [ ] AssetManager tam singleton değil, her import yeni instance
- [ ] yfinance/ccxt timeout eklenmemiş
- [ ] TTL cache implementation eksik

#### Prompt 6 - DB/Docker Kalıcılık (Eksik kısımlar)
- [ ] `DATABASE_URL` hâlâ config.py'de ve db.py'de kullanılıyor (testler için gerekli)
- [ ] `git rm --cached futurewallet.db` yapılmamış (eğer varsa)
- [ ] Docker volume mount kontrolü (docker-compose.yml)

#### Prompt 8 - Transaction API/Ledger (Eksik kısımlar)
- [ ] **409 Conflict**: Stok yetersizliğinde SELL reddi yok
- [ ] DIVIDEND cash_received gösterimi snapshot'ta
- [ ] Fee maliyet bazına eklenmeli

### Orta Öncelik

#### Prompt 11 - Benchmark Zamanlayıcı
- [ ] **Zamanlayıcı yok**: Günlük benchmark/makro güncellemesi yapılmıyor
- [ ] `schedule` veya APScheduler lifespan'a eklenmeli
- [ ] `auto_close_expired_decisions` fonksiyonu var ama çağrılmıyor

#### Prompt 13 - Otomatik EXPIRED Akışı
- [ ] `auto_close_expired_decisions()` fonksiyonu varsa da zamanlayıcıyla çalışmıyor
- [ ] Outcome alanları (outcome_return_pct, outcome_price, target_hit) PB şemasında olabilir ama doldurulmuyor

#### Prompt 14 - Stres Testi UI (Eksik kısımlar)
- [ ] Stres test senaryosu seçimi UI'da yok (faiz artışı/indirimi, kur şoku, vs.)
- [ ] AI risk anlatısı tam integrate değil

### Düşük Öncelik

#### Prompt 15 - Kod Temizliği
- [ ] `_guess_asset_type` tekrarı: api/app.py, ledger_service, decision_service - tek yerde olmalı
- [ ] `decision_to_dict` tekrarı: api/app.py ve decision_service
- [ ] Ölü kodlar: `future_price.py`, kullanılmayan importlar
- [ ] `DEBUG`, `APP_HOST`, `APP_PORT` config'de lazım mı?

---

## 📝 TODO.md İşaretlemeleri (Güncellenecek)

Aşağıdaki maddeler TODO.md'de `[ ]` olarak görünüyor ama **aslında tamamlanmış**:

### Sprint 1
- [x] `services/simulation_service.py` → PB'ye bağımlı değil (YANLIŞ: simulation endpoint'leri eklendi)
- [ ] `services/counterfactual_service.py` → PB geçiş yapılmadı (YANLIŞ: PB kullanıyor, endpoint'ler eklendi)
- [x] `time_travel_portfolio` düzeltmesi (DOĞRU: Tamamlandı)

### Sprint 2
- [ ] `price_service.py` yaz (YANLIŞ: Oluşturuldu)
- [ ] GET `/api/portfolio/value-series` (YANLIŞ: Eklendi)
- [ ] Zamanlayıcı (YANLIŞ: Hâlâ yok)
- [ ] Karar anında otomatik gölge (YANLIŞ: track_shadow implementasyonlu, UI eklendi)
- [ ] POST `/api/counterfactual/shadow-positions` (YANLIŞ: Eklendi)

### Sprint 3
- [ ] POST `/api/simulation/stress-test` (YANLIŞ: Eklendi)
- [ ] POST `/api/simulation/narrative` (YANLIŞ: Eklendi)
- [ ] Monte Carlo histogram/p5/p50/p95 (YANLIŞ: Endpoint'de var, UI'da CSS/JS eklendi)

### Sprint 4
- [ ] USD/TRY seçici (YANLIŞ: Eklendi)
- [ ] Stres test histogram/p5/p50/p95 (YANLIŞ: CSS/JS eklendi)
- [ ] Karar tablosuna İşlemler sütunu (YANLIŞ: Eklendi)
- [ ] Sentiment özet kartı (YANLIŞ: Eklendi)
- [ ] requirements.txt sabitle/pip-audit (YANLIŞ: Tamamlandı)
- [ ] CI GitHub Actions (YANLIŞ: Oluşturuldu)
- [ ] README.md güncelleme (YANLIŞ: Güncellendi)
- [ ] Disclaimer uyarısı (YANLIŞ: Eklendi)

### Faz 2
- [ ] Gölge portföy PB geçişi (YANLIŞ: PB kullanıyor, endpoint'ler eklendi)
- [ ] GET `/api/decisions/stats` (YANLIŞ: Eklendi)
- [ ] DELETE `/api/decisions/{id}` (YANLIŞ: Eklendi)
- [ ] Otomatik EXPIRED akışı (YANLIŞ: Fonksiyon var, zamanlayıcı eksik)

### Faz 3
- [ ] `/api/simulation/stress-test` ve `/api/simulation/narrative` (YANLIŞ: Endpoint'ler eklendi)

### Faz 4
- [ ] `/api/portfolio/benchmarks` (YANLIŞ: Eklendi)
- [ ] `/api/simulation/stress-test` ve `/api/simulation/narrative` (YANLIŞ: Eklendi)
- [ ] `/api/counterfactual/shadow-positions` (YANLIŞ: Eklendi)

---

## 🗺️ Önerilen Sprint Planı (Kalanlar için)

### Sprint 8 - Test & Quality Fixleri (1 Hafta)
1. Rate limiter test fix'i (test_retrospective_under_rate_limit[2-5])
2. test_rationale_exactly_5000_accepted fix'i
3. Request body size limit middleware'i
4. AssetManager singleton + timeout implementasyonu
5. yfinance/ccxt timeout ekleme
6. TTL cache implementasyonu

### Sprint 9 - Ledger & Transaction İyileştirmeleri (1 Hafta)
1. 409 Conflict hatası (stok yetersizliği)
2. DIVIDEND cash_received snapshot'ta
3. Fee maliyet bazına ekleme
4. Ottomatik EXPIRED akışı + zamanlayıcı
5. Outcome alanları doldurulması

### Sprint 10 - Zamanlayıcı & Production (1 Hafta)
1. APScheduler-like zamanlayıcı (benchmark güncelleme, auto_close_expired)
2. Kod tekrarini temizleme (_guess_asset_type, decision_to_dict)
3. Ölü kod temizleme
4. Stres test senaryosu seçimi UI
5. AI risk anlatısı tam integrate

---

## 📋 Hızlı Kontrol Listesi

```text
1. ✅ Token'sız /api/* → 401
2. ✅ XSS payload'lı sembol reddedilir
3. ⚠️ simulations=1e6 → 422 (limit var ama body size limit yok)
4. ✅ /api/portfolio/snapshot?date=... → 200
5. ✅ Boş opsiyonel alanlarla karar kaydı çalışır
6. ⚠️ Docker veri kalıcılığı (volume mount kontrolü needed)
7. ✅ AI hata verince kayıt değişmez (502/503)
8. ⚠️ Transaction eklenir, 409 yok
9. ✅ /stress-test ve /narrative endpoint'leri var
10. ✅ EVDS anahtarı yokken sahte TÜFE yok, gold_try dolu
11. ✅ Gölge portföy karşılaştırması endpoint'leri var
12. ❌ TODO.md işaretleri gerçek durumla örtüşmüyor (güncellenmeli)
13. ❌ Rate limiter testleri fail ediyor
14. ❌ Zamanlayıcı yok
15. ❌ 409 Conflict hatası yok
```
