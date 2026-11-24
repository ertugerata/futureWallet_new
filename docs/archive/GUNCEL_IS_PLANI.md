# FutureWallet – Güncel İş Planı (Consolidated v4 + v5)

> **Durum:** v4 sertleştirme (P1-P6) tamamlandı, 113/113 test + 10/10 hardening yeşil.  
> **v5 doğrulaması sırasında bulunan yeni hatalar** (Prompt 1-9) bu planda toplanmıştır.  
> **Tarih:** 2026-11-21 | **Commit:** `315d184` | **Test:** 113/113 + 10/10 hardening yeşil

---

## 📋 Genel Durum Özeti

| Kategori | Durum | Not |
|---|---|---|
| **v4 P1-P6 (Critical/High)** | ✅ Tamamlandı | 113/113 test + 10/10 hardening yeşil |
| **v5 Prompt 1-9 (Yeni Hatalar)** | 🔴 Yapılacak | 9 adet yeni hata bulundu |
| **MVP/TODO Senkron** | 🟡 Kısmi | Çelişkili işaretler var |
| **Docker Build** | 🟡 Kırık | PB imajı checksum URL 404 |
| **CI/CD** | 🟡 Kırık | `ruff check` 25 hata |

---

## 🔴 YÜKSEK ÖNCELİK (v5 Prompt 1-4)

### P5-1: VaR/CVaR Yön Hatası (services/simulation_service.py)
**Kritiklik:** 🔴 YÜKSEK | **Kanıt:** probe  
**Sorun:** VaR/CVaR hesaplaması **kazanç** yönünde hesaplıyor (losses = initial - final_values), ama VaR için `np.percentile(losses, 5)` kullanıyor → bu EN İYİ %5 sonuç (kazanç), **kayıp değil**.  
**Etki:** Risk bir **kazanç** gibi raporlanıyor. Monte Carlo risk objesi yanlış.

**Yapılacaklar:**
1. `compute_var_cvar(initial, final_values)` fonksiyonu çıkar (services/simulation_service.py)
   - `losses = initial - final_values` (pozitif = kayıp)
   - `var_95 = np.percentile(losses, 95)`; `var_99 = np.percentile(losses, 99)`
   - `cvar_95 = losses[losses >= var_95].mean()`
   - Boş dizi / initial ≤ 0 → None; negatif VaR ham değer kalsın, `var_95_pct` de ver
2. `/api/simulation/monte-carlo` `risk` alanı bu fonksiyondan gelsin; `risk.definition` eklensin
3. UI (web_app/static/app.js + dashboard.html): VaR kartı "Olası kayıp (%95 güven)" etiketi; negatif VaR için "Bu güven düzeyinde kayıp yok"
4. MVP.md'ye VaR/CVaR tanımı ve ufku yaz (P8)

