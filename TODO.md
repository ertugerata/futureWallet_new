# FutureWallet – TODO & Sprint Takip Listesi

> ⚠️ **Not:** Faz 1-4'teki `[x]` işaretleri **hızlı prototip / scaffolding aşamasını** ifade eder — kod çalışır ama güvenlik, doğrulama, test ve prod hazırlığı henüz yapılmamıştır. Gerçek düzeltmeler (Prompt 1 → 15) henüz **tamamlanmamıştır**. Prod'a çıkışı için tüm "kritik" ve "yüksek" düzeltmeleri uygulanıp testleri geçirilmelidir. **Sprint 1-4'teki `[ ]` item'ları en Güncel yapılacaklar listesidir.**

Güncellenmiş **FutureWallet MVP Dokümanı (v2.0)** doğrultusunda projenin güvenlik, PocketBase entegrasyonu, backend servisleri, veri modelleri, AI entegrasyonları, web arayüz bileşenleri ve dağıtım adımlarını kapsayan sprint bazlı yapılacaklar listesi.

---
## 🏃 Sprint 1: Güvenlik, Altyapı ve PocketBase Entegrasyonu

### 1.1 Güvenlik Sertleştirmesi

- [ ] FastAPI ve PocketBase JWT ile API Token / Auth katmanını yapılandır.
- [ ] `ALLOWED_ORIGINS`, `ALLOWED_HOSTS` ve CSP başlıklarını middleware olarak ekle.
- [ ] `asset_symbol` ve metin girdileri için Regex doğrulaması ekle (`^[A-Z0-9.=^\-/]{1,20}$`).
- [ ] Web arayüzünde `innerHTML` kullanımını temizle; `textContent` ve DOM düğümlerine geç.

### 1.2 PocketBase Veri Katmanı Geçişi

- [ ] PocketBase koleksiyon şemalarını (`transactions`, `decisions`, `shadow_portfolios`, `macro_data`, `price_history`) oluştur.
- [ ] SQLAlchemy / SQLite doğrudan bağımlılıklarını PocketBase Async Python Client / SDK ile değiştir.
- [ ] `docker-compose.yml` içine PocketBase servisini ekle ve `./pb_data` kalıcılığını sağla.

### 1.3 İşlem Defteri (Ledger Engine)

- [ ] POST / GET / DELETE `/api/transactions` endpoint'lerini tanımla.
- [ ] Stok veya bakiye yetersizliğinde 409 (Conflict) hatası döndür.
- [ ] Event Sourcing snapshot mantığını `timestamp < as_of + 1 gün` şeklinde güncelle.

---
## 🏃 Sprint 2: Reel Değerleme, Benchmark ve Gölge Portföy

### 2.1 Zaman Yolculuğu ve Fiyat Servisi

- [ ] `price_service.py` yaz; yfinance, ccxt ve PocketBase `price_history` cache'ini bağla.
- [ ] GET `/api/portfolio/time-travel` endpoint'i ile sabit dağılım vs gerçek performans kıyası sun.

### 2.2 Benchmark & Enflasyon Verisi

- [ ] TCMB EVDS API entegrasyonunu resmi dokümana göre düzelt (`key` başlığı).
- [ ] Gram Altın TL formülünü `(GC=F / 31.1035) * USDTRY=X` olarak ekle.
- [ ] GET `/api/portfolio/benchmarks` ile Alpha ve Reel Getiri değerlerini hesapla.

### 2.3 Gölge Portföy (Counterfactual Engine)

- [ ] Karar anında otomatik `HELD_INSTEAD` / `BOUGHT_INSTEAD` gölge kaydı oluştur.
- [ ] Fırsat maliyetini `gölge_değer - gerçek_değer` olarak hesapla.

---
## 🏃 Sprint 3: OpenRouter AI ve Makro Simülasyon

### 3.1 OpenRouter Entegrasyonu

- [ ] `ai_service.py` içinde OpenRouter API istemcisini kur.
- [ ] Model fallback zincirini (`claude-3.5-sonnet` → `gemini-2.0-flash` → `deepseek-r1`) tanımla.
- [ ] Prompt injection korumalarını ekle (`<user_input>` sınırlandırıcıları).
- [ ] Karar retrospektifi için POST `/api/decisions/{id}/retrospective` uç noktasını bağla.

### 3.2 Monte Carlo & Stres Testi

