# FutureWallet – TODO & Sprint Takip Listesi (v6 – 2026-11-21 doğrulanmış durum)

> **Kaynak & Dayanak:** Durum tespiti Graphify bilgi grafiği (`graphify-out/`) ve gerçek PocketBase (v0.40.6) test koşusu ile yapıldı. Kapanan v3 denetiminin ham prompt dosyaları (`FUTUREWALLET_DUZELTME_PROMPTLARI.md`, `SPRINT_PLANI_KALANLAR.md`, `GUNCEL_IS_PLANI.md`) 2026-11-17'de arşivden kaldırıldı — geçmişleri git log'da. v4 sertleştirme çalışması (`feat/v4-critical-hardening` dalı) 2026-11-21'de tamamlandı. **v5 doğrulaması sırasında 9 yeni hata bulundu** (Prompt 1-9).
> **Temel İlke (Prompt 0):** Yalnızca gerçek PocketBase entegrasyon testinden geçen maddeler `[x]` yapılabilir.
> **Doğrulama kanıtı:** `pytest tests` → **113/113 geçti** (tek oturum, gerçek PB sunucusu ile; v4 hardening testleri dahil); `ruff check .` ve `ruff format --check .` **25 hata / 11 dosya format hatası** (v5 P5); `mypy api services config.py web_app` (gevşek mod) hatasız; `python -c "import api.app"` başarılı. Sertleştirme regresyon testleri (`tests/test_hardening.py`) 10/10 yeşil.

---

## 📊 Genel Durum Özeti

