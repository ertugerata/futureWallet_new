# FutureWallet – Düzeltme Promptları v5 (son duruma göre)

Dayanak: repo `ertugerata/futureWallet_new`, commit **`315d184`** (2026-11-21); MVP.md ve TODO.md (v6).
Bu dosya v4'ün yerine geçer. v4'ün büyük kısmı tamamlandı ve bağımsız doğrulandı: `import api.app` temiz, **113/113 test gerçek PocketBase 0.40.6 ile geçiyor**, yazma endpoint'lerinde başka kullanıcı erişimi yok (12 çağrının hepsi 404), PB'ye doğrudan yazma kapalı, zamanlayıcı ilk çalışması düzeltildi, `value-series` aralık sınırı ve hız sınırı çalışıyor, AI hata sızıntısı kapalı, başlıklar ve `/health` düzeltildi.

v5, o doğrulama sırasında bulunan **kalan hataları** kapatır. Çoğu mevcut testlerin yakalayamadığı türden (testler yanıt şeklini ve limitleri kontrol ediyor, değerleri değil).

Kanıt işaretleri: **[probe]** gerçek PB'ye karşı ek testle doğrulandı. **[kod]** kod okuması (Docker ve tarayıcı çalıştırılmadı).

## A. Öncelik tablosu

| # | Konu | Seviye | Kanıt |
|---|------|--------|-------|
| 0 | Ortak kurallar | – | – |
| 1 | VaR/CVaR yön hatası | Yüksek | probe |
| 2 | `value-series` lookahead + çift sayım | Yüksek | probe |
| 3 | PB imajı build olmuyor (checksum URL) | Yüksek | probe |
| 4 | Chart.js vendor eksik, CSP ile çakışma | Yüksek | kod |
| 5 | CI lint kırık (ruff check + format) | Orta | ölçüm |
| 6 | AUTO_RETROSPECTIVE zamanlanmıyor, `housing_index` tipi | Orta | kod + probe |
| 7 | Hata semantiği: 500 + `str(e)`, `PermissionError`, PB CORS | Orta | probe + kod |
| 8 | MVP.md / TODO.md senkronu | Orta | kod |
| 9 | Regresyon test dosyası ve son doğrulama | – | – |

Sıra bağımlılık gözetilerek verildi. Her adım sonunda `pytest -q` yeşil olmalı.

---

## Prompt 0 – Ortak kurallar (her promptun başına ekleyin)

```text
Proje: FutureWallet. Mimari: PocketBase v0.40.6 (DB + Auth) + FastAPI (hesaplama) + OpenRouter (LLM).
Referanslar: MVP.md, TODO.md. SDK: pocketbase==0.17.3 (SENKRON; get_list(page, per_page,
query_params), update(id, body), client.filter(raw, params)).

Kurallar:
- Yalnızca istenen kapsamı değiştir; mevcut 113 test yeşil kalmalı.
- Testler DEĞER doğrulamalı olsun, yalnızca yanıt şekli/HTTP kodu değil: beklenen sayıyı elle
  hesaplayıp assert et. Bu repoda "geçen test = doğru davranış" varsayımı iki kez yanıltıcı çıktı
  (value-series, VaR).
- PB'ye dokunan davranışları GERÇEK PocketBase'e karşı test et (conftest: pb_server, make_user,
  api_client, auth_headers, pb_admin). PB'yi mock'lama.
- Her düzeltme için, düzeltmeden ÖNCE başarısız olan bir regresyon testi ekle (P9'daki dosya).
- Docker/tarayıcıya dokunan adımlarda gerçekten `docker compose up --build` ve tarayıcı duman
  testi çalıştır; yalnızca statik dosya kontrolüyle yetinme.
- TODO.md'de bir maddeyi yalnızca ilgili testle kanıtlandığında [x] yap; "ruff temiz", "docker
  build geçti" gibi iddiaları yazmadan önce komutu gerçekten çalıştır.
- Sır/anahtar/parola koda, loga, hata gövdesine, git'e, imaja yazma.
```

---

## Prompt 1 – VaR/CVaR yön hatası (YÜKSEK)