- [ ] GBM simülasyonundaki drift çift-varyans düzeltme hatasını gider.
- [ ] POST `/api/simulation/stress-test` endpoint'ini varlık duyarlılık matrisiyle yaz.
- [ ] POST `/api/simulation/narrative` ile OpenRouter üzerinden risk anlatısı üret.

---
## 🏃 Sprint 4: Web Arayüzü ve Yayına Hazırlık

### 4.1 Web Arayüzü İyileştirmeleri

- [ ] Karar formunda boş string gönderimlerini temizleyen `apiFetch` sarmalayıcısını ekle.
- [ ] USD/TRY görünüm seçicisini tüm grafik ve tablolara entegre et.
- [ ] Stres testi paneline histogram ve p5 / p50 / p95 dikey çizgilerini ekle.

### 4.2 Dağıtım ve Sertleştirme

- [ ] Dockerfile için `USER app` root-olmayan kullanıcı yapılandırmasını yap.
- [ ] `requirements.txt` içindeki bağımlılık sürümlerini sabitle ve `pip-audit` testini geç.

---
## 📌 Not: Faz 1-4 (Geçiş Öncesi Arka Plan Çalışmaları)

> Aşağıdaki görevler, PocketBase + OpenRouter mimarisine geçiş öncesi yürütülen temel servis geliştirme aşamalarını belgelemektedir. Sprint 1-4 ile çakışan alanlar yeni sprint yapısına uygun şekilde yeniden yazılmıştır. Eski réalisasyon kayıtları münhasıran tinyint/ boolean işaretleriyle taşınmıştır.

### Faz 1: Altyapı, Veritabanı & Ledger Katmanı *(kısa özet – detay Sprint 1'e dahil)*

- [x] Transaction Ledger (`transactions`) tablosunu oluştur.
- [x] Karar Günlüğü (`decisions`) tablosunu tanımla.
- [x] Gölge Portföy (`shadow_portfolios`) tablosunu tanımla.
- [x] Makro & Benchmark verileri (`macro_data`) tablosunu tanımla.
- [x] Makro Veri Servisi (`benchmark_service.py`) — Yahoo Finance / Alpha Vantage, TCMB EVDS / TÜİK TÜFE, FRED US CPI entegrasyonları ve cron önbellek mekanizması.
- [x] Ledger & Tarihsel Snapshot Servisi (`ledger_service.py`) — `get_portfolio_snapshot(date)` ve Time-Travel P&L fonksiyonları.

### Faz 2: Reel Değerleme, Benchmark & Karar Günlüğü *(kısa özet)*

- [x] Reel Değerleme & Enflasyon Motoru — TÜİK ve ABD enflasyon indeksleri ile nominal → reel dönüşüm; Gram Altın, S&P 500 ve gösterge sepet bazında Alpha hesaplama.
- [x] Karar Günlüğü & Duygu Analiz Servisi (`decision_service.py`) — CRUD, duygu tag filtreleme, hedef fiyat/vade gerçekleşme oranı.
- [x] Gölge Portföy Motoru (`counterfactual_service.py`) — otomatik gölge pozisyon oluşturma ve fırsat maliyeti simülatörü.

### Faz 3: Monte Carlo, Makro Stres Testi & AI Entegrasyonu *(kısa özet)*

- [x] Monte Carlo Simülasyon Servisi (`simulation_service.py`) — tarihsel getiri+volatilite/korelasyon matrisiyle 10.000 patikalı simülasyon; 3/6/12 ay %5 / %50 / %95 güven aralıkları; parametrik makro şok stres testleri.
- [x] AI Yorumlama Servisi (`ai_service.py`) — karar Post-Mortem Türkçe değerlendirme notu; Monte Carlo/stres test sonucu → sade Türkçe risk analizi metni.

### Faz 4: REST API & Web Arayüzü Entegrasyonu *(kısa özet)*

- [x] REST API Uç Noktaları (`api/app.py`) — `/api/portfolio/snapshot`, `/api/portfolio/real-valuation`, `/api/decisions`, `/api/counterfactual`, `/api/simulation/monte-carlo`.
- [x] Web Dashboard & Görselleştirme (`web_app/`) — Time-Travel Dashboard, Karar Günlüğü Paneli, "Ne Olurdu?" (What-If) Paneli, Stres Testi & Gelecek Senaryoları Paneli.
