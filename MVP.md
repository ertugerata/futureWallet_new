# FutureWallet - MVP (Minimum Viable Product) Ürün Dokümanı

## 1. Ürün Özeti & Vizyon
**FutureWallet**, yatırımcıların portföylerini sadece anlık fiyatlarla değil; **tarihsel zaman yolculuğu (Time-Travel)**, **enflasyondan arındırılmış satın alma gücü**, **karar psiko-analizi (Decision Journaling)** ve **AI/Monte Carlo stres testleri** ile yönetmelerini sağlayan yeni nesil bir **Finansal Karar Destek ve Öğrenme Platformudur**.

Piyasadaki geleneksel varlık takip uygulamalarından farklı olarak FutureWallet; *"Şu an ne kadarım var?"* sorusunun ötesine geçerek *"Bu kararı neden aldım?", "Satmasaydım ne olurdu?", "Enflasyona karşı gerçek satın alma gücüm ne durumda?"* ve *"Makro şoklarda portföyüm nasıl tepki verir?"* sorularına yanıt verir.

---

## 2. Temel Hedefler & Kullanıcı İhtiyaçları

1. **Tarihsel Zaman Yolculuğu (Time-Travel Valuation):** Geçmiş belirli bir tarihteki portföy bileşiminin, hedef tarihteki veya bugünkü fiyatlarla net değerini ve P&L değişimini anlık hesaplamak.
2. **Yatırım Karar Günlüğü & Duygu Analizi (Decision Journal & Post-Mortem):** Alınan stratejik kararları gerekçesi, hedef vadeleri ve duygu durumu (FOMO, Analiz, Panik vb.) ile kaydetmek; AI ile geçmiş kararların retrospektif değerlendirmesini yapmak.
3. **Gölge Portföy & "Ne Olurdu?" Motoru (Counterfactual Engine):** Erken satılan veya alınmaktan vazgeçilen varlıkların "gölge portföyünü" paralel takip ederek kararların fırsat maliyetini ölçmek.
4. **Reel Satın Alma Gücü & Multi-Benchmark:** Portföyü nominal TRY/USD cinsinden değil; Gram/Ons Altın, S&P 500, TÜİK TÜFE ve US CPI verileriyle arındırarak gerçek satın alma gücü artış/azalışını ölçmek.
5. **Dinamik Stres Testi & AI Senaryo Motoru:** Monte Carlo simülasyonları ve LLM desteği ile makroekonomik şok senaryolarında (TCMB faiz değişimi, Fed kararları, emtia şokları) portföyün direnç haritasını çıkarmak.

---

## 3. MVP Özellik Kapsamı & Modül Detayları

### 3.1. Modül 1: Tarihsel Portföy Değerleme & İşlem Defteri (Ledger Engine)
* **Event-Sourcing Muhasebe Yapısı:** Tüm işlemler (Alım, Satım, Temettü, Nakit Akışı) zaman damgalı `Event` olarak tutulur.
* **Time-Travel Motoru:** Seçilen $T_{başlangıç}$ tarihindeki portföy snapshot'ı otomatik hesaplanır ve $T_{hedef}$ tarihindeki fiyatlarla değerlenir.

### 3.2. Modül 2: Karar Günlüğü & AI Retrospektifi (Decision Journaling)
* **Karar Kaydı:**
  * Karar Tarihi & Varlık / İşlem Tipi.
  * **Karar Gerekçesi** (Metin alanı: bilanço beklentisi, teknik kırılım vb.).
  * **Duygu Durumu Tag'leri:** `FOMO`, `Stratejik Analiz`, `Panik Satışı`, `Temettü/Gelir`, `Risk Azaltma`.
  * Hedef Fiyat & Beklenen Vade.
* **AI Post-Mortem (Karar Değerlendirme):** Vade sonunda AI, kararın arkasındaki gerekçe ile piyasa gerçekleşmesini karşılaştırıp kullanıcıya öğrenme notu sunar (*"FOMO kaynaklı alımlarınız ortalama %-12 kaybettirdi"*).

### 3.3. Modül 3: Gölge Portföy Motoru (Counterfactual / What-If Engine)
* **Karşılaştırmalı Takip:** Kullanıcının sattığı veya almayı düşünüp vazgeçtiği pozisyonlar "Gölge Portföy" olarak kaydedilir.
* **Fırsat Maliyeti Hesabı:** Gerçek Portföy Getirisi vs. Gölge Portföy Getirisi kıyası ile karar doğruluğu test edilir.

### 3.4. Modül 4: Reel Satın Alma Gücü & Multi-Benchmark
* **Nominal vs. Reel Getiri:** TÜİK TÜFE ve US CPI verileriyle enflasyondan arındırılmış net getiri (Real Return).
* **Varlık Sepet Katsayısı:** Portföyün Gram Altın, S&P 500 ve Ortalama Ev/Kira katsayısı cinsinden değişimi.