```text
Mevcut durum [probe]: services/simulation_service.py (VaR/CVaR bloğu, ~satır 355-385) kayıp
pozitif tanımlıyor (losses = initial - final_values) ama VaR için `np.percentile(losses, 5)` ve
`np.percentile(losses, 1)` kullanıyor; bu EN İYİ %5/%1 sonuçların eşiğidir (kazanç). CVaR de
`losses >= p5` olanların ortalaması, yani sonuçların ~%95'inin ortalaması (kuyruk değil).
Gerçek simülasyonda (initial=100, p5_final=40.96, p95_final=114.17):
  kod:   var_95 = -14.17, var_99 = -38.95, cvar_95 = 31.79
  doğru: var_95 = 59.04 (= initial - p5_final), cvar_95 > var_95
Yani risk bir KAZANÇ gibi raporlanıyor. TODO/MVP "VaR/CVaR eklendi" diyor.

Yapılacaklar:
1. Saf bir fonksiyon çıkar: `compute_var_cvar(initial: float, final_values: np.ndarray) -> dict`
   (services/simulation_service.py). Tanım:
     losses = initial - final_values            # pozitif = kayıp
     var_95 = np.percentile(losses, 95); var_99 = np.percentile(losses, 99)
     cvar_95 = losses[losses >= var_95].mean(); cvar_99 = losses[losses >= var_99].mean()
   Boş dizi / initial <= 0 için None döndür. Negatif VaR (o güven düzeyinde kayıp yok) ham
   değer olarak kalsın ama yanıtta `var_95_pct = var_95 / initial * 100` de verilsin.
2. /api/simulation/monte-carlo `risk` alanı bu fonksiyondan gelsin; yanıta `risk.definition`
   ("loss-based, positive = loss, horizon = days") ekle. Kullanılmayan `losses_sorted` değişkenini sil.
3. UI (web_app/static/app.js + dashboard.html): VaR kartında "Olası kayıp (%95 güven)" gibi
   etiket; değerler para birimi + yüzde ile; negatif VaR için "Bu güven düzeyinde kayıp yok".
4. MVP.md'ye VaR/CVaR tanımını ve ufuğunu yaz (P8).

Kabul kriterleri (değer doğrulamalı):
- Birim test: initial=100, finals=np.linspace(0, 200, 10001) -> var_95 ≈ 90 (±0.1),
  var_99 ≈ 98 (±0.1), cvar_95 ≈ 95 (±0.2), cvar_99 ≈ 99 (±0.2); her zaman cvar >= var ve
  var_99 >= var_95.
- API testi (seed'li, PB gerçek): risk.var_95 ≈ total_initial_value - percentile_values.portfolio.p5
  (±1.0); cvar_95 >= var_95.
- Hepsi kazanç dağılımı (finals > initial) için var_95 negatif ve `var_95_pct` negatif döner.
```

---

## Prompt 2 – `value-series` lookahead ve çift sayım (YÜKSEK)

```text
Mevcut durum [probe]: 2024-02-10'da 1 BTC alınmış (fiyat sabit 100) portföyde haftalık seri
2024-01-01..2024-03-04 şunu döndürdü:
  01-01..02-05: 100 (doğrusu 0)   |   02-12 ve sonrası: 200 (doğrusu 100)
Tekil GET /api/portfolio/snapshot?date=2024-01-08 -> 0, ?date=2024-02-12 -> 100 (doğru).
Kök neden: services/ledger_service.py `get_portfolio_snapshots`:
  (a) "Tüm tarihler için işlemleri işle" döngüsü bitiş tarihine kadar TÜM işlemleri
      current_holdings'a uyguluyor (lookahead), sonra tarih döngüsü aynı işlemleri tekrar
      uyguluyor (çift sayım).
  (b) price_fn None değilken kurulan iç sarmalayıcı kendi adını çağırıyor:
      `def price_fn(...): return price_fn(...)` -> sonsuz özyineleme.
  (c) Kullanılmayan değişkenler (cum_cash_received, sorted_div_dates, div_idx, date_idx,
      current_date, holdings_at_date, prev_date) yarım kalmış bir yaklaşımın artığı.
  (d) Zaman filtresi tutarsız: toplu `timestamp <= end+1gün 00:00`, tekil `<` kullanıyor.
Mevcut testler yalnızca yanıt anahtarlarını, 422/429 kodlarını ve nokta sayısını kontrol ediyor.

Yapılacaklar:
1. `get_portfolio_snapshots`'ı baştan yaz (artıklar silinsin):
   - İşlemleri tek sorguyla çek (`user`, `voided=false`, `timestamp < last_date+1gün`), tarihe göre sırala.
   - Tarihleri artan sırada gez; bir imleçle yalnızca `tx_date <= target_date` olan işlemleri
     İLK KEZ uygula (tek geçiş). Her tarih için holdings'in derin kopyasını al (sonraki işlemler
     önceki snapshot'ı değiştirmesin). Cash/DIVIDEND kümülatifi aynı imleçle tutulsun.
   - Hesap (total_value, total_cost, average_cost, unrealized_pnl, cash_received) tekil
     get_portfolio_snapshot ile AYNI kodu kullansın: ortak bir `_snapshot_from_holdings(holdings,
     cash_received, as_of, price_fn)` yardımcısı çıkar ve ikisi de onu çağırsın.
   - Zaman filtresi tekil ile aynı: `timestamp < {gün+1 00:00}`.
   - Özel `price_fn` için sarmalayıcı yok: parametre adı `custom_price_fn`, bulk fiyat
     fonksiyonu ayrı isimli (`_bulk_price_fn`) ve seçim `price = (custom_price_fn or _bulk_price_fn)`.
   - Fiyat bulunamazsa 0 yerine `missing_prices` listesine yazılsın (tekil ile tutarlı).
2. api/app.py value-series: sonuç noktaları artık yalnızca bu fonksiyondan gelsin; start_value/
   end_value/min/max aynı serinin türevleri olsun.
3. Aynı hata sınıfı için time-travel (`time_travel_portfolio`) ve /benchmarks'ın bu fonksiyonu
   kullanıp kullanmadığını kontrol et; kullanıyorsa aynı golden test onları da kapsasın.

Kabul kriterleri (gerçek PB, fiyatlar mock'lı):
- Probe senaryosu: BUY(2024-02-10, 1 adet, fiyat 100) -> seri değerleri tam olarak
  [0,0,0,0,0,0, 100,100,100,100] (01-01…02-05 için 0; 02-12 ve sonrası 100).
- Golden test: rastgele ama sabit seed'li bir işlem dizisi (BUY/SELL/DIVIDEND/CASH_IN, 40 işlem,
  60 gün) ve her günlük tarih için get_portfolio_snapshots(...)[d] ile get_portfolio_snapshot(d)
  total_value, total_cost, unrealized_pnl, cash_received ve holdings miktarlarında BİREBİR eşit.
- Aynı gün ve ertesi gün 00:00'daki işlemler için tekil/toplu sınır davranışı aynı.
- Özel price_fn verilince RecursionError yok.
- ruff F841 uyarısı kalmaz.
```