**Kabul Kriterleri (Değer Doğrulamalı):**
- Birim test: `initial=100, finals=np.linspace(0,200,10001)` → `var_95≈90`, `var_99≈98`, `cvar_95≈95`, `cvar_99≈99`; her zaman `cvar >= var` ve `var_99 >= var_95`
- API test (seed'li, PB gerçek): `risk.var_95 ≈ total_initial - percentile_values.portfolio.p5` (±1.0); `cvar_95 >= var_95`
- Kazanç dağılımı için `var_95` negatif, `var_95_pct` negatif

---

### P5-2: value-series Lookahead + Çift Sayım (services/ledger_service.py)
**Kritiklik:** 🔴 YÜKSEK | **Kanıt:** probe  
**Sorun:** `get_portfolio_snapshots()` **lookahead** + **çift sayım** yapıyor:
- (a) Tüm işlemleri bitiş tarihine kadar işleyip (lookahead), sonra tarih döngüsünde **tekrar** uyguluyor (çift sayım)
- (b) `price_fn` iç sarmalayıcı `def price_fn(...): return price_fn(...)` → **sonsuz özyineleme**
- (c) Yarım kalmış değişkenler, tutarsız zaman filtresi (`<= end+1gün` vs `<`)
- (d) Mevcut testler sadece yanıt anahtarlarını/422/429 kodlarını kontrol ediyor, **değerleri değil**

**Yapılacaklar:**
1. `get_portfolio_snapshots`'ı **baştan yaz** (artıklar silinsin):
   - İşlemleri **tek sorgu** çek (`user`, `voided=false`, `timestamp < last_date+1gün`), tarihe göre sırala
   - Tarihleri artan sırada gez; bir imleçle yalnızca `tx_date <= target_date` işlemleri **İLK KEZ** uygula (tek geçiş)
   - Her tarih için holdings'in **derin kopyasını** al
   - Hesap (total_value, total_cost, average_cost, unrealized_pnl, cash_received) tekil `get_portfolio_snapshot` ile **AYNI kodu** kullansın → ortak `_snapshot_from_holdings(holdings, cash_received, as_of, price_fn)` yardımcıları çıkar
   - Zaman filtresi tekil ile aynı: `timestamp < {gün+1 00:00}`
   - Özel `price_fn` için sarmalayıcı YOK: parametre adı `custom_price_fn`, bulk fiyat fonksiyonu ayrı (`_bulk_price_fn`), seçim `price = custom_price_fn or _bulk_price_fn`
   - Fiyat bulunamazsa 0 yerine `missing_prices` listesine yaz
2. `api/app.py` value-series: sonuç noktaları yalnızca bu fonksiyondan gelsin
3. time-travel (`time_travel_portfolio`) ve `/benchmarks` bu fonksiyonu kullanıyorsa aynı golden test onları da kapsasın

**Kabul Kriterleri (Gerçek PB, Fiyatlar Mock'lı):**
- Probe: BUY(2024-02-10, 1 adet, fiyat 100) → seri değerleri **[0,0,0,0,0,0, 100,100,100,100]**
- Golden test: Rastgele sabit seed'li 40 işlem (BUY/SELL/DIVIDEND/CASH_IN, 60 gün) → her günlük tarih için `get_portfolio_snapshots(...)[d]` ile `get_portfolio_snapshot(d)` **BİREBİR eşit** (total_value, total_cost, unrealized_pnl, cash_received, holdings)
- Aynı gün ve ertesi gün 00:00 işlemler için tekil/toplu sınır davranışı aynı
- Özel `price_fn` verilince `RecursionError` yok
- `ruff F841` uyarısı kalmaz

---

### P5-3: PB Dockerfile Build Olmuyor (Checksum URL 404)
**Kritiklik:** 🔴 YÜKSEK | **Kanıt:** probe  
**Sorun:** `docker/pocketbase/Dockerfile` checksum için `${URL}.sha256` indiriyor. PocketBase release'inde **bu dosya YOK** (HTTP 404); gerçek checksum dosyası release'in `checksums.txt`'i (HTTP 200). `curl -fsSL` 404'te hata verip build düşüyor.

**Yapılacaklar:**
1. Dockerfile: `checksums.txt`'i indir: `https://github.com/pocketbase/pocketbase/releases/download/v${POCKETBASE_VERSION}/checksums.txt`
   - `grep " pocketbase_${POCKETBASE_VERSION}_linux_${ARCH}.zip$" checksums.txt` ile ilgili satırı seç
   - `sha256sum -c -` ile doğrula; uyuşmazlıkta build düşsün
   - `ARG TARGETARCH` kullanmayı değerlendir (uname yerine)
2. CI: `docker build -f docker/pocketbase/Dockerfile .` ve `docker build .` gerçekten çalışsın (sadece `print` değil)
3. README'ye "PB sürümü yükseltirken ARG ve doğrulama adımı" notu ekle

**Kabul Kriterleri:**
- `docker build -f docker/pocketbase/Dockerfile .` başarılı
- Yanlış ARG/bozuk checksum ile build FAIL eder
- `docker compose up --build`: PB sağlıklı → host'tan `curl http://127.0.0.1:8000/health` 200 + `pb: ok`

---

### P5-4: Chart.js Vendor Eksik, CSP ile Çakışma
**Kritiklik:** 🔴 YÜKSEK | **Kanıt:** kod  
**Sorun:** CSP `script-src 'self'` gönderiyor (docstring "Chart.js yerel olarak servis edilir" diyor) ama `web_app/static/vendor/` **DİZİNİ REPODA YOK** ve dashboard.html Chart.js'i CDN'den yüklüyor. Tarayıcı CSP nedeniyle engelliyor, grafikler çalışmıyor.

**Yapılacaklar:**
1. Chart.js 4.4.0 UMD dosyasını `web_app/static/vendor/chart.umd.min.js` olarak ekle (npm pack veya jsDelivr'den indir; mevcut integrity `sha384-e6nUZ...` ile doğrula)
2. Lisans notu (MIT) `web_app/static/vendor/LICENSE-chartjs.txt` olarak ekle
3. `dashboard.html` (ve diğer şablonlar): `<script src="/static/vendor/chart.umd.min.js"></script>`; CDN etiketi ve crossorigin kaldır
3. Şablonlarda harici kaynak kalmadığını doğrulayan test yaz: tüm `<script src>`, `<link href>`, `<img src>` değerleri `/static/...` ya da aynı origin
4. Tarayıcı duman testi (Playwright, CI'da isteğe bağlı): giriş → `/web/` yükle → `window.Chart` tanımlı mı, CSP/JS hatası yok, grafik çizilmiş

**Kabul Kriterleri:**
- `GET /static/vendor/chart.umd.min.js` 200, dosya > 100 KB
- `dashboard.html`'de "jsdelivr" ve "cdn" geçmez
- Playwright: giriş sonrası `typeof Chart === 'function'`, konsol CSP/JS hatası yok, grafik çizilmiş

---

## 🟡 ORTA ÖNCELİK (v5 Prompt 5-7)

### P5-5: CI Lint Kırık (ruff check + format)
**Kritiklik:** 🟡 ORTA | **Kanıt:** ölçüm  
**Sorun:** `ruff check .` **25 hata**, `ruff format --check .` 11 dosya başarısız (CI lint işi düşer).

**Detaylı Hatalar:**
- **PLR0912 (çok fazla dal):** `api/app.py:731`, `benchmark_service.py:450`, `decision_service.py:403`, `ledger_service.py:468`, `price_service.py:134`, `simulation_service.py:219`
- **F841** kullanılmayan değişken: `ledger_service.py:577-604` (P2 ile silinecek), `price_service.py:189` (`atype`), `simulation_service.py:367` (`losses_sorted`, P1 ile silinecek), `tests/test_pb_integration.py:105` (`shadow_id`)
- **W293** boşluklu satır: `ledger_service.py:475,481`; `price_service.py:143`
- **RUF059** testlerde kullanılmayan unpack: `test_hardening.py:37,49`; `test_pb_integration.py:38,39,80`
- **I001** import sırası: `tests/conftest.py:139`
- `ruff format --check` v4.md dosyasını da biçimlendirmeye çalışıyor

**Yapılacaklar:**
1. P1/P2 bittikten sonra kalanları düzelt: ölü değişkenleri sil, `_` ile unpack et, importları sırala, `ruff format .` çalıştır
2. PLR0912 için fonksiyonları parçala (özellikle ledger snapshot, simulation, api/app.py:731)
3. `ruff.toml`: `extend-exclude = ["docs", "*.md"]` (markdown kod bloklarını kapat), eski prompt dosyalarını `docs/archive/` altına taşı
3. Ruff sürümünü sabitle (requirements-dev.in + CI `pip install ruff==<sürüm>`)
4. mypy (gevşek) gerçekten çalıştırılıp hatasız olduğu doğrulansın
5. Önerilen: pre-commit (ruff + ruff-format) ekle; README'ye kurulum notu

**Kabul Kriterleri:**
- `ruff check .` ve `ruff format --check .` hatasız
- `mypy --ignore-missing-imports --follow-imports=skip api/ services/ config.py` hatasız
- CI lint, type-check, test, docker işleri yeşil

---

### P5-6: AUTO_RETROSPECTIVE Zamanlanmıyor + `housing_index` Tipi
**Kritiklik:** 🟡 ORTA | **Kanıt:** kod + probe  

**(a) AUTO_RETROSPECTIVE:** `_run_auto_retrospective` fonksiyonu var (satır ~436) ama lifespan'da `add_job` **yok**. Bayrak true olsa da hiçbir şey olmaz.

**(b) housing_index:** Migration `1794054599_add_housing_index.js` alanı **TextField** olarak ekliyor (diğer makro alanlar number). `123.4` yazılınca `'123.4'` (str) okunuyor; kod `float()` ile çalışıyor ama tip yanlış, boş değer `''` oluyor, filtreler (`housing_index != ''`) buna göre yazılmış.

**Yapılacaklar:**
1. **Zamanlayıcı:** `AUTO_RETROSPECTIVE=true` iken `_run_auto_retrospective` job'ı eklenir (id "auto_retrospective"; günlük, ilk çalışma birkaç dakika sonra; coalesce, max_instances=1, misfire_grace_time). Sadece EXPIRED ve `ai_retrospective` boş kararlar için, kullanıcı başına `AUTO_RETROSPECTIVE_DAILY_LIMIT` ve `_check_ai_rate_limit` kurallarına uyarak. Hata/AI yoksa sessiz logla devam. Bayrak false iken job eklenmez.
2. **housing_index:** YENİ migration (mevcut dosyayı **düzenleme**): eski text alanı `housing_index_old` olarak yeniden adlandır, `housing_index` **NumberField** ekle, mevcut kayıtlarda `parseFloat` ile kopyala, eski alanı sil; geri alma işlemi de yaz. Servis kodunda yazma `float`, okuma `housing_index > 0` filtresiyle (`!= ''` yerine). MVP §5.4 güncelle (P8).

**Kabul Kriterleri (Gerçek PB):**
- Test: `AUTO_RETROSPECTIVE=true`, AI mock'lı, EXPIRED karar → job tetiklenince `ai_retrospective` dolu ve `status=REVIEWED`; kullanıcı günlük limiti aşılınca üretim durur. Bayrak false iken `get_job("auto_retrospective")` None
- Migration sonrası `pb_admin.collections.get_one("macro_data")` içinde `housing_index` tipi `"number"`; 123.4 yazıp okuyunca `float(123.4)`; eski veri (text '100.5') migration sonrası `100.5`
- Benchmarks çıktısındaki housing_index hesabı önceki sonuçlarla aynı

---

### P5-7: Hata Semantiği + PB/Compose Sertleştirme
**Kritiklik:** 🟡 ORTA | **Kanıt:** probe + kod  

**Sorunlar:**
- (a) Başkasının `transaction_id`'siyle karar oluşturma → `PermissionError` fırlatılıyor, endpoint yakalamıyor → **HTTP 500** (beklenen 404/422)
- (b) `api/app.py`'de hâlâ `raise HTTPException(500, str(e))` (satır ~1178, 1319, 1335, 1356, 1378, 1410) ve bazı 400/409/503'te `str(e)` var: iç hata metni (PB veri, Python istisnaları) istemciye sızıyor
- (c) PB CORS varsayılanı tüm origin'lere açık; entrypoint `--origins` vermiyor; superuser parolası CLI argümanı olarak geçiyor; compose'ta `read_only`/`cap_drop`/`no-new-privileges` yok

**Yapılacaklar:**
1. **Tek istisna eşleme katmanı** (FastAPI `exception_handler`):
   - `PermissionError` → 404 (kaynak sızdırmadan)
   - `NotFound` → 404
   - `ValueError` → 422 (mesaj güvenli)
   - `ConflictError` → 409
   - PB istemci hataları → 503 "Veri servisi geçici olarak kullanılamıyor"
   - `AIUnavailable` → 503, `AIGenerationError` → 502
   - Diğer → 500 + genel mesaj "Beklenmeyen bir hata oluştu" + `request_id` (log'da `logger.exception`)
   - Tüm `HTTPException(..., str(e))` kaldır; endpoint try/except bloklarını sadeleştir
2. Decision create: başkasının/olmayan `transaction_id` → 404 ("İşlem bulunamadı"); aynı mantık shadow-position `decision_id`'sinde (şu an 400, 404'e hizala)
3. PB: entrypoint'e `--origins` ver (env: `PB_ALLOWED_ORIGINS`, varsayılan `http://127.0.0.1:8000,http://localhost:8000`; flag adı `./pocketbase serve --help` ile doğrula). Superuser'ı komut satırı yerine JS migration ile oluşturmayı değerlendir (olmuyorsa mevcut yöntem + README risk notu)
4. Compose app servisi: `read_only: true`, `tmpfs: [/tmp]`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`; PB servisi için `cap_drop: [ALL]` ve `no-new-privileges`

**Kabul Kriterleri:**
- Başkasının `transaction_id` → 404/422 (500 değil); log'da istisna var
- Servis katmanı `RuntimeError("secret-internal-detail")` fırlatınca yanıt 500 ama gövdede bu metin YOK, `request_id` var
- `grep -n "str(e)\|str(exc)" api/app.py` HTTPException içinde sonuç vermez
- PB'ye `Origin: https://evil.example` ile istek → `Access-Control-Allow-Origin` header'ı yok; izinli origin için var
- `docker compose up` read_only + cap_drop ile sağlıklı kalkar

---

## 🟡 ORTA: MVP/TODO Senkronu (Prompt 8)

**Sorun:** Faz 2 kararları (ENAG, kira endeksi) yalnızca TODO'da; MVP.md eski:
- §1 "TÜİK/ENAG TÜFE" (satır 18), §3.4 "Ortalama Ev/Kira katsayısı" (satır 65)
- §5.4 `macro_data` alanları `gold_try` (gerçek: `gold_try_gram`, `housing_index`, `source`, `is_estimate`)
- Mimari diyagramı "SQLite Storage" (artık PocketBase), VaR/CVaR çıktısı ve Faz 2 işaretleri yok
- TODO kendi içinde çelişiyor: "[ ] ENAG / Ev-Kira / VaR-CVaR — Faz 2'ye ertelendi" iken VaR/CVaR "eklendi" deniyor

**Yapılacaklar:**
1. **MVP.md:**
   - §1/§2: "TÜİK TÜFE ve US CPI" (ENAG = Faz 2 / kapsam dışı; resmî API yok)
   - §3.4: "Gram Altın, S&P 500 ve konut fiyat endeksi (EVDS); kira endeksi Faz 2"
   - §5.4: macro_data alanları (`gold_try_gram`, `gold_usd`, `sp500`, `tr_cpi`, `us_cpi`, `housing_index`, `source`, `is_estimate`); price_history alanları; §5.3 shadow `user` alanı
   - Mimari diyagramı: SQLite → PocketBase; VaR/CVaR tanımı (P1) ve ufku; scheduler job'ları (expire, refresh_macro, opsiyonel auto_retrospective)
   - "Bilinen Sınırlar / Faz 2" bölümü: ENAG, kira endeksi, çok worker'da zamanlayıcı/hız sınırı
2. **TODO.md:** Tek tutarlı sürüm; test sayısı `pytest --collect-only -q` ile aynı; her [x] bir test dosyası/adına bağlı; P1-P9 (v5) maddeleri listelenip tamamlandıkça işaretlensin; "ruff temiz", "docker build [x]" iddiaları yalnızca komut çıktısıyla (tarih + commit). Çelişkili satırları düzelt
3. **README:** Çalıştırma adımları ile compose değişkenleri (`POCKETBASE_PUBLIC_URL`, `PB_ALLOWED_ORIGINS`, `OPENROUTER_MODELS`, `ENABLE_SCHEDULER`, `AUTO_RETROSPECTIVE`) tek tabloda
4. CI'ya doküman tutarlılık adımı: TODO.md içindeki "N/N geçti" ifadesi `pytest --collect-only` sayısıyla eşleşmiyorsa uyarı ver

**Kabul Kriterleri:**
- MVP.md'de her özellik testli ya da "Faz 2/kapsam dışı" olarak işaretli
- `grep -n "ENAG\|SQLite Storage\|gold_try\b" MVP.md` yalnızca Faz 2 notlarında/güncel alan adlarıyla sonuç verir
- TODO'daki test sayısı `pytest --collect-only` sayısıyla eşit; çelişen madde kalmaz

---

## 🟢 Regresyon Test Dosyası + Son Doğrulama (Prompt 9)

**Yeni dosya:** `tests/test_v5_regressions.py` (mevcut `conftest.py` fixture'larına uygun). Her test ilgili prompt uygulanmadan ÖNCE başarısız olmalı. Fiyat/geçmiş veri mock'lı, PB gerçek.

**Test Kapsamı:**
- P1: `compute_var_cvar` birim testi + Monte Carlo API `risk.var_95 ≈ initial - p5`
- P2: `value-series` lookahead/çift sayım yok + tekil snapshot ile birebir eşit
- P3: PB Dockerfile `checksums.txt` var, `.sha256` yok
- P4: Chart.js yerel (`/static/vendor/chart.umd.min.js`), CDN yok, HTML'de `jsdelivr`/`cdn` yok
- P6: `AUTO_RETROSPECTIVE=true` → scheduler job eklenir; `housing_index` tipi `number`
- P7: Başkasının `transaction_id` → 404/422; `500 + str(e)` iç hata sızmaz; PB CORS sadece izinli origin
- P8: MVP.md/TODO.md çelişkisi yok, test sayıları eşleşir

**Son Doğrulama Listesi (Tüm Promptlar Bittikten Sonra):**
1. `pytest -q` yeşil (113 + yeni testler); `ruff check .`, `ruff format --check .`, mypy hatasız; CI güncel HEAD'de yeşil
2. VaR/CVaR: Bilinen dağılımda beklenen değerler; monte-carlo çıktısında `var_95 ≈ initial - p5`
3. value-series: Alım öncesi 0, sonrası doğru miktar; tüm tarihlerde tekil snapshot ile birebir eşit
4. `docker compose up --build` sıfırdan çalışır (PB imajı dahil); `/health` `pb: ok`; konteynerler root değil, read_only/cap_drop ile sağlıklı
5. Tarayıcı: Giriş → dashboard → grafikler çizilir; konsolda CSP/JS hatası yok
6. `AUTO_RETROSPECTIVE` açıkken EXPIRED karar için AI retrospektifi üretilir, kapalıyken job yok
7. `macro_data.housing_index` number alanı; eski veri migration ile korunmuş
6. Hata yanıtlarında iç istisna metni yok; yabancı `transaction_id` 404/422; PB CORS yalnızca izinli origin
7. MVP.md ve TODO.md gerçek durumla örtüşür; çelişkili satır ve doğrulanmamış iddia kalmaz

---

## 📅 Önerilen Sıralama (Bağımlılık Sırası)

| Sıra | Prompt | Neden Önce | Tahmini Süre |
|---|---|---|---|
| 1 | **P5-3** (PB Dockerfile) | Docker build kırık, CI/CD bloklar | 0.5 gün |
| 2 | **P5-1** (VaR/CVaR) | Bağımsız, kritik risk metriği | 1 gün |
| 3 | **P5-2** (value-series) | Bağımsız, kritik veri doğruluğu | 1.5 gün |
| 4 | **P5-4** (Chart.js/CSP) | Bağımsız, UI bloklar | 0.5 gün |
| 5 | **P5-6** (AUTO_RETRO + housing) | P3 migration + P1/P2 sonrası | 1 gün |
| 6 | **P5-7** (Hata semantiği + PB/compose) | Tüm endpoint'ler etkilenir | 1.5 gün |
| 7 | **P5-5** (CI Lint) | Kod stabilise olunca | 0.5 gün |
| 8 | **MVP/TODO Senkron (Prompt 8)** | Kod bittikten sonra | 0.5 gün |
| 9 | **Regresyon Test + Son Doğrulama (Prompt 9)** | En son | 0.5 gün |

---

## ✅ TAMAMLANAN (v4 P1-P6) – Referans

| Prompt | Konu | Durum |
|---|---|---|
| P1 | Docker Compose, PB imajı, build context | ✅ |
| P2 | Zamanlayıcı (ilk çalışma 30sn, worker koruması) | ✅ |
| P3 | PB kuralları (write rules null), yazma yolu (admin client), rate limit | ✅ |
| P4 | AI modeller (env), hız sınırı (dk 5 + gün 30), hata sızıntısı kapalı | ✅ |
| P5 | Value-series DoS (nokta sayısı önceden), N+1 (bulk), rate limit (dk 10) | ✅ |
| P6 | CSP (jsdelivr yok, Chart.js yerel), /health gerçek PB, _init_pocketbase temiz, _user_locks LRU, Enum tekilleştirme, EVDS auth | ✅ |

**Test Sonucu:** 113/113 test + 10/10 hardening yeşil ✅

---

## 📝 KAYIT: v4/v5 Karşılaştırması

| v4 Prompt | Durum | v5 Karşılığı | Not |
|---|---|---|---|
| P1 Docker | ✅ | P5-3 (build kırık) | v4 "tamam" v5'te kırık bulundu |
| P2 Scheduler | ✅ | - | Tamam |
| P3 PB Rules | ✅ | - | Tamam |
| P4 AI | ✅ | - | Tamam |
| P5 Value-Series | ✅ | P5-2 (lookahead/çift sayım) | v4 "tamam" v5'te mantık hatası bulundu |
| P6 CSP/Health | ✅ | P5-4 (Chart.js/CSP) | v4 "tamam" v5'te vendor eksik bulundu |
| - | - | P5-1 VaR/CVaR | v4'te yok, v5'te bulundu |
| - | - | P5-5 CI Lint | v4'te yok, v5'te bulundu |
| - | - | P5-6 AUTO_RETRO/housing | v4'te "tamam" işaretli, v5'te eksik bulundu |
| - | - | P5-7 Hata semantiği | v4'te "tamam" işaretli, v5'te eksik bulundu |
| - | - | P8 MVP/TODO Sync | v4'te "tamam" işaretli, v5'te çelişki bulundu |
| - | - | P9 Regresyon Testler | Yeni |

---

## 📌 ÖZET: KALAN İŞLER (YAPILACAKLAR)

| # | İş | Öncelik | Bağımlılık | Tahmin |
|---|---|---|---|---|
| 1 | PB Dockerfile checksums.txt | 🔴 Yüksek | - | 0.5 gün |
| 2 | VaR/CVaR yön düzeltme | 🔴 Yüksek | - | 1 gün |
| 3 | value-series lookahead/çift sayım düzeltme | 🔴 Yüksek | - | 1.5 gün |
| 4 | Chart.js vendor + CSP | 🔴 Yüksek | - | 0.5 gün |
| 6 | AUTO_RETRO job + housing_index migration | 🟡 Orta | P3, P1, P2 | 1 gün |
| 7 | Hata semantiği (exception handler) + PB/compose | 🟡 Orta | Tüm endpoint'ler | 1.5 gün |
| 5 | CI Lint (ruff/mypy) | 🟡 Orta | Kod stabil olunca | 0.5 gün |
| 8 | MVP/TODO Senkron | 🟡 Orta | Kod bittikten sonra | 0.5 gün |
| 9 | Regresyon test dosyası + Son doğrulama | 🟢 Düşük | En son | 0.5 gün |

**Toplam Tahmini Süre:** ~8 gün (paralel çalışılabilir kısımlar hariç)

---

## 📌 NOTLAR

1. **v4 "tamam" işaretli maddelerden bazıları v5 doğrulamasında kırık/eksik bulundu** → v5 kaynak alınacak
2. **Testler DEĞER doğrulamalı olmalı** (Prompt 0 kuralı): sadece HTTP kodu/yapı değil, beklenen sayıyı elle hesaplayıp assert et
3. **Docker/Tarayıcı adımları gerçek test edilmeli** (Prompt 0 kuralı): statik dosya kontrolü yetmez
4. **TODO.md'de bir madde sadece ilgili testle kanıtlandığında [x]** olur; "ruff temiz", "docker build [x]" komut çıktısıyla yazılır
5. **CI/CD:** `ruff==<sürüm>` sabitlensin; pre-commit önerilir

---

**Hazırlayan:** FutureWallet Geliştirme Ekibi  
**Tarih:** 2026-11-21  
**Versiyon:** 1.0 (v4+v5 konsolide)