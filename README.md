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
- 🎲 **Monte Carlo & Makro Stres Testi Motoru:** Varlık korelasyonlu geometrik Brownian hareketi (GBM), makro şok senaryoları (faiz, kur şoku, piyasa çöküşü) ve LLM destekli durum analizi. `currency` çıktısı varlık tabanına göre dinamik (BIST/TL → TRY, kripto/ABD/emtia → USD; karışık sepette çoğunluk).

---

## 🛠 Mimari ve Teknoloji Yığını

Projenin hedef mimarisi üç ana katmandan oluşur:
- **Veritabanı & Kimlik Doğrulama:** [PocketBase v0.40.6](https://pocketbase.io/) (SQLite tabanlı, yerleşik auth, rule-based erişim denetimi ve migration desteği)
- **Hesaplama Motoru & REST API:** Python 3.11+, FastAPI, Pydantic v2, Uvicorn
- **Finansal Analiz & Simülasyon:** NumPy, Pandas
- **Zamanlama:** APScheduler (lifespan içinde; `ENABLE_SCHEDULER=false` ile kapatılabilir) — job'lar: vadesi geçmiş OPEN kararları EXPIRED yapma + outcome doldurma (`auto_close_expired_decisions`, uçtan uca PB testli) ve 24s makro veri yenileme (`refresh_macro`)
- **AI & Doğal Dil Yorumlama:** OpenRouter API (Fallback zinciri: Claude, Gemini, DeepSeek)
- **Piyasa Verisi:** yfinance, ccxt, TCMB EVDS API, FRED API
- **Web Arayüzü:** HTML5, Jinja2, Chart.js, Vanilla JS — PB JWT giriş akışı, CSP temizliği ve `innerHTML`-siz DOM render (P14) canlı tarayıcı E2E ile doğrulandı; USD/TRY para birimi seçicisi API `currency` alanına dinamik bağlı (P9 kapandı)

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
   PocketBase v0.40.6 binary'sini indirin ve ayrı bir terminalde, **repo kökünde** çalıştırın (`./pocketbase` yerine `./pb_bin/pocketbase` de olur; test fixture'ı binary'yi oraya da önbellekler):
   ```bash
   curl -sL -o pb.zip https://github.com/pocketbase/pocketbase/releases/download/v0.40.6/pocketbase_0.40.6_linux_amd64.zip && unzip pb.zip
   ./pocketbase --dir ./pb_data superuser upsert 'superuser@sirket.local' 'GucluParola123!'
   ./pocketbase serve --dir ./pb_data --http 127.0.0.1:8080
   ```

   Port `8080`, `POCKETBASE_URL` varsayımıyla (`http://localhost:8080`) birebir eşleşir. Repo kökünde koşulduğunda `pb_migrations/` otomatik uygulanır; sonucunda 6 koleksiyon (`users`, `transactions`, `decisions`, `shadow_portfolios`, `macro_data`, `price_history`) oluşur — API bunu açılışta ayrıca doğrular (`/health` → `pb: ok|down`).

3. **Python sanal ortamı kurun ve bağımlılıkları yükleyin** (repo kuralı: `uv` — `bin/uv` gitignore'dadır; yoksa kurun):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh   # uv yoksa
   uv venv
   uv pip install -r requirements.txt
   ```

4. **Çevre değişkenlerini ayarlayın:**
   ```bash
   cp .env.example .env
   # POCKETBASE_EMAIL + POCKETBASE_PASSWORD zorunlu (.env.example'da boş bırakılır);
   # POCKETBASE_URL yalnız farklı port/host için; AI için OPENROUTER_API_KEY opsiyonel
   ```

5. **Uygulamayı başlatın:**
   ```bash
   uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload
   ```

6. **Erişim:**
   - Web Arayüzü: [http://127.0.0.1:8000/web/](http://127.0.0.1:8000/web/)
   - API Dokümantasyonu (Swagger): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) — yalnızca `DEBUG=true` iken açıktır
   - Sistem Sağlık Kontrolü: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) (`pb: ok|down` alanıyla)

---

## 🔐 Yapılandırma (Environment Variables)

Hassas anahtarlar ve ortam değişkenleri `.env` dosyası üzerinden yapılandırılır:

| Değişken | Açıklama | Varsayılan | Zorunlu mu? |
|---|---|---|---|
| `POCKETBASE_URL` | PocketBase sunucu URL'si | `http://localhost:8080` | Hayır (compose bunu ağ içi değere sabitler) |
| `POCKETBASE_EMAIL` | PocketBase superuser e-postası | - | Evet (eksikse `config.py` RuntimeError) |
| `POCKETBASE_PASSWORD` | PocketBase superuser parolası | - | Evet (eksikse `config.py` RuntimeError) |
| `ALLOWED_ORIGINS` | CORS izinli origin listesi (virgüllü) | `""` (yalnızca same-origin) | Hayır |
| `ALLOWED_HOSTS` | İzinli HTTP Host başlıkları | `localhost,127.0.0.1` | Hayır |
| `OPENROUTER_API_KEY` | OpenRouter API anahtarı | `""` | AI özellikleri için (yoksa AI uçları 503) |
| `OPENROUTER_BASE_URL` | OpenRouter temel adresi | `https://openrouter.ai/api/v1` | Hayır |
| `OPENROUTER_MODELS` | Model fallback zinciri (virgüllü) | `anthropic/claude-3.5-sonnet,google/gemini-2.0-flash-001,deepseek/deepseek-r1` | Hayır |
| `ENABLE_SCHEDULER` | APScheduler açık/kapalı | `true` | Hayır |
| `TCMB_API_KEY` | TCMB EVDS API anahtarı | `""` | TÜFE benchmark için |
| `FRED_API_KEY` | FRED API anahtarı | `""` | US CPI benchmark için |
| `DEBUG` | Geliştirici modu; `/docs` ve `/openapi.json` bunu açar | `false` | Hayır |
| `APP_HOST` / `APP_PORT` | Uvicorn bind hedefi (`uvicorn` CLI kullanılıyorsa CLI geçerli) | `127.0.0.1` / `8000` | Hayır |

> **Fail-Closed Güvenlik Notu:** `POCKETBASE_EMAIL`/`POCKETBASE_PASSWORD` boşsa uygulama import aşamasında RuntimeError ile başlar.

## 🔐 Kimlik Doğrulama

Statik API token **yoktur**. Tüm `/api/*` uçları PocketBase kullanıcı JWT'si ister:

```bash
# 1. Kullanıcı oluşturun (PB admin veya kayıt) ve token alın:
curl -X POST $POCKETBASE_URL/api/collections/users/auth-with-password \
  -H 'Content-Type: application/json' \
  -d '{"identity":"user@sirket.local","password":"Parola123!"}'

# 2. API çağrılarında taşıyın:
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/portfolio/snapshot
```

Sunucu token'ı `users/auth_refresh` ile doğrular (geçersiz/süresi dolmuş → 401); tüm veri erişimi PB erişim kuralları ve uygulama tarafı sahiplik kontrolleriyle kullanıcı bazında izole edilir (başkasının kaynağı → 404). PB record ID'leri uç girişinde `^[a-z0-9]{15}$` formatında doğrulanır — biçimsiz ID path/query/body'de servise inmeden 422 döner.

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
- `pocketbase`: PocketBase v0.40.6 servisi (`127.0.0.1:8080:8090`). Veritabanı verisi adlandırılmış Docker volume'ünde (`pb_data`) kalıcı saklanır; migration'lar imajla gelir.
- `futurewallet`: FastAPI hesaplama servisi (`127.0.0.1:8000:8000`). `POCKETBASE_URL=http://pocketbase:8090` compose içinde ağ-internal olarak verilir; host `.env`'inden yalnız credential/anahtarlar okunur (`${VAR:?required}` fail-closed).

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

Proje kurallarına göre (`TODO.md` Temel İlke, Prompt 0):
- Kod değişiklikleri **gerçek PocketBase v0.40.6** instance'ına karşı doğrulanmalıdır.
- MagicMock veya sahte in-memory SQLite veritabanı PocketBase entegrasyonu için kanıt sayılmaz.

```bash
# Statik kod analizi ve lint
ruff check .
ruff format --check .

# Tip denetimi (gevşek mod, mypy.ini)
mypy api services config.py web_app

# Testleri çalıştırma (PocketBase binary'si tests/conftest.py tarafından
# otomatik indirilir ve pb_bin/ içinde önbelleklenir) — mevcut durum: 101/101
pytest -q

# Yalnızca PocketBase entegrasyon testleri
pytest -m pb -q
```

CI (`.github/workflows/ci.yml`) bu adımların tamamını + ayrı `python -c "import api.app"` duman adımı, `pip-audit` ve docker build'i koşar.

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
