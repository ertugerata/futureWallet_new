# 🚀 FutureWallet

> **Bireysel Yatırımcılar İçin Akıllı Portföy, Karar Günlüğü ve Makro Simülasyon Sistemi**

FutureWallet, geleneksel portföy takip uygulamalarının ötesine geçerek yatırımcıların **karar alma süreçlerini**, **reel satın alma güçlerini** ve **geleceğe yönelik makro senaryolarını** takip etmelerini sağlayan açık kaynaklı bir karar destek platformudur.

---

## 🌟 Neden FutureWallet? (Piyasa Farkı)

Piyasadaki uygulamalar yalnızca *"Şu an ne kadar paranız var?"* sorusuna yanıt verir. FutureWallet ise şu 4 kritik soruya yanıt vermek için tasarlanmıştır:

1. **Reel Büyüme:** Portföyüm enflasyona (TÜİK/ENAG/US CPI), Altına veya S&P 500'e karşı gerçekten değer kazandı mı?
2. **Karar Günlüğü:** Bu alım/satım kararını verirken ne düşünüyordum? Psikolojik faktörler (FOMO, Panik vb.) performansımı nasıl etkiledi?
3. **Alternatif Senaryolar (What-If):** O hisseyi satmayıp tutsaydım veya Altın yerine S&P500 alsaydım şu an ne durumdaydım?
4. **Gelecek Simülasyonu:** Enflasyon, faiz veya kur şoklarında portföyümün risk ve getiri dağılımı (Monte Carlo + AI) ne olur?

---

## ✨ Temel Özellikler

- 📜 **Event Sourcing & İşlem Defteri (Ledger):** Tüm alım, satım, temettü ve transfer hareketlerinin zaman damgalı kaydı. İstenen geçmiş tarihe dönük anlık portföy snapshot'ı alma.
- 📓 **Karar Günlüğü (Decision Journal):** İşlem anında strateji notu ve duygu durumu kaydı. 3/6 ay sonra AI destekli karar retrospektifi (Post-Mortem).
- 📉 **Reel Değerleme & Benchmark Engine:** TÜİK, ENAG, US CPI, Gram Altın, S&P 500 ve Gösterge Mevduat ile enflasyondan arındırılmış reel getiri analizi.
- 🔀 **Gölge Portföy (Counterfactual Engine):** Alınmayan veya erken satılan kararların alternatif senaryolarla paralel takibi.
- 🎲 **Monte Carlo & AI Senaryo Motoru:** Tarihsel kriz testleri ve makro değişkenlerle (faiz/enflasyon/kur) geleceğe dönük risk haritası ve LLM destekli durum analizi.

---

## 🛠 Mimari ve Teknoloji Yığını

- **Backend:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy 2.0
- **Veri & Analiz:** Pandas, NumPy, SciPy (Monte Carlo simülasyonları)
- **Veri Tabanı:** SQLite / PostgreSQL (Event Sourcing yapısı)
- **Frontend:** HTML5, TailwindCSS, Chart.js / Plotly.js, HTMX / Alpine.js
- **Piyasa Veri Sağlayıcıları:** yfinance, TCMB EVDS API, TÜİK / ENAG serileri

---

## 🚀 Hızlı Başlangıç

### Gereksinimler
- Python 3.11 veya üzeri
- Git

### Kurulum

1. **Depoyu klonlayın:**
   ```bash
   git clone [https://github.com/ertugerata/futurewallet.git](https://github.com/ertugerata/futurewallet.git)
   cd futurewallet