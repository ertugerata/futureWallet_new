# 🚀 FutureWallet – MVP Dokümanı (PocketBase + FastAPI + OpenRouter)
> **Sürüm:** 2.0  
> **Mimari:** PocketBase (DB/Auth) + FastAPI (Hesaplama) + OpenRouter (LLM)  
> **Tarih:** Kasım 2026

---

## 1. Ürün Özeti & Vizyon

**FutureWallet**, yatırımcıların portföylerini sadece anlık fiyatlarla değil; **tarihsel zaman yolculuğu (Time-Travel)**, **enflasyondan arındırılmış satın alma gücü**, **karar psiko-analizi (Decision Journaling)** ve **AI/Monte Carlo stres testleri** ile yönetmelerini sağlayan yeni nesil bir **Finansal Karar Destek ve Öğrenme Platformudur**.

Piyasadaki geleneksel varlık takip uygulamalarından farklı olarak FutureWallet; *"Şu an ne kadarım var?"* sorusunun ötesine geçerek *"Bu kararı neden aldım?", "Satmasaydım ne olurdu?", "Enflasyona karşı gerçek satın alma gücüm ne durumda?"* ve *"Makro şoklarda portföyüm nasıl tepki verir?"* sorularına yanıt verir.

### Piyasadaki Uygulamalardan Farkı

1. **Reel Büyüme (Inflation-Adjusted Worth):** Portföyü nominal değerinin yanı sıra TÜİK/ENAG TÜFE, US CPI, Gram Altın ve S&P 500 bazında reel satın alma gücüyle ölçer.
2. **Karar Günlüğü (Decision Journaling & Sentiment):** Alım/satım kararlarındaki psikolojiyi (FOMO, Panik, Stratejik vb.) kaydeder ve 3/6 ay sonra AI destekli kararlılık retrospektifi sunar.
3. **Gölge Portföy (Counterfactual Engine):** "O hisseyi satmayıp tutsaydım ne olurdu?" sorusunu paralel bir gölge portföy ile yanıtlar.
4. **Makro Simülasyon (Stress Testing & Monte Carlo):** Faiz artışı, kur şoku veya küresel durgunluk gibi makro senaryolar altında portföy risk haritasını çıkarır.

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

* **Event-Sourcing Muhasebe Yapısı:** Tüm işlemler (Alım, Satım, Temettü, Nakit Akışı) zaman damgalı `Event` olarak PocketBase `transactions` koleksiyonunda tutulur.
* **Time-Travel Motoru:** Seçilen $T_{başlangıç}$ tarihindeki portföy snapshot'ı otomatik hesaplanır ve $T_{hedef}$ tarihindeki fiyatlarla değerlenir.
* **Fiyat Servisi:** `price_service.py` — yfinance, ccxt ve PocketBase `price_history` cache'ini birleştirir.

### 3.2. Modül 2: Karar Günlüğü & AI Retrospektifi (Decision Journaling)

* **Karar Kaydı:**
  * Karar Tarihi & Varlık / İşlem Tipi.
  * **Karar Gerekçesi** (Metin alanı, max 5000 karakter).
  * **Duygu Durumu Tag'leri:** `FOMO`, `STRATEGIC`, `PANIC`, `DIVIDEND`, `OPPORTUNITY`.
  * Hedef Fiyat & Beklenen Vade.
* **AI Post-Mortem (Karar Değerlendirme):** Vade sonunda OpenRouter LLM, kararın arkasındaki gerekçe ile piyasa gerçekleşmesini karşılaştırıp kullanıcıya Türkçe öğrenme notu sunar (*"FOMO kaynaklı alımlarınız ortalama %-12 kaybettirdi"*).
* **DELETE /api/decisions/{id}:** Kararı fiziksel olarak siler (bağlı gölge pozisyonlar da silinir).
* **GET /api/decisions/stats:** Sentiment ve action bazında karar istatistikleri (ortalama getiri, hedef tutma oranı).
* **Otomatik EXPIRED akışı:** Zamanlayıcı (APScheduler) ile vadesi geçmiş OPEN kararlar otomatik olarak EXPIRED yapılır ve outcome alanları doldurulur.

### 3.3. Modül 3: Gölge Portföy Motoru (Counterfactual / What-If Engine)

