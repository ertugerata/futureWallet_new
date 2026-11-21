# FutureWallet – TODO & Sprint Takip Listesi (v6 – 2026-11-21 doğrulanmış durum)

> **Kaynak & Dayanak:** Durum tespiti Graphify bilgi grafiği (`graphify-out/`) ve gerçek PocketBase (v0.40.6) test koşusu ile yapıldı. Kapanan v3 denetiminin ham prompt dosyaları (`FUTUREWALLET_DUZELTME_PROMPTLARI.md`, `SPRINT_PLANI_KALANLAR.md`, `GUNCEL_IS_PLANI.md`) 2026-11-17'de arşivden kaldırıldı — geçmişleri git log'da. v4 sertleştirme çalışması (`feat/v4-critical-hardening` dalı) 2026-11-21'de tamamlandı.
> **Temel İlke (Prompt 0):** Yalnızca gerçek PocketBase entegrasyon testinden geçen maddeler `[x]` yapılabilir.
> **Doğrulama kanıtı:** `pytest tests` → **113/113 geçti** (tek oturum, gerçek PB sunucusu ile; v4 hardening testleri dahil); `ruff check .` ve `ruff format --check .` temiz; `mypy api services config.py web_app` (gevşek mod) hatasız; `python -c "import api.app"` başarılı. Sertleştirme regresyon testleri (`tests/test_hardening.py`) 10/10 yeşil.

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

### P5 – Value-Series DoS (ORTA) – Kısmen
- [x] Nokta sayısı **döngüden ÖNCE** aritmetikle hesaplanır (daily/weekly/monthly); >400 → 422.
- [x] Aralık sınırları: `start_date >= 1900`, max 20 yıl, `step` Literal doğrulaması.
- [x] OverflowError önlendi (yıl 9999 hatası).
- [ ] N+1 kaldırma (toplu snapshot + fiyat cache) — ORTA, ertelendi.
- [ ] Value-series hız sınırı (dk 10) — ORTA, ertelendi.

### P6 – CSP / Health / Ölü Kod (ORTA) – Kısmen
- [x] CSP hardened (jsdelivr yok, Chart.js yerel, frame-ancestors/deny, HSTS, Permissions-Policy).
- [x] `/health` gerçek PB check.
- [x] `_init_pocketbase` subprocess migrate kısmı silindi (sadece `verify_collections`).
- [ ] `_user_locks` LRU/WeakValueDictionary — ORTA, ertelendi (mevcut defaultdict testlerde büyümez).
- [ ] Enum tekilleştirme (`services/enums.py` → Literal) — ORTA, ertelendi.
- [ ] EVDS anahtar başlık/parametre doğrulama — ORTA, ertelendi.

### P7 – MVP Kapsam / Doküman Senkron (ORTA)
- [x] `MVP.md`: OpenRouter modelleri "örnek / env ile ayarlanır" olarak güncellendi; PB write rules null notu eklendi.
- [x] `README.md`: Ters proxy + TLS notu; tek worker / `SCHEDULER_LEADER` notu; secret risk notu.
- [x] `TODO.md` v6: test sayıları 113, v4 hardening özeti eklendi.
- [ ] ENAG / Ev-Kira / VaR-CVaR kararları — ORTA, Faz 2'ye ertelendi.

---

## 📋 Hızlı Kontrol Listesi

```text
[x] 1. python -c "import api.app" hatasız.
[x] 2. ruff check . + ruff format --check . sıfır hata.
[x] 3. Boş PB + migration → 7 koleksiyon; izolasyon testleri geçiyor.
[x] 4. İki farklı kullanıcı birbirinin verisini okuyamıyor (404).
[x] 5. Repoda changeme / admin@example.com / API_TOKEN yok.
[x] 6. Snapshot 2 işlem sonrası dolu; cash_received DIVIDEND'i sayıyor.
[x] 7. Fazla SELL → 409 Conflict.
[x] 8. Time-travel 5 BTC 30k→60k %100 PnL senaryo testi geçiyor.
[x] 9. OpenRouter fallback 502/503 semantiği + hız sınırı + hata sızıntısı kapalı testli.
[x] 10. market_crash %50 kalıcı şok testi geçiyor.
[x] 11. EXPIRED job + refresh_macro job PB üzerinde uçtan uca testli (ilk çalışma <30sn).
[x] 12. Web UI login → dashboard akışı CSP/konsol hatası olmadan tarayıcıda doğrulandı.
[x] 13. P1–P14 + v4 hardening testleri geçiyor (113/113 + 10/10 hardening).
[x] 14. Docker compose build → user!=root, .dockerignore pb_data/pb_bin/tests/docs, CSP hardened, /health real PB check.
```

---

## 🔜 Kalan / Ertelenen (ORTA / Faz 2)

1. **P5 N+1 & hız sınırı**: `get_portfolio_snapshots` toplu fonksiyon + fiyat cache; value-series rate limit (dk 10).
2. **P6 `_user_locks`**: LRU/WeakValueDictionary ile sınırlı boyut.
3. **P6 Enum tekilleştirme**: `services/enums.py` → `Literal[*]` / Pydantic Enum.
4. **P6 EVDS anahtar**: Resmî dokümana göre header/parametre doğrulama.
5. **P7 Kapsam kararları**: ENAG (Faz 2), Ev-Kira (EVDS housing index / Faz 2), VaR/CVaR (Monte Carlo kuyruk ort. / Faz 2).
6. **P8 Otomatik retrospektif**: `AUTO_RETROSPECTIVE` flag + scheduler adımı (Faz 2).