### 3.5. Modül 5: Monte Carlo & AI Senaryo Motoru
* **Monte Carlo Simülasyonu:** Geçmiş volatilite ve korelasyon verilerine dayanarak 10.000 olasılıklı 3, 6 ve 12 aylık portföy değerleme dağılımları.
* **Makro Stres Testleri:** Faiz artışı, faiz indirimi, döviz şoku ve küresel durgunluk senaryoları.
* **AI Risk Anlatısı:** Karmaşık sayısal simülasyon çıktılarını sade Türkçe metin ve risk tavsiyelerine dönüştüren LLM entegrasyonu.

---

## 4. Mimari Yapı & Veri Katmanı

```text
FutureWallet/
├── api/
│   └── app.py                  # FastAPI REST Uç Noktaları
├── services/
│   ├── ledger_service.py       # Event-Sourcing İşlem ve Snapshot Motoru
│   ├── benchmark_service.py    # Altın, SP500, TÜFE (EVDS/FRED) Entegrasyonu
│   ├── decision_service.py     # Karar Günlüğü & Post-Mortem Analizörü
│   ├── counterfactual_service.py # Gölge Portföy / What-If Motoru
│   ├── simulation_service.py   # Monte Carlo & Stres Testi Engine
│   └── ai_service.py           # Gemini LLM Karar Yorumlama & Senaryo Anlatısı
├── db.py                       # SQLAlchemy Veritabanı Modelleri
└── web_app/                    # Web Arayüzü & Dashboard Components
```

---

## 5. Veritabanı Şeması (MVP)

### 5.1. `transactions` (İşlem Defteri)
* `id`: UUID PRIMARY KEY
* `timestamp`: DATETIME
* `asset_symbol`: VARCHAR(20)
* `type`: VARCHAR(10) (BUY, SELL, DIVIDEND, CASH_IN, CASH_OUT)
* `quantity`: FLOAT
* `price`: FLOAT
* `fee`: FLOAT

### 5.2. `decisions` (Karar Günlüğü)
* `id`: UUID PRIMARY KEY
* `transaction_id`: UUID (FK, opsiyonel)
* `date`: DATETIME
* `asset_symbol`: VARCHAR(20)
* `action`: VARCHAR(10)
* `rationale`: TEXT
* `sentiment`: VARCHAR(30) (FOMO, STRATEGIC, PANIC, DIVIDEND)
* `target_price`: FLOAT
* `target_date`: DATE
* `status`: VARCHAR(20) (OPEN, REVIEWED, EXPIRED)
* `ai_retrospective`: TEXT

### 5.3. `shadow_portfolios` (Gölge Portföy / What-If)
* `id`: UUID PRIMARY KEY
* `decision_id`: UUID (FK)
* `asset_symbol`: VARCHAR(20)
* `simulated_action`: VARCHAR(10) (HELD_INSTEAD, BOUGHT_INSTEAD)
* `entry_date`: DATETIME
* `entry_price`: FLOAT
* `quantity`: FLOAT

### 5.4. `macro_data` (Benchmark & Enflasyon Önbelleği)
* `date`: DATE PRIMARY KEY
* `gold_try`: FLOAT
* `gold_usd`: FLOAT
* `sp500`: FLOAT
* `tr_cpi`: FLOAT (TÜİK TÜFE Endeksi)
* `us_cpi`: FLOAT (US CPI Endeksi)

---

## 6. MVP Geliştirme Yol Haritası (Roadmap)

| Aşama | Görev Tanımı | Tahmini Süre |
| :--- | :--- | :--- |
| **Aşama 1** | **Veritabanı & Ledger Yapısı:** Multi-asset transaction ledger ve makro veri caching mimarisinin kurulması. | 1 Hafta |
| **Aşama 2** | **Reel Değerleme & Time-Travel:** Tarihsel snapshot motoru ve Enflasyon/Gold/SP500 arındırılmış getiri hesaplamaları. | 1 Hafta |
| **Aşama 3** | **Karar Günlüğü & Gölge Portföy:** Karar kayıt arayüzü, duygu tag'leri ve "Satmasaydım Ne Olurdu?" simülasyonu. | 1 Hafta |
| **Aşama 4** | **Monte Carlo & AI Senaryo Motoru:** Monte Carlo algoritması, makro stres testleri ve AI Post-Mortem/Risk anlatısı. | 1 Hafta |
| **Aşama 5** | **UI Entegrasyonu & MVP Lansmanı:** Responsive web panellerinin (Dashboard, Journal, Simulator) yayınlanması. | 1 Hafta |