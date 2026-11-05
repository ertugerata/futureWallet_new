# Sprint Planı - KALAN DEĞİŞİKLİKLER

## 📊 Mevcut Durum Özeti

### Zaten Tamamlananlar (Sprint 4 + önceki işler)
- [x] requirements.txt sürümlerini sabitle + pip-audit geç
- [x] GitHub Actions CI (ruff, mypy, pytest, pip-audit, docker build)
- [x] README.md güncellendi (config, auth/token, CORS vb.)
- [x] Yatırım tavsiyesi değildir disclaimer (arayüz + AI çıktıları)
- [x] `/api/portfolio/benchmarks` endpoint'i
- [x] `/api/simulation/stress-test` ve `/api/simulation/narrative` endpoint'leri
- [x] `/api/counterfactual/shadow-positions` (POST/GET) ve `/api/counterfactual/what-if`
- [x] `/api/decisions/stats` ve `DELETE /api/decisions/{id}`
- [x] `delete_decision` fonksiyonu decision_service.py'ye eklendi

### PocketBase Backend Durumu
| Servis | PB Kullanımı | Durum |
|--------|--------------|-------|
| `pocketbase.py` | PB Async Client, collection şemaları | ✅ Hazır |
| `ledger_service.py` | PB `transactions` collection | ✅ Geçiş yaptı |
| `decision_service.py` | PB `decisions` collection | ✅ Geçiş yaptı |
| `benchmark_service.py` | PB `macro_data` collection | ✅ Geçiş yaptı |
| `counterfactual_service.py` | PB `shadow_portfolios` collection | ✅ Bağlantı var, endpoint'ler eklendi |

---

## 🔴 KRITIK - Hemen Yapılmalı

### Prompt 1 - Kimlik Doğrulama (Hâlâ sorunlu)
- [ ] **Rate limiter testleri düzelt**: `test_retrospective_under_rate_limit[2-5]` → 429 hatası
  - `_RETRO_RATE_LIMITS` global dict state accumulation sorunu
  - Test fixture isolasyonu düzeltilmeli

### Prompt 2 - XSS (Hâlâ sorunlu)
- [ ] **test_rationale_exactly_5000_accepted** → ValueError: httpx Headers parser hatası
  - Test client içinde header dict formatı sorunu

---

## 🟠 YAPILMALI - Yüksek Önceliğin

