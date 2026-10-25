# FutureWallet Web Uygulaması - TODO Listesi

Güncellenmiş **FutureWallet MVP Dokümanı** doğrultusunda projenin backend servisleri, veri modelleri, AI entegrasyonları ve web arayüz bileşenlerini hayata geçirecek adım adım yapılacaklar listesi.

---

## 🏗️ Faz 1: Altyapı, Veritabanı & Ledger Katmanı

* [ ] **1.1. Veritabanı Şemasının Yeniden Yapılandırılması (`db.py`)**
  * [ ] Transaction Ledger (`transactions`) tablosunu oluştur (`id`, `timestamp`, `asset_symbol`, `type`, `quantity`, `price`, `fee`).
  * [ ] Karar Günlüğü (`decisions`) tablosunu tanımla (`id`, `transaction_id`, `date`, `asset_symbol`, `action`, `rationale`, `sentiment`, `target_price`, `target_date`, `status`, `ai_retrospective`).
  * [ ] Gölge Portföy (`shadow_portfolios`) tablosunu tanımla (`id`, `decision_id`, `asset_symbol`, `simulated_action`, `entry_date`, `entry_price`, `quantity`).
  * [ ] Makro & Benchmark verileri (`macro_data`) tablosunu tanımla (`date`, `gold_try`, `gold_usd`, `sp500`, `tr_cpi`, `us_cpi`).

* [ ] **1.2. Makro Veri Servisi (`services/benchmark_service.py`)**
  * [ ] Yahoo Finance / Alpha Vantage API entegrasyonu (Gram Altın, Ons Altın, S&P 500).
  * [ ] TCMB EVDS API / TÜİK TÜFE aylık enflasyon serisi çekme ve önbellekleme.
  * [ ] FRED API üzerinden ABD Enflasyon (US CPI) veri serisini entegre etme.
  * [ ] Makro verileri günlük ve aylık periyotta `macro_data` tablosuna yazan cron/job mekanizması.

* [ ] **1.3. Ledger & Tarihsel Snapshot Servisi (`services/ledger_service.py`)**
  * [ ] Belirli bir $T$ tarihi itibarıyla portföy varlık adetlerini event log'lardan hesaplayan `get_portfolio_snapshot(date)` fonksiyonu.
  * [ ] İki tarih ($T_1$ ve $T_2$) arasındaki portföy değişimini hesaplayan Time-Travel değerleme fonksiyonu.

---

## 📊 Faz 2: Reel Değerleme, Benchmark & Karar Günlüğü

* [ ] **2.1. Reel Değerleme & Enflasyon Motoru (`services/benchmark_service.py`)**
  * [ ] TÜİK ve ABD enflasyon indeksleri kullanılarak nominal portföy tutarını reel satın alma gücüne çeviren metot.
  * [ ] Portföyün Gram Altın, S&P 500 ve Gösterge Sepet bazında göreli performansını (Alpha) hesaplama.

* [ ] **2.2. Karar Günlüğü & Duygu Analiz Servisi (`services/decision_service.py`)**
  * [ ] Karar ekleme, güncelleme ve tamamlama CRUD işlemleri.
  * [ ] Duygu durum tag'leri (`FOMO`, `Stratejik`, `Panik`, `Temettü`) ile kararları filtreleme ve sınıflandırma.
  * [ ] Kararların hedef fiyat/vade gerçekleşme oranlarını hesaplama logic'i.

* [ ] **2.3. Gölge Portföy Motoru (`services/counterfactual_service.py`)**
  * [ ] Karar anında satılan veya alınmayan varlığın "Gölge Pozisyon" olarak oluşturulması.
  * [ ] Gerçek Portföy vs. Gölge Portföy performans farkını (Fırsat Maliyeti) anlık hesaplayan simülatör.

---

## 🤖 Faz 3: Monte Carlo, Makro Stres Testi & AI Entegrasyonu

* [ ] **3.1. Monte Carlo Simülasyon Servisi (`services/simulation_service.py`)**
  * [ ] Varlıkların tarihsel getiri ve volatilite/korelasyon matrislerini kullanarak 10.000 patikalı Monte Carlo simülasyonu.
  * [ ] 3, 6 ve 12 aylık %5 (Bear), %50 (Base), %95 (Bull) güven aralığı değerlerini üretme.
  * [ ] Makro Şok Senaryoları: Faiz artışı/indirimi veya döviz şoku parametrik stres testleri.

* [ ] **3.2. AI Yorumlama Servisi (`services/ai_service.py`)**
  * [ ] **AI Karar Retrospektifi (Post-Mortem):** Vadesi dolan kararlar için gerekçe ve gerçekleşen fiyatı LLM'e gönderip Türkçe değerlendirme notu alma.
  * [ ] **AI Risk & Senaryo Anlatısı:** Monte Carlo ve stres testi sonuçlarını sade Türkçe risk/fırsat analiz metnine dönüştürme.

---

## 🌐 Faz 4: REST API & Web Arayüzü Entegrasyonu

* [ ] **4.1. REST API Uç Noktaları (`api/app.py`)**
  * [ ] `/api/portfolio/snapshot`: Tarihsel ve anlık portföy değerleme uç noktası.
  * [ ] `/api/portfolio/real-valuation`: Enflasyon ve benchmark arındırılmış veriler.
  * [ ] `/api/decisions`: Karar günlüğü CRUD ve retrospektif uç noktaları.
  * [ ] `/api/counterfactual`: Gölge portföy karşılaştırma verisi.
  * [ ] `/api/simulation/monte-carlo`: Monte Carlo ve stres testi sonuçları.

* [ ] **4.2. Web Dashboard & Görselleştirme (`web_app/`)**
  * [ ] **Time-Travel Dashboard:** Tarih seçici ile portföyün geçmiş/güncel değer grafiği.
  * [ ] **Karar Günlüğü Paneli:** İşlem gerekçesi, duygu tag'leri ekleme formu ve AI Post-Mortem görünümü.
  * [ ] **"Ne Olurdu?" (What-If) Paneli:** Gerçek vs. Gölge portföy grafiksel kıyaslaması.
  * [ ] **Stres Testi & Gelecek Senaryoları Paneli:** Monte Carlo dağılım grafiği ve AI risk anlatısı kartı.