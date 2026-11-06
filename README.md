# 🚀 FutureWallet

> **Bireysel Yatırımcılar İçin Akıllı Portföy, Karar Günlüğü ve Makro Simülasyon Sistemi**

FutureWallet, geleneksel portföy takip uygulamalarının ötesine geçerek yatırımcıların **karar alma süreçlerini**, **reel satın alma güçlerini** ve **geleceğe yönelik makro senaryolarını** takip etmelerini sağlayan açık kaynaklı bir karar destek platformudur.

---

## 🌟 Neden FutureWallet? (Piyasa Farkı)

Piyasadaki uygulamalar yalnızca *"Şu an ne kadar paranız var?"* sorusuna yanıt verir. FutureWallet ise şu 4 kritik soruya yanıt vermek için tasarlanmıştır:

1. **Reel Büyüme:** Portföyüm enflasyona (TÜİK/ENAG/US CPI), Altına veya S&P 500'e karşı gerçekten değer kazandı mı?
2. **Karar Günlüğü:** Bu alım/satım kararını verirken ne düşünüyordum? Psikolojik faktörler (FOMO, Panik vb.) performansımı nasıl etkiledi?
3. **Alternatif Senaryolar (What-If):** O hisseyi satmayıp tutsaydım veya Altın yerine S&P 500 alsaydım şu an ne durumdaydım?
4. **Gelecek Simülasyonu:** Enflasyon, faiz veya kur şoklarında portföyümün risk ve getiri dağılımı (Monte Carlo + AI) ne olur?

---

## ✨ Temel Özellikler

- 📜 **Event Sourcing & İşlem Defteri (Ledger):** Tüm alım, satım, temettü ve nakit hareketlerinin zaman damgalı kaydı. İstenen geçmiş tarihe dönük anlık portföy snapshot'ı alma.
- 📓 **Karar Günlüğü (Decision Journal):** İşlem anında strateji notu ve duygu durumu kaydı (FOMO, STRATEGIC, PANIC, DIVIDEND, OPPORTUNITY). Vade sonunda AI destekli karar retrospektifi (Post-Mortem).
- 📉 **Reel Değerleme & Benchmark Engine:** TÜİK TÜFE, US CPI, Gram Altın ve S&P 500 ile enflasyondan arındırılmış reel getiri ve alpha analizi.
- 🔀 **Gölge Portföy (Counterfactual Engine):** Alınmayan (BOUGHT_INSTEAD) veya erken satılan (HELD_INSTEAD) kararların alternatif senaryolarla fırsat maliyeti takibi.
- 🎲 **Monte Carlo & Makro Stres Testi Motoru:** Varlık korelasyonlu geometrik Brownian hareketi (GBM), makro şok senaryoları (faiz, kur şoku, piyasa çöküşü) ve LLM destekli durum analizi.

---

## 🛠 Mimari ve Teknoloji Yığını

