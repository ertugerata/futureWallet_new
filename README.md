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
   git clone https://github.com/ertugerata/futurewallet.git
   cd futurewallet
   ```

2. **Sanal ortamı aktif edin:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # venv\Scripts\activate  # Windows
   ```

3. **Bağımlılıkları kurun:**
   ```bash
   pip install -r requirements.txt
   ```

4. **.env dosyasının yapılandırılması (opsiyonel):**
   ```bash
   cp .env.example .env
   # .env dosyasını düzenleyerek API key'lerini girin
   ```

5. **Uygulamayı başlatın:**
   ```bash
   uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
   ```

6. **Tarayıcınızdan erişin:** [http://localhost:8000/web/](http://localhost:8000/web/)

---

## 🐳 Docker ile Çalıştırma

Uygulama, Docker ile de kolayca çalıştırılabilir. Aşağıdaki adımları takip edin.

### Docker Kurulumu

Sistemde Docker ve Docker Compose yüklü olmalıdır:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (macOS, Windows)
- [Docker Engine](https://docs.docker.com/engine/install/) (Linux)

Linux kullanıcıları için Docker kurulumu:

```bash
sudo apt update
sudo apt install docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Oturumu yenileyin veya yeniden giriş yapın
```

### Docker Image Oluşturma

Depo dizininde (bu dosyanın bulunduğu yerde) aşağıdaki komutu çalıştırın:

```bash
# FutureWallet Docker image'ı oluştur
docker build -t futurewallet .
```

Bu komut iki aşamalı Dockerfile kullanarak:

1. **Builder aşaması:** Python 3.11-slim üzerinde bağımlılıkları kurar
2. **Runtime aşaması:** Sadece gerekli dosyaları ve bağımlılıkları içeren optimize edilmiş bir image oluşturur

Başarılı bir build sonucunda `futurewallet:latest` imajı oluşur.

### Docker ile Çalıştırma

Uygulamayı başlatmak için aşağıdaki komutu çalıştırın:

```bash
docker run -p 8000:8000 futurewallet
```

Burada:

- `-p 8000:8000` → Container içindeki port 8000, makinenizin port 8000'a eşlenir
- `futurewallet` → Oluşturulan image'in adı

Opsiyonel olarak, environment variable'ları ile yapılandırma:

```bash
docker run -p 8000:8000 \
  -e GOOGLE_API_KEY="your-key" \
  -e DEBUG="true" \
  -e TCMB_API_KEY="your-tcmb-key" \
  -e FRED_API_KEY="your-fred-key" \
  futurewallet
```

Veya özelleştirilmiş bir `.env` dosyası ile:

```bash
# Kendi .env dosyanızı oluşturun
cp .env.example .env
# .env dosyasını düzenleyerek API key'lerini girin

# Docker'a mount ederek çalıştırın
docker run -p 8000:8000 -v $(pwd)/.env:/app/.env futurewallet
```

### Docker Compose ile Çalıştırma (Önerilen)

Eğer Docker Compose kullanıyorsanız, `docker-compose.yml` dosyası oluşturun:

```yaml
version: '3.8'

services:
  futurewallet:
    build: .
    ports:
      - "8000:8000"
    environment:
      - GOOGLE_API_KEY=${GOOGLE_API_KEY:-}
      - DEBUG=${DEBUG:-false}
      - TCMB_API_KEY=${TCMB_API_KEY:-}
      - FRED_API_KEY=${FRED_API_KEY:-}
    volumes:
      - ./data:/app/data  # Veritabanı dosyasını kalıcı olarak saklamak için
    restart: unless-stopped
```

Daha sonra:

```bash
# İlk kez kurulum ve başlatma
docker-compose up -d

# Güncellemeden ardından yeniden başlatma  
docker-compose up -d --build

# Çalışan container'ı durdurma
docker-compose down
```

Çalışan container'ı izlemek için: `docker-compose logs -f`

### Çevrimiçi Erişim

İşlemin başarılı olduğunu doğrulamak için:

- Tarayıcınızdan: [http://localhost:8000/web/](http://localhost:8000/web/)
- API health check: [http://localhost:8000/health](http://localhost:8000/health)
- API dokümantasyonu: [http://localhost:8000/docs](http://localhost:8000/docs) (FastAPI otomatik Swagger UI)

### Veritabanı Yönetimi

Docker ile çalıştırırken SQLite veritabanı (`futurewallet.db`) container içine kalıcı olmayan bir şekilde kaydedilir. Veritabanınızı kalıcı hale getirmek için volume mount kullanın:

```bash
docker run -p 8000:8000 -v $(pwd)/data:/app/data futurewallet
```

Bu durumda, `data/` dizini içinde `futurewallet.db` dosyası oluşur ve container kaldırıldığında bile korunur.

---

## 🌐 Başvuru

- API referansı ve interaktif test için: [http://localhost:8000/docs](http://localhost:8000/docs)
- Web dashboard: [http://localhost:8000/web/](http://localhost:8000/web/)
- Sağlık kontrolü: [http://localhost:8000/health](http://localhost:8000/health)

---

## 📄 Lisans

MIT - detaylar için [LICENSE.md](LICENSE.md)

---

## 🤝 Katkıda Bulunmak

- Fork edin ve özellik/Eklemek istediğiniz konuları `main` branch'ine PR gönderin
- Sorun bildirimi için GitHub Issues sayfasını kullanın
- Daha fazla bilgi için [MVP.md](MVP.md) dosyasını inceleyin

---

**FutureWallet** - Yatırımcıların kararlarını geleceğe taşıyabilmesi için tasarlanmış bir platform. 🚀