* **Karşılaştırmalı Takip:** Kullanıcının sattığı veya almayı düşünüp vazgeçtiği pozisyonlar "Gölge Portföy" olarak kaydedilir.
* **Otomatik Gölge Oluşturma:** Karar oluşturulduğunda (özellikle SELL işlemiyle ilişkili bir karar varsa) otomatik olarak `HELD_INSTEAD` gölge pozisyonu oluşturulur; kullanıcı manuel olarak `BOUGHT_INSTEAD` gölge pozisyonu da ekleyebilir.
* **API:** POST/GET/DELETE `/api/counterfactual/shadow-positions` uç noktaları; `GET /api/counterfactual?decision_id=` ile kıyaslama.
* **Fırsat Maliyeti Hesabı:** Gerçek Portföy Getirisi vs. Gölge Portföy Getirisi kıyası ile karar doğruluğu test edilir.
### 3.4. Modül 4: Reel Satın Alma Gücü & Multi-Benchmark

* **Nominal vs. Reel Getiri:** TÜİK TÜFE ve US CPI verileriyle enflasyondan arındırılmış net getiri (Real Return).
* **Varış Sepet Katsayısı:** Portföyün Gram Altın, S&P 500 ve Ortalama Ev/Kira katsayısı cinsinden değişimi.

### 3.5. Modül 5: Monte Carlo & AI Senaryo Motoru

* **Monte Carlo Simülasyonu:** Geçmiş volatilite ve korelasyon verilerine dayanarak 10.000 olasılıksal 3, 6 ve 12 aylık portföy değerleme dağılımları (GBM temsili ile drift düzeltmeli varyans düzeltmesi).
* **API:** GET `/api/simulation/monte-carlo` → histogram (40 kutu), p5/p50/p95 değerleri, `currency` alanı.
* **POST /api/simulation/stress-test:** Makro şok senaryoları altında portföy risk dağılımları (p5/p50/p95).
* **POST /api/simulation/narrative:** Simülasyon sonucu → Türkçe AI risk anlatısı.
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
│   ├── ai_service.py           # OpenRouter LLM Karar Yorumlama & Senaryo Anlatısı
│   └── price_service.py        # yfinance, ccxt, PB price_history cache birleştirici
├── web_app/                    # Web Arayüzü & Dashboard Components (HTML5 + Jinja2 + Chart.js + JavaScript)
└── docker-compose.yml          # PocketBase + FastAPI container tanımları

### Sistem Mimarisi

```
+--------------------------------------------------------+
|                     Frontend (Web UI)                  |
          HTML5 + Jinja2 + Chart.js + JavaScript            |
+---------------------------+----------------------------+
|                                        |
v                                        v
+-----------------------+        +-----------------------+
|  PocketBase Server    |        |  FastAPI Backend      |
|  - REST API & WebSockets|       |  - Ledger & Snapshot  |
|  - Auth & RLS         |        |  - Real Valuation     |
|  - SQLite Storage     |        |  - Monte Carlo & VaR  |
+-----------------------+        |  - OpenRouter AI      |
+-----------------------+--------+
|
v
+-----------------------+
|  OpenRouter Provider  |
|  (Claude/Gemini/DS)   |
+-----------------------+
```

---

## 5. PocketBase Veri Modeli (Collections)

### 5.1. `transactions` (İşlem Defteri)

| Alan | Tip | Açıklama |
|------|-----|----------|
| `id` | Text (PB default) | PK |
| `user` | Relation (users) | Sahip kullanıcı |
| `asset_symbol` | Text | Örn: `THYAO.IS`, `BTC/USDT`, `GC=F` |
| `type` | Select | `BUY`, `SELL`, `DIVIDEND`, `CASH_IN`, `CASH_OUT` |
| `quantity` | Number | İşlem miktarı |
| `price` | Number | Birim fiyat |
| `fee` | Number | İşlem ücreti |
| `timestamp` | DateTime | İşlem zaman damgası |
| `voided` | Bool | İptal/soft-delete kaydı |

### 5.2. `decisions` (Karar Günlüğü)