Projenin hedef mimarisi üç ana katmandan oluşur:
- **Veritabanı & Kimlik Doğrulama:** [PocketBase v0.40.6](https://pocketbase.io/) (SQLite tabanlı, yerleşik auth, rule-based erişim denetimi ve migration desteği)
- **Hesaplama Motoru & REST API:** Python 3.11+, FastAPI, Pydantic v2, Uvicorn
- **Finansal Analiz & Simülasyon:** NumPy, Pandas, SciPy
- **AI & Doğal Dil Yorumlama:** OpenRouter API (Fallback zinciri: Claude, GPT, Gemini vb.)
- **Piyasa Verisi:** yfinance, ccxt, TCMB EVDS API, FRED API
- **Web Arayüzü:** HTML5, TailwindCSS, Chart.js, Vanilla JS (DOM-safe, CSP uyumlu)

---

## 🚀 Hızlı Başlangıç

### Gereksinimler

- Python 3.11 veya üzeri
- PocketBase v0.40.6
- Git

### Yerel Kurulum (Manuel)

1. **Depoyu klonlayın:**
   ```bash
   git clone https://github.com/ertugerata/futureWallet_new.git
   cd futureWallet_new
   ```

2. **PocketBase'i kurun ve başlatın:**
   PocketBase v0.40.6 binary'sini indirin ve ayrı bir terminalde çalıştırın:
   ```bash
   curl -sL -o pb.zip https://github.com/pocketbase/pocketbase/releases/download/v0.40.6/pocketbase_0.40.6_linux_amd64.zip && unzip pb.zip
   ./pocketbase --dir ./pb_data superuser upsert admin@example.com 'GucluParola123!'
   ./pocketbase serve --dir ./pb_data --http 127.0.0.1:8090
   ```

3. **Python sanal ortamı kurun ve bağımlılıkları yükleyin:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Çevre değişkenlerini ayarlayın:**
   ```bash
   cp .env.example .env
   # .env dosyasını açıp POCKETBASE_URL, POCKETBASE_EMAIL, POCKETBASE_PASSWORD ve API_TOKEN girin
   ```

5. **Uygulamayı başlatın:**
   ```bash
   uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload
   ```

6. **Erişim:**
   - Web Arayüzü: [http://127.0.0.1:8000/web/](http://127.0.0.1:8000/web/)
   - API Dokümantasyonu (Swagger): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   - Sistem Sağlık Kontrolü: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## 🔐 Yapılandırma (Environment Variables)

Hassas anahtarlar ve ortam değişkenleri `.env` dosyası üzerinden yapılandırılır:

| Değişken | Açıklama | Varsayılan | Zorunlu mu? |
|---|---|---|---|
| `POCKETBASE_URL` | PocketBase sunucu URL'si | `http://127.0.0.1:8090` | Evet |
| `POCKETBASE_EMAIL` | PocketBase yönetici/sistem e-postası | - | Evet (migration/admin işleri için) |
| `POCKETBASE_PASSWORD` | PocketBase yönetici parolası | - | Evet |
| `API_TOKEN` | FastAPI servis token'ı / fallback auth | - | Evet (fail-closed) |
| `ALLOWED_ORIGINS` | CORS izinli origin listesi (virgüllü) | `""` (yalnızca same-origin) | Hayır |
| `ALLOWED_HOSTS` | İzinli HTTP Host başlıkları | `localhost,127.0.0.1` | Hayır |
| `OPENROUTER_API_KEY` | OpenRouter API anahtarı | `""` | AI özellikleri için |
| `OPENROUTER_MODELS` | Model fallback zinciri (virgüllü) | `openai/gpt-4o-mini,...` | Hayır |
| `TCMB_API_KEY` | TCMB EVDS API anahtarı | `""` | TÜFE benchmark için |
| `FRED_API_KEY` | FRED API anahtarı | `""` | US CPI benchmark için |
| `DEBUG` | Geliştirici modu (`true`/`false`) | `false` | Hayır |

> **Fail-Closed Güvenlik Notu:** `DEBUG=false` iken gerekli token ve PocketBase yapılandırmaları eksikse FastAPI uygulaması başlamayı reddeder.

---

## 🐳 Docker Compose ile Çalıştırma

En kolay ve izole kurulum yolu Docker Compose kullanmaktır.

```bash
# 1. Ortam dosyasını oluşturun
cp .env.example .env

# 2. .env içinde şifre ve anahtarları düzenleyin
# 3. Servisleri derleyin ve ayağa kaldırın
docker compose up -d --build
```

### Konteyner Mimarisi
- `pocketbase`: PocketBase v0.40.6 servisi (`127.0.0.1:8080:8090`). Veritabanı verisi `./pb_data` içinde kalıcı saklanır.
- `futurewallet`: FastAPI hesaplama servisi (`127.0.0.1:8000:8000`). PocketBase ile iç Docker ağı üzerinden konuşur.

Günlükleri takip etmek için:
```bash
docker compose logs -f futurewallet
```

Kapatmak için:
```bash
docker compose down
```

---

## 🧪 Test ve Kalite Kontrolleri

Proje kurallarına göre (`FUTUREWALLET_DUZELTME_PROMPTLARI.md` Prompt 0):
- Kod değişiklikleri **gerçek PocketBase v0.40.6** instance'ına karşı doğrulanmalıdır.
- MagicMock veya sahte in-memory SQLite veritabanı PocketBase entegrasyonu için kanıt sayılmaz.

```bash
# Statik kod analizi ve lint
ruff check .

# Tip denetimi
mypy api services config.py

# Testleri çalıştırma
pytest -q
```

---

## ⚠️ Yasal Uyarı

> **Bu platform ve yazılım yatırım tavsiyesi niteliğinde değildir.**

FutureWallet, yalnızca bireysel yatırımcıların kendi karar süreçlerini ve portföy hareketlerini takip etmelerini kolaylaştırmak amacıyla tasarlanmış bir **karar destek** aracıdır.

Sistem tarafından sunulan:
- Portföy snapshot'ları ve getiri hesaplamaları,
- Enflasyondan arındırılmış reel değerlemeler,
- Monte Carlo olasılık dağılımları ve stres testi simülasyonları,
- AI destekli karar retrospektifleri ve piyasa risk anlatıları

geçmiş verilere ve varsayımsal matematiksel modellere dayanır. Gelecekteki getirileri garanti etmez. Yatırım kararlarınızı vermeden önce lisanslı finansal danışmanlardan profesyonel destek alınız.