---

## Prompt 3 – PocketBase imajı build olmuyor (YÜKSEK)

```text
Mevcut durum [probe]: docker/pocketbase/Dockerfile checksum için `${URL}.sha256` indiriyor.
PocketBase release'inde bu dosya YOK (HTTP 404); gerçek checksum dosyası release'in
`checksums.txt`'i (HTTP 200). `curl -fsSL` 404'te hata verdiği için
`docker compose up --build` PB imajında düşer. TODO'da bu madde [x].

Yapılacaklar:
1. Dockerfile: `checksums.txt`'i
   https://github.com/pocketbase/pocketbase/releases/download/v${POCKETBASE_VERSION}/checksums.txt
   adresinden indir (curl -fsSL), zip'in satırını seç
   (`grep " pocketbase_${POCKETBASE_VERSION}_linux_${ARCH}.zip$" checksums.txt` — satır biçimini
   gerçek dosyada doğrula) ve `sha256sum -c -` ile doğrula; uyuşmazlıkta build düşsün.
   Mimari eşlemesi (x86_64->amd64, aarch64->arm64) korunur; uname çıktısına güvenmeden
   `ARG TARGETARCH` kullanmayı değerlendir.
2. Aynı build, CI'da gerçek `docker build` ile her iki imaj (app ve PB) için çalışsın; CI'daki
   mevcut "docker" işini yalnızca `print` çalıştırmak yerine `docker build -f
   docker/pocketbase/Dockerfile .` ve `docker build .` yapacak şekilde güncelle.
3. README'ye "PB sürümü yükseltirken ARG ve doğrulama adımı" notu ekle.

Kabul kriterleri:
- `docker build -f docker/pocketbase/Dockerfile .` başarılı.
- Yanlış ARG sürümü ya da bozuk checksum ile build FAIL eder (denemesini yap).
- `docker compose up --build`: PB sağlıklı -> uygulama sağlıklı; host'tan `curl
  http://127.0.0.1:8000/health` 200 ve `pb: ok`.