| Alan | Tip | Açıklama |
|------|-----|----------|
| `id` | Text | PK |
| `user` | Relation (users) | Sahip kullanıcı |
| `asset_symbol` | Text | Kararlı olduğu varlık |
| `action` | Select | `BUY`, `SELL`, `HOLD` |
| `sentiment` | Select | `FOMO`, `PANIC`, `STRATEGIC`, `DIVIDEND`, `OPPORTUNITY` |
| `rationale` | Text | Karar gerekçesi (max 5000 karakter) |
| `target_price` | Number | Hedef fiyat (opsiyonel) |
| `target_date` | DateTime | Hedef vade (opsiyonel) |
| `status` | Select | `OPEN`, `EXPIRED`, `REVIEWED`, `CLOSED` |
| `ai_retrospective` | Text | AI Post-Mortem notu |
 | `outcome_return_pct` | Number | Gerçekleşen getiri % |
 | `decision_date` | DateTime | Karar tarih (geçmiş olabilir) |
 | `outcome_price` | Number | Vade tarihi fiyatı (opsiyonel) |
 | `target_hit` | Bool | Hedef gerçekleşti mi (opsiyonel) |

### 5.3. `shadow_portfolios` (Gölge Portföy)

| Alan | Tip | Açıklama |
|------|-----|----------|
| `id` | Text | PK |
| `decision` | Relation (decisions) | Kaynağını çektığı karar |
| `asset_symbol` | Text | Gölge pozisyon varlığı |
| `shadow_type` | Select | `HELD_INSTEAD`, `BOUGHT_INSTEAD` |
| `entry_price` | Number | Giriş fiyatı |
| `quantity` | Number | Miktar |
 | `entry_date` | DateTime | Başlangıç tarihi |
 | `exit_date` | DateTime | Çıkış tarihi (opsiyonel) |
 | `asset_type` | Text | Varlık türü (opsiyonel) |

### 5.4. `macro_data` & `price_history`

* **macro_data:** Tarihsel TÜFE/CPI serileri (`date`, `gold_try`, `gold_usd`, `sp500`, `tr_cpi`, `us_cpi`).
* **price_history:** Varış sembollerinin günlük/historical fiyat cache'leri.

---

## 6. AI Servis Entegrasyonu (OpenRouter)

* **Provider:** OpenRouter (`https://openrouter.ai/api/v1`)
* **Modeller:** `anthropic/claude-3.5-sonnet`, `google/gemini-2.0-flash-001`, `deepseek/deepseek-r1`
* **Fallback Zinciri:** Birincil model yanıt vermediğinde otomatik ikincil modele geçiş.
* **Güvenlik Güvencesi:** Kullanıcı notları `<user_input>` etiketleri içinde verilerek prompt injection engellenir.

---

## 7. MVP Geliştirme Yol Haritası

| Aşama / Sprint | Görev Tanımı | Tahmini Süre |
| :--- | :--- | :--- |
 | **Sprint 1** | **Güvenlik, Altyapı & PocketBase Geçişi:** Auth/JWT katmanı, CSP/ALLOWED_ORIGINS, PB koleksiyon şemaları, SQLAlchemy → PB Async Client migrasyonu, docker-compose tanımları, **asset_symbol regex doğrulaması (Pydantic field_validator), web UI innerHTML→textContent güvenlik temizliği.** | 1 Hafta |
 | **Sprint 2** | **Reel Değerleme, Benchmark & Gölge Portföy:** Fiyat servisi (yfinance + ccxt + PB cache), time-travel endpoint, EVDS/TÜFE entegrasyonu, Gram Altın formülü, benchmark endpoint, **gölge portföy otomatik oluşturma (karar anında HELD_INSTEAD/BOUGHT_INSTEAD), POST/GET/DELETE shadow-positions endpoint'leri, fırsat maliyeti hesabı.** | 1 Hafta |
 | **Sprint 3** | **OpenRouter AI & Makro Simülasyon:** **OpenRouter client (fallback zinciri: claude-3.5-sonnet → gemini-2.0-flash → deepseek-r1)**, model fallback, karar retrospektifi endpoint, Monte Carlo (drift düzeltmeli GBM), **histogram (40 kutu), POST /api/simulation/stress-test, POST /api/simulation/narrative, AI risk anlatısı endpoint.** | 1 Hafta |
| **Sprint 4** | **Web Arayüzü & Yayına Hazırlık:** Karar formu doğrulamaları, USD/TRY seçici entegrasyonu, stres test histogram/p5/p50/p95 çizgileri, Docker USER app, requirements.txt sürüm kilitleme, pip-audit. | 1 Hafta |