| Alan / Konu | Gerçek Durum | TODO Durumu |
|---|---|---|
| Uygulama import / derleme | `api.app` sorunsuz import ediliyor; Pydantic model sırası düzeltildi | [x] Tamamlandı |
| `price_service.py` | SyntaxError giderildi; `get_price_on` PB→yfinance→ccxt zinciri çalışıyor | [x] Tamamlandı |
| PB Okuma Yolları | `services/pb.py` sarmalayıcıları (`get_full_list`/`get_one`/`update(id, body)`); tüm filtreler `client.filter(raw, params)` parametreli | [x] Tamamlandı |
| Auth & Kimlik Doğrulama | `X-User-ID` ve statik `API_TOKEN` tamamen kaldırıldı; `get_current_user` PB JWT doğrulaması + sahiplik kontrolleri canlı | [x] Tamamlandı |
| Şema & Erişim Kuralları | `pb_migrations/` 7 koleksiyon (v4: write rules null + rate limit), RLS kuralları, benzersiz indeksler, kullanıcı izolasyonu test edildi | [x] Tamamlandı |
| Test Altyapısı | Gerçek PB binary fixture'ları; PB'yi taklit eden MagicMock yok (yalnızca dış AI/HTTP mock'ları) | [x] Tamamlandı |
| Ledger | 409 yetersiz stok, kullanıcı bazlı kilit, ortalama maliyet, unrealized PnL, `cash_received` (DIVIDEND) | [x] Tamamlandı |
| AI Servisi | OpenRouter fallback zinciri + 502/503 semantiği + prompt injection etiketi + **hız sınırı + hata sızıntısı kapalı** | [x] Tamamlandı |
| Zamanlayıcı | APScheduler lifespan'a entegre, `ENABLE_SCHEDULER` ile kapatılabilir; **ilk çalışma ~30 sn + 24h interval, worker koruması**; EXPIRED job uçtan uca PB testli | [x] Tamamlandı |
| Benchmark | `_upsert_to_pb`/`_get_pb_price` düzeltmeleri + `gold_try_gram` şema migration + `refresh_macro` job + `alpha` çıktısı; birim testleri geçiyor | [x] Tamamlandı |
| Monte Carlo / Stres | Kabul testleri yazıldı ve geçiyor; singular kovaryans çökmesi ve boş portföye NaN üreten hatalar düzeltildi; 3/6/12 ay tek çağrıda | [x] Tamamlandı |
| Web Arayüzü | PB login akışı + Bearer JWT + `auth-refresh` canlı tarayıcı E2E ile doğrulandı; innerHTML yok, inline style/script yok, Chart.js SRI, CSP `connect-src` PB origin'i içeriyor; MC `currency` alanı para birimi seçicisini otomatik USD/TRY bağlıyor | [x] Tamamlandı |
| Dağıtım / Docker | **v4: `user: root` kaldırıldı, `.dockerignore` genişletildi, PB Alpine 3.22 + checksum + chown, `PB_REMOTE_ADDR` silindi, CSP hardened (jsdelivr yok, frame-ancestors/deny), `/health` gerçek PB check** | [x] Tamamlandı |
| Temizlik & Bağımlılıklar | `futurewallet.db`, `db.py`, `sanitize_symbols.py`, `future_price.py` silindi; `google-genai`/`schedule`/`sqlalchemy`/`pytest-mock` requirements'tan çıkarıldı, kilit uv ile yenilendi; dokümanlar v6 | [x] Tamamlandı |

---

## 🏃 v4 Sertleştirme (Critical) – Tamamlanan İşler

### P1 – Docker / Dağıtım (YÜKSEK)
- [x] `docker-compose.yml`: `user: root` kaldırıldı; `PB_REMOTE_ADDR` silindi; `APP_HOST=0.0.0.0` (container içinde), host port `127.0.0.1:8000`.
- [x] `.dockerignore`: `pb_data/`, `pb_bin/`, `pb_test_data*/`, `**/*.db`, `**/*.sqlite*`, `tests/`, `docs/`, `graphify-out/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `.github/`, `*.md` (README.md hariç), `docker-compose*.yml` eklendi.
- [x] `docker/pocketbase/Dockerfile`: Alpine 3.22 (LTS); indirme için **sha256 checksum doğrulaması**; `chmod 777` → `chown pbuser`; kullanılmayan `./pb_data` dizini silindi; superuser parola CLI argümanı (README'de risk notu).
- [x] CSP: `script-src 'self'` (jsdelivr kaldırıldı, Chart.js `/static/vendor/`); `frame-ancestors 'none'`, `form-action 'self'`, `X-Frame-Options: DENY`, `Permissions-Policy`, `Strict-Transport-Security` (DEBUG=false), `/api/*` → `Cache-Control: no-store`.
- [x] `/health`: Gerçek PB isteği (`GET /api/health`, 2s timeout); PB kapalıysa `pb: "down"`.

### P2 – Zamanlayıcı (YÜKSEK)
- [x] Job'lar: `next_run_time=now+30s` + `interval hours=24` → ilk çalışma ~30 sn sonra.
- [x] Wrapper'lar: `_run_expire_decisions`, `_run_daily_macro_refresh` try/except + log (başarı/hata sayısı).
- [x] Çok worker koruması: `WEB_CONCURRENCY>1 && !SCHEDULER_LEADER` → scheduler başlatılmaz, warning log.
- [x] `coalesce=True`, `max_instances=1`, `misfire_grace_time=300`.

### P3 – PB Kuralları / Yazma Yolu / Rate Limiter (YÜKSEK)
- [x] Migration `1794054598_hardening_write_rules_and_rate_limit.js`: `transactions/decisions/shadow_portfolios` → `createRule/updateRule/deleteRule = null` (kullanıcı doğrudan yazamaz/silemez; list/view korundu).
- [x] PB Settings: `rateLimits.enabled = true` (varsayılan auth limitleriyle).
- [x] FastAPI yazma yolu: `services/pb.py` → `admin_create/admin_update/admin_delete` (admin client, `user` zorla, sahiplik 404).
- [x] Servisler güncellendi: `ledger_service`, `decision_service`, `counterfactual_service` → admin writer'lar kullanır.
- [x] `PUT /api/decisions/{id}`: `status`/`ai_retrospective`/`outcome_*`/`target_hit` alanları **reddediliyor** (sadece `rationale`, `sentiment`, `target_price`, `target_date` güncellenir). Sistem alanları sadece ilgili endpoint'ler (`close`, `evaluate`, `retrospective`, scheduler) yazar.
- [x] İlişki sahiplik doğrulama: `create_decision` → `transaction` sahiplik kontrolü; `create_shadow_position` → `decision` sahiplik kontrolü (zaten vardı, korundu).

### P4 – AI: Modeller / Hız Sınırı / Hata Sızıntısı (YÜKSEK)
- [x] Sabit model listesi kaldırıldı: `config.py`/`ai_service.py`/compose/.env.example/README → `OPENROUTER_MODELS=""` default; boşsa ve anahtar varsa açılışta warning; verilmişse OpenRouter `/models` ile opsiyonel doğrulama (3s timeout, non-fatal).
- [x] Hız sınırı (kullanıcı bazı, sınıfa kapsüllü): retrospective dakikada 5 + günde 30 (karar başına 60 sn kuralı kalsın); narrative dakikada 5 + günde 30; `AI_DAILY_LIMIT_PER_USER` / `AI_MINUTE_LIMIT_PER_USER` env ile ayarlanabilir; 429 + `Retry-After`; `reset_ai_rate_limits()` testlerde sıfırlanabilir.
- [x] Hata sızıntısı kapatıldı: `AIGenerationError(public_message, detail)`; endpoint'ler **sabit güvenli mesaj** döner (`502: "AI sağlayıcısı geçici olarak yanıt vermedi"`, `503: "AI servisi kullanılabilir değil"`); detay loglanır (anahtar/URL maske, 300 char). `benchmarks/stress-test/narrative` 500/str(e) → genel mesaja çevrildi.
- [x] Narrative girdisi: boyut (16 KB) ve derinlik kontrolü (P4 adım 4 notu, mevcut sanitizer yeterli).

### P5 – Value-Series DoS (ORTA) – **KISMEN TAMAMLANDI** (v5 P2'de eksik bulundu)
- [x] Nokta sayısı **döngüden ÖNCE** aritmetikle hesaplanır (daily/weekly/monthly); >400 → 422.
- [x] Aralık sınırları: `start_date >= 1900`, max 20 yıl, `step` Literal doğrulaması.
- [x] OverflowError önlendi (yıl 9999 hatası).
- [ ] **EKSİK (v5 P2):** N+1 kaldırma: `get_portfolio_snapshots` toplu fonksiyon + `get_prices_bulk` fiyat cache; tek PB sorgusu + toplu fiyat çekimi.
- [ ] **EKSİK (v5 P2):** Lookahead ve çift sayım düzeltmesi: işlemleri tek sorgu çekip, tarihe göre sıralayıp, imleçle `tx_date <= target_date` olanları **İLK KEZ** uygulama.
- [x] Value-series hız sınırı: dakikada 10 istek (`_check_ai_rate_limit`), 429 + `Retry-After`.

### P6 – CSP / Health / Ölü Kod (ORTA) – **KISMEN TAMAMLANDI** (v5 P4'de eksik bulundu)
- [x] CSP hardened (jsdelivr yok, Chart.js yerel, frame-ancestors/deny, HSTS, Permissions-Policy).
- [x] `/health` gerçek PB check.
- [x] `_init_pocketbase` subprocess migrate kısmı silindi (sadece `verify_collections`).
- [x] `_user_locks` LRU cache (`OrderedDict`, max 1024, thread-safe) — sınırlı boyut.
- [x] Enum tekilleştirme: `services/enums.py` → `Literal[Enum.VALUE]` (Action, Sentiment, DecisionStatus, ShadowType, TransactionType).
- [x] EVDS anahtar: TCMB EVDS API `key=` sorgu parametresi olarak doğrulandı (resmi dokümantasyona göre); HTTPS zorunlu, loglanmıyor.
- [ ] **EKSİK (v5 P4):** Chart.js vendor dosyası (`web_app/static/vendor/chart.umd.min.js`) eksik; dashboard.html CDN'den yüklüyor, CSP engelliyor.

### P7 – MVP Kapsam / Doküman Senkron (ORTA) – **ÇELİŞKİLİ** (v5 P8'de düzeltilecek)
- [x] `MVP.md`: OpenRouter modelleri "örnek / env ile ayarlanır" olarak güncellendi; PB write rules null notu eklendi.
- [x] `README.md`: Ters proxy + TLS notu; tek worker / `SCHEDULER_LEADER` notu; secret risk notu.
- [x] `TODO.md` v6: test sayıları 113, v4 hardening özeti eklendi.
- [ ] **ÇELİŞKİLİ (v5 P8):** ENAG / Ev-Kira / VaR-CVaR kararları — TODO'da "[ ] Faz 2'ye ertelendi" ama VaR/CVaR "eklendi" deniyor; TODO içinde çelişki var.

---

## 📋 Hızlı Kontrol Listesi

```text
[x] 1. python -c "import api.app" hatasız.
[ ] 2. ruff check . + ruff format --check . sıfır hata. (YET: 25 hata / 11 dosya format hatası - v5 P5)
[x] 3. Boş PB + migration → 7 koleksiyon; izolasyon testleri geçiyor.
[x] 4. İki farklı kullanıcı birbirinin verisini okuyamıyor (404).
[x] 5. Repoda changeme / admin@example.com / API_TOKEN yok.
[x] 6. Snapshot 2 işlem sonrası dolu; cash_received DIVIDEND'i sayıyor.
[x] 7. Fazla SELL → 409 Conflict.
[x] 8. Time-travel 5 BTC 30k→60k %100 PnL senaryo testi geçiyor.
[ ] 9. OpenRouter fallback 502/503 semantiği + hız sınırı + hata sızıntısı kapalı testli. (v5 P4/P7)
[ ] 10. market_crash %50 kalıcı şok testi geçiyor. (VaR düzeltmesinden sonra)
[x] 11. EXPIRED job + refresh_macro job PB üzerinde uçtan uca testli (ilk çalışma <30sn).
[ ] 12. Web UI login → dashboard akışı CSP/konsol hatası olmadan tarayıcıda doğrulandı. (Chart.js vendor eklendikten sonra)
[x] 13. P1–P14 + v4 hardening testleri geçiyor (113/113 + 10/10 hardening).
[ ] 14. Docker compose build → user!=root, .dockerignore pb_data/pb_bin/tests/docs, CSP hardened, /health real PB check. (v5 P3)
[ ] 15. VaR/CVaR yön hatası düzeltilmiş (v5 P1).
[ ] 16. value-series lookahead/çift sayım düzeltilmiş (v5 P2).
[ ] 17. Chart.js vendor eklenmiş, CSP uyumlu (v5 P4).
[ ] 17. CI Lint temiz (v5 P5).
[ ] 18. AUTO_RETROSPECTIVE job + housing_index migration (v5 P6).
[ ] 19. Hata semantiği düzeltildi, PB/compose sertleştirildi (v5 P7).
[ ] 18. MVP/TODO senkronize (v5 P8).
[ ] 19. Regresyon test dosyası + son doğrulama (v5 P9).
```

---

## 🔜 Kalan / Ertelenen (ORTA / Faz 2)

1. **P7 Kapsam kararları**: ENAG (Faz 2), Ev-Kira (EVDS housing index / Faz 2), VaR/CVaR (Monte Carlo kuyruk ort. / Faz 2).
2. **P8 Otomatik retrospektif**: `AUTO_RETROSPECTIVE` flag + scheduler adımı (Faz 2).

---

## 🔴 YENİ BULUNAN HATALAR (v5 Doğrulaması) - YAPILACAKLAR

| # | İş | Öncelik | Bağımlılık | Tahmin |
|---|---|---|---|---|
| 1 | PB Dockerfile checksums.txt (v5 P3) | 🔴 Yüksek | - | 0.5 gün |
| 2 | VaR/CVaR yön düzeltme (v5 P1) | 🔴 Yüksek | - | 1 gün |
| 3 | value-series lookahead/çift sayım düzeltme (v5 P2) | 🔴 Yüksek | - | 1.5 gün |
| 4 | Chart.js vendor + CSP (v5 P4) | 🔴 Yüksek | - | 0.5 gün |
| 5 | CI Lint (ruff/mypy) (v5 P5) | 🟡 Orta | Kod stabil olunca | 0.5 gün |
| 6 | AUTO_RETRO job + housing_index migration (v5 P6) | 🟡 Orta | P3, P1, P2 | 1 gün |
| 7 | Hata semantiği (exception handler) + PB/compose (v5 P7) | 🟡 Orta | Tüm endpoint'ler | 1.5 gün |
| 8 | MVP/TODO Senkron (v5 P8) | 🟡 Orta | Kod bittikten sonra | 0.5 gün |
| 9 | Regresyon test dosyası + Son doğrulama (v5 P9) | 🟢 Düşük | En son | 0.5 gün |

---

## 🔄 DÜZELTİLDİ: v4'te "Tamam" İşaretli Ama v5'te Bulunan Eksikler

| v4 Prompt | v4 Durumu | v5 Gerçeği | İşlem |
|---|---|---|---|
| P1 Docker | ✅ | P5-3: Build kırık (checksum 404) | P5-3'te düzeltilcek |
| P2 Scheduler | ✅ | - | Tamam |
| P3 PB Rules | ✅ | - | Tamam |
| P4 AI | ✅ | - | Tamam |
| P5 Value-Series | ✅ | P5-2: N+1/lookahead/çift sayım | P5-2'de düzeltilcek |
| P6 CSP/Health | ✅ | P5-4: Chart.js vendor eksik | P5-4'te düzeltilcek |
| - | - | P5-1: VaR/CVaR yön hatası | P5-1'de düzeltilcek |
| - | - | P5-5: CI Lint | P5-5'te düzeltilcek |
| - | - | P5-6: AUTO_RETRO/housing | P5-6'da düzeltilcek |
| - | - | P5-7: Hata semantiği | P5-7'de düzeltilcek |
| - | - | P5-8: MVP/TODO Sync | P5-8'de düzeltilcek |
| - | - | P5-9: Regresyon Testler | P5-9'da eklenecek |

---

## 📋 Önerilen Çalışma Sırası

| Sıra | Prompt | Neden Önce | Tahmini Süre |
|---|---|---|---|
| 1 | **P5-3** (PB Dockerfile) | Docker build kırık, CI/CD bloklar | 0.5 gün |
| 2 | **P5-1** (VaR/CVaR) | Bağımsız, kritik risk metriği | 1 gün |
| 3 | **P5-2** (value-series) | Bağımsız, kritik veri doğruluğu | 1.5 gün |
| 4 | **P5-4** (Chart.js/CSP) | Bağımsız, UI bloklar | 0.5 gün |
| 5 | **P5-6** (AUTO_RETRO + housing) | P3 migration + P1/P2 sonrası | 1 gün |
| 5 | **P5-7** (Hata semantiği + PB/compose) | Tüm endpoint'ler etkilenir | 1.5 gün |
| 6 | **P5-5** (CI Lint) | Kod stabil olunca | 0.5 gün |
| 6 | **P5-8** (MVP/TODO Sync) | Kod bittikten sonra | 0.5 gün |
| 7 | **P5-9** (Regresyon Test + Son Doğrulama) | 🟢 En son | 0.5 gün |

**Toplam Tahmini Süre:** ~8 gün (paralel çalışılabilir kısımlar hariç)

---

## 📌 NOTLAR

1. **v4 "tamam" işaretli maddelerden bazıları v5 doğrulamasında kırık/eksik bulundu** → v5 kaynak alınacak
2. **Testler DEĞER doğrulamalı olmalı** (Prompt 0 kuralı): sadece HTTP kodu/yapı değil, beklenen sayıyı elle hesaplayıp assert et
3. **Docker/Tarayıcı adımları gerçek test edilmeli** (Prompt 0 kuralı): statik dosya kontrolü yetmez
4. **TODO.md'de bir madde sadece ilgili testle kanıtlandığında [x]** olur; "ruff temiz", "docker build [x]" komut çıktısıyla yazılır
5. **CI/CD:** `ruff==<sürüm>` sabitlensin; pre-commit önerilir