- Statik test (P9): Dockerfile'da `.sha256` geçmez, `checksums.txt` geçer.
```

---

## Prompt 4 – Chart.js vendor eksik, CSP ile çakışma (YÜKSEK)

```text
Mevcut durum [kod]: api/app.py CSP `script-src 'self'` gönderiyor (docstring "Chart.js yerel
olarak servis edilir (static/vendor/)" diyor) ama web_app/static/vendor/ DİZİNİ REPODA YOK
(git ls-files boş, .gitignore ignore etmiyor) ve web_app/templates/dashboard.html Chart.js'i
hâlâ https://cdn.jsdelivr.net/npm/chart.js@4.4.0/... adresinden (integrity ile) yüklüyor.
Tarayıcı CSP nedeniyle scripti engeller; `new Chart(...)` (app.js:116) ReferenceError verir ve
tüm grafikler çalışmaz. TODO hem "Chart.js /static/vendor/" hem "Chart.js SRI" yazıyor.

Yapılacaklar:
1. Chart.js 4.4.0 UMD dosyasını web_app/static/vendor/chart.umd.min.js olarak ekle (npm pack
   veya jsDelivr'den geliştirme zamanında indir; şablondaki mevcut integrity
   sha384-e6nUZLBkQ86NJ6TVVKAeSaK8jWa3NhkYWZFomE39AvDbQWeie9PlQqM3pmYW5d1g ile dosyayı doğrula).
   Lisans notunu (MIT) web_app/static/vendor/LICENSE-chartjs.txt olarak ekle. Dosya git'te
   izlenmeli (git ls-files ile doğrula).
2. dashboard.html (ve varsa diğer şablonlar): `<script src="/static/vendor/chart.umd.min.js"></script>`;
   CDN etiketi ve crossorigin kaldırılır. CSP aynı kalır (`script-src 'self'`).
3. Şablonlarda harici kaynak kalmadığını doğrulayan bir test yaz: tüm `<script src>`, `<link href>`,
   `<img src>` değerleri `/static/...` ya da aynı origin olmalı.
4. Tarayıcı duman testi (Playwright, CI'da isteğe bağlı iş): giriş yap, /web/ yükle,
   `window.Chart` tanımlı mı, console'da CSP ihlali ve JS hatası var mı kontrol et; en az bir
   grafik canvas'ı çizilmiş olmalı.

Kabul kriterleri:
- GET /static/vendor/chart.umd.min.js 200 ve dosya boyutu > 100 KB.
- dashboard.html'de "jsdelivr" ve "cdn" geçmez.
- Playwright: giriş sonrası `typeof Chart === 'function'`, console'da "Content Security Policy"
  hatası yok, snapshot grafiği render edilmiş.
```

---

## Prompt 5 – CI lint kırık (ORTA)

```text
Mevcut durum [ölçüm]: `ruff check .` 25 hata, `ruff format --check .` 11 dosya için başarısız
(CI'nın lint işi düşer). TODO "ruff check ve format temiz" diyor. Ayrıntı:
- PLR0912 (çok fazla dal): api/app.py:731, benchmark_service.py:450, decision_service.py:403,
  ledger_service.py:468, price_service.py:134, simulation_service.py:219.
- F841 kullanılmayan değişken: ledger_service.py:577-604 (P2 ile silinecek), price_service.py:189
  (`atype`), simulation_service.py:367 (`losses_sorted`, P1 ile silinecek),
  tests/test_pb_integration.py:105 (`shadow_id`).
- W293 boşluklu satır: ledger_service.py:475,481; price_service.py:143.
- RUF059 testlerde kullanılmayan unpack: test_hardening.py:37,49; test_pb_integration.py:38,39,80.
- I001 import sırası: tests/conftest.py:139.
- `ruff format --check` FUTUREWALLET_DUZELTME_PROMPTLARI_v4.md dosyasını da (içindeki Python
  bloğunu) biçimlendirmeye çalışıyor.

Yapılacaklar:
1. P1/P2 tamamlandıktan sonra kalan hataları düzelt: ölü değişkenleri sil, `_` ile unpack et,
   importları sırala, `ruff format .` çalıştır. PLR0912 için tercih: fonksiyonları parçala
   (özellikle ledger snapshot, simulation, api/app.py:731). Parçalamak risk yaratıyorsa yalnızca
   o fonksiyonda `# noqa: PLR0912  # gerekçe` kullan; toplu ignore ekleme.
2. ruff.toml: `extend-exclude = ["docs", "*.md"]` (markdown kod bloklarının biçimlendirilmesini
   kapat) ve eski prompt dosyalarını docs/archive/ altına taşı.
3. Ruff sürümünü sabitle (requirements-dev.in ve CI'da `pip install ruff==<sürüm>`); CI ile
   yerel aynı sürümü kullansın.
4. mypy işi (gevşek) gerçekten çalıştırılıp hatasız olduğu doğrulansın; TODO'daki iddia buna
   dayansın.
5. Önerilen: pre-commit (ruff + ruff-format) ekle; README'ye kurulum notu.

Kabul kriterleri:
- `ruff check .` ve `ruff format --check .` hatasız (komutu CI ile aynı sürümde çalıştır).
- `mypy --ignore-missing-imports --follow-imports=skip api/ services/ config.py` hatasız.
- CI'nın lint, type-check, test ve docker işleri yeşil (güncel HEAD için gerçek run bağlantısı).
```

---

## Prompt 6 – AUTO_RETROSPECTIVE ve `housing_index` tipi (ORTA)

```text
(a) AUTO_RETROSPECTIVE [kod]: api/app.py'de `_run_auto_retrospective` (satır ~436) tanımlı ve
    config.AUTO_RETROSPECTIVE bayrağını kontrol ediyor, ama lifespan'da hiçbir `add_job` ona
    bağlı değil (dosyada tek referans fonksiyon tanımı). Bayrak true yapılsa da hiçbir şey olmaz.
(b) housing_index [probe]: migration 1794054599_add_housing_index.js alanı TextField olarak
    ekliyor (diğer makro alanlar number). 123.4 yazılınca '123.4' (str) geri okunuyor; kod
    float() ile okuduğu için çalışıyor ama tip yanlış, boş değer '' oluyor ve filtreler
    (`housing_index != ''`) buna göre yazılmış.

Yapılacaklar:
1. Zamanlayıcı: AUTO_RETROSPECTIVE=true iken `_run_auto_retrospective` job'ı eklenir
   (id "auto_retrospective"; günlük, ilk çalışma birkaç dakika sonra; coalesce, max_instances=1,
   misfire_grace_time). Yalnızca EXPIRED ve ai_retrospective boş kararlar için, kullanıcı başına
   AUTO_RETROSPECTIVE_DAILY_LIMIT ve `_check_ai_rate_limit` kurallarına uyarak çalışsın; başarıda
   ai_retrospective yazılır, status REVIEWED olur (admin client, sahiplik zaten karar kaydından).
   Hata/AI yapılandırması yoksa job sessizce loglar ve devam eder. Bayrak false iken job eklenmez.
2. housing_index: YENİ bir migration (mevcut dosyayı düzenleme): eski text alanı
   `housing_index_old` olarak yeniden adlandır, `housing_index` NumberField ekle, mevcut kayıtlarda
   parseFloat ile kopyala, eski alanı sil; geri alma işlemi de yaz. Servis kodunda yazma float,
   okuma `housing_index > 0` filtresiyle (`!= ''` yerine) olsun. MVP §5.4'ü güncelle (P8).

Kabul kriterleri (gerçek PB):
- Test: AUTO_RETROSPECTIVE=true, AI mock'lı, EXPIRED bir karar -> job tetiklenince (job'ı
  `modify(next_run_time=now)` ile çalıştır) ai_retrospective dolu ve status REVIEWED; kullanıcı
  günlük limiti aşılınca üretim durur. Bayrak false iken `get_job("auto_retrospective")` None.
- Migration sonrası `pb_admin.collections.get_one("macro_data")` içinde housing_index tipi
  "number"; 123.4 yazıp okuyunca float(123.4); eski veri (text '100.5') migration sonrası 100.5.
- benchmarks çıktısındaki housing_index hesabı önceki sonuçlarla aynı (mevcut test yeşil).
```

---

## Prompt 7 – Hata semantiği ve PB/compose sertleştirme (ORTA)

```text
Mevcut durum:
(a) [probe] POST /api/decisions ile başkasının transaction_id'si gönderilince
    decision_service `PermissionError("Transaction does not belong to user")` fırlatıyor ve
    endpoint yakalamıyor -> HTTP 500 (izolasyon korunuyor ama yanıt yanlış). Beklenen 404/422.
(b) [kod] api/app.py'de hâlâ `raise HTTPException(500, str(e))` (satır ~1178, 1319, 1335, 1356,
    1378, 1410) ve bazı 400/409/503'lerde `str(e)` var: iç hata metni (PB veri/ayrıntıları,
    Python istisnaları) istemciye gidiyor. Genel-mesaj kuralı yalnızca AI yolunda uygulanmış.
(c) [kod] PB CORS varsayılanı tüm origin'lere açık; entrypoint `--origins` vermiyor. Superuser
    parolası `superuser upsert` komut satırı argümanı olarak geçiyor. compose'ta app için
    `read_only`/`cap_drop`/`no-new-privileges` yok.

Yapılacaklar:
1. Tek bir istisna eşleme katmanı (FastAPI exception_handler'lar): PermissionError -> 404 (kaynağı
   sızdırmadan), NotFound -> 404, ValueError -> 422 (kullanıcı girdisi kaynaklıysa mesaj güvenli
   bir metinle), ConflictError -> 409, PB istemci hataları -> 503 "Veri servisi geçici olarak
   kullanılamıyor", AIUnavailable -> 503, AIGeneration -> 502, diğer her şey -> 500 + genel mesaj
   "Beklenmeyen bir hata oluştu" + `request_id` (log'da ayrıntı, `logger.exception`). Tüm
   `HTTPException(..., str(e))` kullanımlarını kaldır; endpoint'lerdeki gereksiz try/except
   bloklarını sadeleştir.
2. decision create: başkasının/olmayan transaction_id -> 404 ("İşlem bulunamadı"); aynı mantık
   shadow-position decision_id'sinde (şu an 400 dönüyor; 404'e hizala).
3. PB: entrypoint'e `--origins` ver (env: PB_ALLOWED_ORIGINS, varsayılan
   http://127.0.0.1:8000,http://localhost:8000; bayrağın adını `./pocketbase serve --help` ile
   doğrula). Superuser'ı komut satırı argümanı yerine ilk açılışta çalışan bir JS migration ile
   `$os.getenv("POCKETBASE_EMAIL"/"POCKETBASE_PASSWORD")` kullanarak oluşturmayı değerlendir
   (olmuyorsa mevcut yöntem + README'de risk notu kalsın).
4. compose app servisi: `read_only: true`, `tmpfs: [/tmp]`, `cap_drop: [ALL]`,
   `security_opt: [no-new-privileges:true]` (uygulama çalışıyorsa); PB servisi için
   `cap_drop: [ALL]` ve `no-new-privileges`.

Kabul kriterleri:
- Başkasının transaction_id'siyle karar oluşturma 404/422 (500 değil); log'da istisna var.
- Servis katmanı RuntimeError("secret-internal-detail") fırlatacak şekilde monkeypatch'lenince
  yanıt 500 ama gövdede bu metin YOK ve request_id var.
- `grep -n "str(e)\|str(exc)" api/app.py` HTTPException içinde sonuç vermez.
- PB'ye `Origin: https://evil.example` ile istek yapınca `Access-Control-Allow-Origin` header'ı
  yok; izinli origin için var.
- `docker compose up` read_only ve cap_drop ile sağlıklı kalkar.
```

---

## Prompt 8 – MVP.md / TODO.md senkronu (ORTA)

```text
Mevcut durum [kod]: Faz 2 kararları (ENAG, kira endeksi) yalnızca TODO'da; MVP.md eski:
§1 "TÜİK/ENAG TÜFE" (satır 18), §3.4 "Ortalama Ev/Kira katsayısı" (satır 65), §5.4 macro_data
`gold_try` (satır 178; gerçek alanlar gold_try_gram, housing_index, source, is_estimate),
mimari diyagramı "SQLite Storage" (satır 114; artık PocketBase), VaR/CVaR çıktısı ve Faz 2
işaretleri yok. TODO kendi içinde çelişiyor: satır ~78 "[ ] ENAG / Ev-Kira / VaR-CVaR — Faz 2'ye
ertelendi" iken VaR/CVaR "eklendi" deniyor; başlıkta "ruff temiz" ve "Docker build [x]"
iddiaları doğrulanmadı (P3/P5).

Yapılacaklar:
1. MVP.md:
   - §1/§2: "TÜİK TÜFE ve US CPI" (ENAG kapsam dışı / Faz 2: resmî API yok); §3.4: "Gram Altın,
     S&P 500 ve konut fiyat endeksi (EVDS); kira endeksi Faz 2".
   - §5.4: macro_data alanları (gold_try_gram, gold_usd, sp500, tr_cpi, us_cpi, housing_index,
     source, is_estimate); price_history alanları; §5.3 shadow `user` alanı.
   - Mimari diyagramı: SQLite -> PocketBase; VaR/CVaR tanımı (P1) ve ufku; scheduler job'ları
     (expire, refresh_macro, opsiyonel auto_retrospective).
   - "Bilinen sınırlar / Faz 2" bölümü: ENAG, kira endeksi, çok worker'da zamanlayıcı/hız sınırı.
2. TODO.md: tek tutarlı sürüm; test sayısı `pytest --collect-only -q` çıktısıyla aynı; her [x]
   bir test dosyası/adına bağlı; P1-P8 (v5) maddeleri açık olarak listelenip tamamlandıkça
   işaretlensin; "ruff/mypy/docker build temiz" gibi iddialar yalnızca komut çıktısıyla
   birlikte yazılsın (tarih + commit). Çelişen satırları (Faz 2 / VaR) düzelt.
3. README: çalıştırma adımları ile compose değişkenleri (POCKETBASE_PUBLIC_URL,
   PB_ALLOWED_ORIGINS, OPENROUTER_MODELS, ENABLE_SCHEDULER, AUTO_RETROSPECTIVE) tek tabloda.
4. CI'ya doküman tutarlılık adımı: TODO.md içindeki "N/N geçti" ifadesi `pytest --collect-only`
   sayısıyla eşleşmiyorsa uyarı ver.

Kabul kriterleri:
- MVP.md'de yer alan her özellik testli ya da "Faz 2/kapsam dışı" olarak işaretli.
- `grep -n "ENAG\|SQLite Storage\|gold_try\b" MVP.md` yalnızca Faz 2 notlarında/güncel alan
  adlarıyla sonuç verir.
- TODO'daki test sayısı ile gerçek sayı eşit; çelişen madde kalmaz.
```

---

## Prompt 9 – Regresyon test dosyası ve son doğrulama

```text
Aşağıdaki dosyayı tests/test_v5_regressions.py olarak ekle (fixture adlarını mevcut conftest'e
uyarla). Her test ilgili prompt uygulanmadan ÖNCE başarısız olmalı. Fiyat ve geçmiş veri mock'ları
ağ çağrısını engeller; PB gerçektir.
```

```python
"""v5 regresyon testleri: değer doğrulamalı. Her biri ilgili düzeltmeden önce başarısız olmalıdır."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


# --- P1: VaR/CVaR ------------------------------------------------------------------------
def test_compute_var_cvar_direction():
    from services.simulation_service import compute_var_cvar

    finals = np.linspace(0, 200, 10001)
    r = compute_var_cvar(100.0, finals)
    assert r["var_95"] == pytest.approx(90, abs=0.2)
    assert r["var_99"] == pytest.approx(98, abs=0.2)
    assert r["cvar_95"] == pytest.approx(95, abs=0.3)
    assert r["cvar_99"] >= r["var_99"] >= r["var_95"]


@pytest.mark.pb
def test_monte_carlo_var_matches_percentiles(api_client, auth_headers, monkeypatch):
    import services.multi_asset_manager as mam

    rng = np.random.default_rng(1)
    idx = pd.date_range("2023-01-01", periods=300)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, 300)))
    monkeypatch.setattr(mam.AssetManager, "get_price", lambda self, *a, **k: 100.0)
    monkeypatch.setattr(
        mam.AssetManager, "get_historical_data",
        lambda self, *a, **k: pd.DataFrame({"Close": px}, index=idx),
    )
    r = api_client.get("/api/simulation/monte-carlo", headers=auth_headers,
                       params={"assets": "BTC", "simulations": 5000, "days": 126, "seed": 7})
    j = r.json()
    ini, p5 = j["total_initial_value"], j["percentile_values"]["portfolio"]["p5"]
    assert j["risk"]["var_95"] == pytest.approx(ini - p5, abs=1.0)
    assert j["risk"]["cvar_95"] >= j["risk"]["var_95"]


# --- P2: value-series ---------------------------------------------------------------------
@pytest.mark.pb
def test_value_series_has_no_lookahead_or_double_count(make_user, api_client, monkeypatch):
    import services.ledger_service as ls
    import services.multi_asset_manager as mam
    import services.price_service as ps

    def fake_bulk(symbols, asset_types, start_date, end_date, **k):
        out = {s: {} for s in symbols}
        d = start_date
        while d <= end_date:
            for s in symbols:
                out[s][d] = 100.0
            d += timedelta(days=1)
        return out

    monkeypatch.setattr(ps, "get_prices_bulk", fake_bulk, raising=False)
    monkeypatch.setattr(ps, "get_price_on", lambda *a, **k: 100.0, raising=False)
    monkeypatch.setattr(ls, "_get_price_on", lambda *a, **k: 100.0, raising=False)
    monkeypatch.setattr(mam.AssetManager, "get_price", lambda self, *a, **k: 100.0)

    _uid, tok, _c = make_user("v5_series@t.local")
    h = {"Authorization": f"Bearer {tok}"}
    assert api_client.post("/api/transactions", headers=h, json={
        "asset_symbol": "BTC", "tx_type": "BUY", "quantity": 1, "price": 50,
        "timestamp": "2024-02-10"}).status_code == 201
    r = api_client.get("/api/portfolio/value-series", headers=h, params={
        "start_date": "2024-01-01", "end_date": "2024-03-04", "step": "weekly"})
    pts = r.json()["series"]
    values = [(p["date"], p.get("total_value", p.get("value"))) for p in pts]
    for d, v in values:
        assert v == pytest.approx(100.0 if d >= "2024-02-10" else 0.0), values
    # tekil snapshot ile aynı
    for d, v in values:
        s = api_client.get("/api/portfolio/snapshot", headers=h, params={"date": d}).json()
        assert s["total_value"] == pytest.approx(v)


# --- P3: PB Dockerfile -----------------------------------------------------------------------
def test_pb_dockerfile_uses_checksums_txt():
    txt = (ROOT / "docker/pocketbase/Dockerfile").read_text()
    assert "checksums.txt" in txt and ".sha256" not in txt


# --- P4: Chart.js yerel -------------------------------------------------------------------------
def test_chartjs_vendored_and_no_cdn():
    f = ROOT / "web_app/static/vendor/chart.umd.min.js"
    assert f.exists() and f.stat().st_size > 100_000
    for tpl in (ROOT / "web_app/templates").glob("*.html"):
        t = tpl.read_text()
        assert "jsdelivr" not in t and "cdn." not in t, tpl.name


# --- P6: AUTO_RETROSPECTIVE ve housing_index ----------------------------------------------------
def test_auto_retrospective_job_scheduled_when_enabled(monkeypatch):
    import config
    from fastapi.testclient import TestClient

    import api.app as appmod

    monkeypatch.setattr(config, "AUTO_RETROSPECTIVE", True)
    with TestClient(appmod.app):
        if appmod._scheduler is None:
            pytest.skip("scheduler kapalı")
        assert appmod._scheduler.get_job("auto_retrospective") is not None


@pytest.mark.pb
def test_housing_index_is_number(pb_admin):
    col = pb_admin.collections.get_one("macro_data")
    f = {x["name"]: x["type"] for x in col.fields}
    assert f["housing_index"] == "number"
    r = pb_admin.collection("macro_data").create(
        {"date": "2019-01-01 00:00:00.000Z", "housing_index": 123.4})
    assert isinstance(r.housing_index, float) and r.housing_index == pytest.approx(123.4)


# --- P7: hata semantiği ---------------------------------------------------------------------------
@pytest.mark.pb
def test_foreign_transaction_id_is_not_500(make_user, api_client):
    _a, ta, _ = make_user("v5_a@t.local")
    _b, tb, _ = make_user("v5_b@t.local")
    ha, hb = {"Authorization": f"Bearer {ta}"}, {"Authorization": f"Bearer {tb}"}
    tx = api_client.post("/api/transactions", headers=ha, json={
        "asset_symbol": "BTC", "tx_type": "BUY", "quantity": 1, "price": 10}).json()
    r = api_client.post("/api/decisions", headers=hb, json={
        "asset_symbol": "BTC", "action": "BUY", "sentiment": "FOMO", "transaction_id": tx["id"]})
    assert r.status_code in (404, 422)


@pytest.mark.pb
def test_internal_errors_do_not_leak(api_client, auth_headers, monkeypatch):
    import api.app as appmod

    def boom(*a, **k):
        raise RuntimeError("secret-internal-detail")

    monkeypatch.setattr(appmod, "svc_list_decisions", boom, raising=False)
    r = api_client.get("/api/decisions", headers=auth_headers)
    assert r.status_code == 500 and "secret-internal-detail" not in r.text


def test_no_str_e_in_http_exceptions():
    src = (ROOT / "api/app.py").read_text()
    assert "HTTPException(500, str(e))" not in src
```

```text
Not: Fonksiyon/değişken adları (compute_var_cvar, svc_list_decisions, _scheduler) bu dosyada
varsayım; mevcut koda göre uyarla. Gerçek PB gerektiren testler `pytest -m pb` ile çalışır.
```

---

## Son doğrulama listesi (tüm promptlar bitince)

```text
1. `pytest -q` yeşil (113 + yeni testler); `ruff check .`, `ruff format --check .` ve mypy
   hatasız; CI güncel HEAD'de yeşil (run bağlantısı TODO'da).
2. VaR/CVaR: bilinen dağılımda beklenen değerler; monte-carlo çıktısında var_95 ≈ initial - p5.
3. value-series: alım öncesi 0, sonrası doğru miktar; tüm tarihlerde tekil snapshot ile birebir eşit.
4. `docker compose up --build` sıfırdan çalışır (PB imajı dahil); /health `pb: ok`;
   konteynerler root değil, read_only/cap_drop ile sağlıklı.
5. Tarayıcı: giriş -> dashboard -> grafikler çizilir; konsolda CSP/JS hatası yok.
6. AUTO_RETROSPECTIVE açıkken EXPIRED karar için AI retrospektifi üretilir, kapalıyken job yok.
7. macro_data.housing_index number alanı; eski veri migration ile korunmuş.
8. Hata yanıtlarında iç istisna metni yok; yabancı transaction_id 404/422; PB CORS yalnızca izinli origin.
9. MVP.md ve TODO.md gerçek durumla örtüşür; çelişen satır ve doğrulanmamış iddia kalmaz.
```