### Prompt 6 - DB/Docker kalıcılığı
- [ ] `db.py` ve Alembic bağımlılığını kaldır
- [ ] `DATABASE_URL` referanslarını temizle (config.py'de hala var)
- [ ] `git rm --cached futurewallet.db` (repodaki .db dosyası)

### Prompt 8 - Transaction API & Ledger
- [ ] Stok yetersizliğinde **409 Conflict** hatası (SELL miktarı > eldeki miktar)
- [ ] Snapshot'a **average cost** ve **K/Z** alanları eklenecek

### Prompt 9 - Gerçek tarihsel fiyatla Time-Travel
- [ ] `services/price_service.py` YENİ dosya: `get_price_on(symbol, asset_type, on_date)` fonksiyonu
- [ ] Ledger'den geçmiş fiyatlar çekmek için price_history cache mekanizması
- [ ] `get_portfolio_snapshot(price_fn=...)` parametresi kullanılabilir konuma getir
- [ ] Time-Travel düzeltilmeli: T_start snapshot'ı T_target fiyatlarıyla değerlenmeli
- [ ] GET `/api/portfolio/value-series?start=&end=&step=weekly` endpoint'i

---

## 🟡 YAPILMAYİ (Opsiyonel / Orta Önceliğin)

### Prompt 10 - Monte Carlo API iyileştirmeleri
- [ ] Monte Carlo API'ya `histogram` alanı (40 kutu) - zaten simulation_service'de var
- [ ] p5/p50/p95 değerleri zaten döndürülüyor

### Prompt 13 - Karar Günlüğü İyileştirmeleri
- [ ] Karar tablosuna **"İşlemler" sütunu**: Retrospektif + Kapat butonları
- [ ] Karar paneline **sentiment bazlı özet kartı** (stats endpoint'inden)
- [ ] `decision_date` (geçmiş tarihli karar) desteklenmeli

### Prompt 12 - Counterfactual iyileştirmeleri
- [ ] Karar anında **otomatik HELD_INSTEAD/BOUGHT_INSTEAD** gölge oluşturma
- [ ] `create_decision` endpoint'ine `track_shadow` parametresi

### Prompt 14 - Web Arayüzü
- [ ] **USD/TRY görünüm seçici** tüm grafik ve tablolara entegre
- [ ] Stres testi paneline **histogram ve p5/p50/p95 dikey çizgileri**
- [ ] Mikrofon görünüm CSS düzeltmeleri

---

## 📝 Otomatik EXPIRED Akışı (Prompt 13)

Var로가 `auto_close_expired_decisions` fonksiyonu decision_service.py'dе:
```python
def auto_close_expired_decisions(days_before: int = 0) -> list[dict]:
    """Hedef tarihleri dolmuş ama REVIEWED yapılmamış kararları EXPIRED yapar."""
```

**Eksik**: Zamanlayıcı (APScheduler veya `schedule` + thread) lifespan'a eklenmeli.

---

## 🗺️ Önerilen Sprint Planı

### Sprint 5 - Altyapı & Ledger Tamamlama (1 Hafta)

**Güvenlik & Test Düzeltmeleri:**
1. Rate limiter test fix'i
2. test_rationale_exactly_5000_accepted fix'i

**DB/Migration:**
3. db.py ve Alembic bağımlılığını kaldırma
4. DATABASE_URL referanslarını temizleme
5. .db dosyasını repo'dan kaldırma

**Ledger İyileştirmeleri:**
6. Stok yetersizliğinde 409 hatası
7. Snapshot average cost ve K/Z alanları

### Sprint 6 - Fiyat Servisi & Time-Travel (1 Hafta)

**Yeni Servis:**
8. `services/price_service.py` oluşturma (get_price_on fonksiyonu)
9. Price history cache mekanizması

**Ledger Güncellemeleri:**
10. get_portfolio_snapshot(price_fn=...) parametresi
11. Time-Travel düzeltilmesi (gerçek tarihsel fiyatlarla)

**Yeni Endpoint:**
12. GET `/api/portfolio/value-series` endpoint'i

### Sprint 7 - Web UI Tamamlama (1 Hafta)

**Dashboard:**
13. USD/TRY görünüm seçici
14. Stres testi histogram + p5/p50/p95 çizgileri

**Karar Paneli:**
15. İşlemler sütunu (Retrospektif + Kapat butonları)
16. Sentiment özet kartı

**Counterfactual:**
17. Otomatik gölge oluşturma (track_shadow parametresi)

### Sprint 8 - Production Hazırlık (1 Hafta)

**Zamanlayıcılar:**
18. APScheduler ile günlük job'lar (benchmark güncelleme, auto_close_expired_decisions)

**Code Quality:**
19. `_guess_asset_type` ve `decision_to_dict` kod tekrarlarını temizleme
20. Ölü kodları temizleme (future_price.py, vb.)

**Test Coverage:**
21. Tüm yeni endpoint'ler için pytest testleri

---

## ⚠️ Önemli Notlar

1. **counterfactual_service.py PB geçişi**: Halukyla PB `get_client()` kullanıyor ama tam olarak "geçiş yapılmadı" olarak işaretlenmiş. Endpoint'ler eklendi, service PB kullanıyor → bu kısım yarıwegelijk.

2. **delete_decision**: Hala decision_service.py'ye eklenmemiş → yukarıda eklendi, endpoint çalışıyor.

3. **Otomatik gölge oluşturma**: `track_shadow` parametresi henüz yok → Sprint 7'de eklenecek.

4. **Zamanlayıcı**: Hiçbir zamanlayıcı (APScheduler/schedule) lifespan'a eklenmemiş → Sprint 8'de eklenecek.
