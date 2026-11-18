# FutureWallet – Düzeltme Promptları v4 (son duruma göre)

Dayanak: repo `ertugerata/futureWallet_new`, commit **`2a4aca7`**; MVP.md v2.0 ve TODO.md (v5).
Bu dosya v3'ün yerine geçer. v3'teki P0–P15'in işlevsel kısmı büyük ölçüde tamamlandı: `import api.app` temiz, `ruff` temiz, **101/101 test gerçek PocketBase 0.40.6 ile geçiyor** (bağımsız doğrulandı). v4, testlerin kapsamadığı kalan sorunları kapatır: dağıtım, PB'nin doğrudan API'si, zamanlayıcı, AI ve dış servisler, DoS, MVP kapsamı.

Kanıt işaretleri: **[probe]** gerçek PB'ye karşı ek testle doğrulandı. **[ölçüm]** çalıştırılıp ölçüldü. **[kod]** kod okuması (Docker çalıştırılmadı).

## A. Öncelik tablosu

| # | Konu | Seviye | Kanıt |
|---|------|--------|-------|
| 0 | Ortak kurallar | – | – |
| 1 | Docker Compose: bind adresi, genel PB URL'si, root, .dockerignore, PB imajı | Yüksek | kod |
| 2 | Zamanlayıcı: ilk çalışma 24 saat sonra | Yüksek | probe |
| 3 | PB kuralları: değişmezlik, sistem alanları, rate limit | Yüksek | probe |
| 4 | AI: güncel modeller, hız sınırı, hata sızıntısı | Yüksek | kod + kaynak |
| 5 | value-series DoS ve N+1 | Orta | ölçüm |
| 6 | CSP, /health, ölü kod, küçük sertleştirmeler | Orta | kod |
| 7 | MVP kapsam kararı ve doküman senkronu | Orta | kod |
| 8 | Probe testlerini kalıcı regresyon testine çevir, son doğrulama | – | – |

Sıra bağımlılık gözetilerek verildi; P8'deki testler her prompt bitince çalıştırılmalı.

---

## Prompt 0 – Ortak kurallar (her promptun başına ekleyin)

```text
Proje: FutureWallet. Mimari: PocketBase v0.40.6 (DB + Auth) + FastAPI (hesaplama) + OpenRouter (LLM).
Referanslar: MVP.md, TODO.md. SDK: pocketbase==0.17.3 (SENKRON; get_list(page, per_page,
query_params), update(id, body), client.filter(raw, params); `params=` kwarg ve RecordService.get YOK).

Kurallar:
- Yalnızca istenen kapsamı değiştir; mevcut 101 test yeşil kalmalı (`pytest -q`).
- PB'ye dokunan davranışları GERÇEK PocketBase'e karşı test et (tests/conftest.py fixture'ları:
  pb_server, make_user, api_client, auth_headers, pb_admin). PB'yi mock'lama.
- Her düzeltme için, düzeltmeden ÖNCE başarısız olan bir regresyon testi ekle (P8'deki probe
  testlerinden başla).
- Sır/anahtar/parola koda, loga, hata gövdesine, git'e, Docker imajına yazma.
- Bitirince: değişen dosyalar + her kabul kriterinin nasıl doğrulandığı + TODO.md'de yalnızca
  testle kanıtlanan maddeleri [x] yap. Docker'a dokunan adımlarda `docker compose up --build`
  ile uçtan uca duman testini (login -> dashboard) elle de çalıştır.
```

---

## Prompt 1 – Docker Compose, PB imajı, build context (YÜKSEK)

```text
Mevcut durum [kod]:
(a) docker-compose.yml uygulamayı konteyner içinde APP_HOST=127.0.0.1 ile başlatıyor (Dockerfile
    CMD de bu değişkeni kullanıyor) ve portu "127.0.0.1:8000:8000" yayınlıyor. Konteyner yalnızca
    kendi loopback'inde dinlediği için host'tan erişilemez.
(b) web_app/__init__.py giriş/dashboard şablonlarına `pb_base = config.POCKETBASE_URL` veriyor;
    compose'ta bu `http://pocketbase:8090` (iç ağ adı). Tarayıcı çözemez -> giriş başarısız.
    CSP connect-src de aynı adresten üretiliyor (api/app.py `_add_security_headers`).
(c) compose'ta `user: root` Dockerfile'daki `USER app`'i eziyor.
(d) .dockerignore: `*.db` yalnızca kök dizini eşler; pb_data/, pb_bin/, pb_test_data*/, tests/,
    docs/, graphify-out/ build context'ine girer; Dockerfile `COPY . .` yaptığı için yerelde PB
    çalıştırılmışsa superuser hash'i ve kullanıcı verisi imaja girebilir.
(e) docker/pocketbase/Dockerfile: `alpine:3.19` (desteği bitmiş olabilir, doğrula), indirilen
    zip için checksum doğrulaması yok, `chmod 777 /pb_data`, kullanılmayan ./pb_data dizini;
    compose'ta `PB_REMOTE_ADDR` PB'nin tanıdığı bir ayar değil (etkisiz); entrypoint superuser
    parolasını komut satırı argümanı olarak veriyor.
(f) PB varsayılan CORS'u tüm origin'lere açıktır; --origins ile sınırlanmalı (flag'i doğrula).

Yapılacaklar:
1. APP_HOST: Dockerfile varsayılanı ve compose'ta konteyner içi `0.0.0.0`; ana makineye yayın
   `127.0.0.1:8000:8000` olarak kalsın (dışarıya açılmasın). README'ye "dışarı açmak için ters
   proxy + TLS" notu ekle.
2. Yeni config: PUBLIC_POCKETBASE_URL (tarayıcının erişeceği adres; varsayılan
   http://localhost:8080). POCKETBASE_URL yalnızca sunucu->PB iç trafiği için. Şablonlara
   (`pb_base`) ve CSP connect-src'e PUBLIC_POCKETBASE_URL verilir; compose'a değişken eklenir.
3. compose: `user: root` satırını kaldır; `PB_REMOTE_ADDR` kaldır; PB'ye `--origins` ile
   yalnızca uygulamanın genel origin'ini ver (örn. http://localhost:8000); app servisine
   `read_only: true` + `tmpfs: /tmp` ve `cap_drop: [ALL]` ekle (çalışıyorsa).
4. .dockerignore: pb_data/, pb_bin/, pb_test_data*/, **/*.db, **/*.sqlite*, tests/, docs/,
   graphify-out/, .pytest_cache/, .ruff_cache/, .mypy_cache/, .github/, *.md (README.md hariç),
   docker-compose*.yml. Böylece yerel PB verisi imaja giremez.
5. PB Dockerfile: güncel destekli Alpine sürümüne geç (sabit etiket), release'in
   checksums dosyasıyla sha256 doğrulaması yap (indirme `curl -fsSL`), `chmod 777` yerine
   `chown pbuser`, kullanılmayan dizini sil. Superuser parolasını komut satırı yerine dosya/Docker
   secret'tan okuyan bir adım kullan (mümkün değilse risk README'de belirtilsin).
6. İki servis için healthcheck'i doğrula; app sağlıklı olmadan PB bağımlılığı sağlanmış olsun.

Kabul kriterleri:
- `docker compose up --build` sonrası host'tan `curl http://127.0.0.1:8000/health` 200 döner.
- Tarayıcıdan http://localhost:8000/web/login ile giriş çalışır (PB'ye http://localhost:8080
  üzerinden); sayfadaki meta pb-base genel adrestir, `pocketbase:8090` içermez.
- `docker compose exec futurewallet id -u` 0 değil.
- `docker build` bağlamında `pb_data` yoksa imajda yoktur: `docker run --rm <img> ls /app` çıktısında
  pb_data/pb_bin/tests/docs görünmez.
- Statik test (P8): compose'ta APP_HOST=0.0.0.0, `user: root` yok, PUBLIC_POCKETBASE_URL tanımlı;
  .dockerignore pb_data içerir.
```

---

## Prompt 2 – Zamanlayıcı (YÜKSEK)

```text
Mevcut durum [probe]: api/app.py lifespan'da `expire_decisions` ve `refresh_macro` job'ları
`interval, hours=24` ile ekleniyor; APScheduler'da ilk çalışma başlangıçtan 24.0 saat sonradır.
Uygulama günlük yeniden başlarsa job'lar hiç çalışmaz. Testler job fonksiyonunu doğrudan
çağırdığı için bu hata görünmüyor. Ayrıca çok worker'da (WEB_CONCURRENCY>1) job'lar çoğalır.

Yapılacaklar:
1. Job'lar: başlangıçtan ~30 sn sonra ilk çalışma (next_run_time) + ardından günlük
   (cron 03:00 yerel saat önerilir); `coalesce=True`, `max_instances=1`, `misfire_grace_time`.
2. Job sarmalayıcıları try/except ile loglasın (şu an makro job'ı yapıyor; expire job'ı da
   aynısını yapsın), uygulamayı düşürmesin; başarı/hata sayısını loga yaz.
3. Çok worker koruması: yalnızca `SCHEDULER_LEADER=true` olan tek süreçte ya da
   WEB_CONCURRENCY==1 ise başlat; aksi hâlde uyarı logla. README'de "tek worker" şartını yaz.
4. İsteğe bağlı: `/api/admin/jobs` yok; bunun yerine superuser ile elle tetikleme için
   `scripts/run_jobs_once.py` ekle.

Kabul kriterleri:
- Test: `with TestClient(app)` içinde `api.app._scheduler.get_job("expire_decisions").next_run_time`
  şimdi + 60 sn içinde; "refresh_macro" için de aynı.
- Test: vadesi geçmiş OPEN karar, ilk job tetiklemesinden sonra EXPIRED + outcome dolu
  (job'ı zamanı beklemeden `modify(next_run_time=now)` ile çalıştır).
- ENABLE_SCHEDULER=false iken job eklenmez.
```

---

## Prompt 3 – PB kuralları: değişmezlik, sistem alanları, rate limit (YÜKSEK)

```text
Mevcut durum [probe, gerçek PB]: giriş doğrudan PB'ye yapıldığı için PB REST API'si kullanıcıya
açık ve migration kuralları iş kurallarını zorlamıyor. Kullanıcı kendi verisi üzerinde şunları
yapabildi:
- elde olmayan SELL işlemi oluşturma (FastAPI'deki 409 atlanıyor),
- işlemin quantity/price alanını UPDATE,
- işlemi HARD DELETE,
- status=REVIEWED + sahte ai_retrospective ile karar oluşturma,
- başka kullanıcının karar id'sine shadow bağlama (id tahmin edilemez; düşük risk).
Ayrıca PB yerleşik rate limiter KAPALI (`rateLimits.enabled=False`): auth-with-password sınırsız
denenebilir. Diğer kullanıcıların verisine erişim YOK (izolasyon sağlam).
Kural biçimi (v0.40.6): migration JS dosyaları pb_migrations/ altında.

Karar: ledger bütünlüğü (MVP §3.1 event-sourcing) için kullanıcı YAZIMI FastAPI üzerinden
yapılsın; kullanıcı token'ı yalnızca OKUMA için kullanılsın.

Yapılacaklar:
1. Yeni migration(lar) (mevcutları düzenleme, yenisini ekle):
   transactions: createRule = null, updateRule = null, deleteRule = null
     (kullanıcı PB'den doğrudan yazamaz/silemez; list/view kuralları aynı kalır).
   decisions: createRule = null; updateRule = null; deleteRule = null.
   shadow_portfolios: createRule = null; updateRule = null; deleteRule = null.
   (Sadece list/view `user = @request.auth.id` kalır.)
2. FastAPI yazma yolu: services/pb.py'ye `get_admin_client()` ile çalışan YAZMA yardımcıları ekle;
   tüm create/update/delete işlemlerinde `user` alanı CurrentUser.id'den ZORLA atanır ve
   güncelleme/silme öncesi sahiplik doğrulanır (kayıt `user == current_user.id` değilse 404).
   Okuma yolu user-scoped client'ta kalır. Servis imzaları: yazma fonksiyonları current_user
   alır (kullanıcı id'sini dışarıdan değil CurrentUser'dan).
3. Kullanıcı tarafından düzenlenebilir karar alanları (PUT /api/decisions/{id}): rationale,
   sentiment, target_price, target_date. Sistem alanları (status, ai_retrospective,
   outcome_price, outcome_return_pct, target_hit) yalnızca ilgili sistem endpoint'lerinden
   (close, evaluate, retrospective, zamanlayıcı) yazılır; PUT bu alanları reddeder/yok sayar.
4. decisions.transaction ve shadow_portfolios.decision ilişkilerinde, ilişkilendirilen kaydın
   çağıran kullanıcıya ait olduğu FastAPI tarafında doğrulansın (başkasının id'si -> 404/422).
5. PB rate limiter: yeni bir JS migration ile settings.rateLimits.enabled = true yap
   (varsayılan kurallar: `*:auth` için düşük sınır zaten tanımlı; doğrula ve uygun değerleri
   ayarla). Migration sözdizimini PB 0.40.6'da çalıştırarak doğrula.
6. users koleksiyonu: e-posta doğrulama/MFA gereksinimini MVP kapsamına göre karara bağla
   (en az: min. parola uzunluğu 10, authAlert açık); kararı MVP.md'ye yaz.

Kabul kriterleri (gerçek PB, bu testler düzeltmeden önce BAŞARISIZ olmalı; P8'de kod var):
- Kullanıcı token'ıyla PB'ye doğrudan transactions/decisions/shadow create/update/delete -> 403/404.
- FastAPI üzerinden işlem ekleme/void/karar oluşturma/silme eskisi gibi çalışır (101 test yeşil).
- PUT /api/decisions/{id} ile {"status":"REVIEWED","ai_retrospective":"x"} gönderilince bu
  alanlar değişmez.
- Başkasının transaction/decision id'siyle karar/shadow oluşturma -> 404/422.
- `pb_admin.settings.get_all()["rateLimits"]["enabled"]` True; art arda 10 hatalı giriş sonrası PB 429 döner.
```

---

## Prompt 4 – AI: güncel modeller, hız sınırı, hata sızıntısı (YÜKSEK)

```text
Mevcut durum:
(a) [kod + kaynak] Varsayılan model listesi `anthropic/claude-3.5-sonnet,google/gemini-2.0-flash-001,
    deepseek/deepseek-r1` üç yerde sabit (config.py, docker-compose.yml, .env.example) ve MVP §6'da
    yazılı. Anthropic'in kendi tablosuna göre claude-3-5-sonnet-20241022 22 Ekim 2025'te emekliye
    ayrıldı; diğer ikisinin güncelliği doğrulanmadı. Birincil model yoksa her istek fallback'e
    düşer, hepsi giderse retrospektif/narrative 502 verir.
(b) [kod] `/api/simulation/narrative` için hız sınırı yok; retrospektif yalnızca KARAR başına
    60 sn sınırlı, kullanıcı başına toplam sınır yok. Her istek 3 modele kadar fallback yapabilir
    (ücretli çağrı kötüye kullanımı).
(c) [kod] AIGenerationError mesajı OpenRouter yanıt gövdesini (`resp.text`) içeriyor ve endpoint'ler
    `HTTPException(502, str(e))` ile istemciye dönüyor; benchmarks/stress-test/narrative de
    `500, str(e)` dönüyor (iç hata sızıntısı).
(d) [kod] `config.OPENROUTER_MODELS` env boş bırakılırsa varsayılanı ezer (os.environ.get(K, default)).

Yapılacaklar:
1. Model yapılandırması: koddaki/compose'taki/.env.example'daki sabit varsayılanları KALDIR.
   OPENROUTER_MODELS verilmemişse ve anahtar varsa açılışta net hata/uyarı; verilmişse açılışta
   (opsiyonel, 3 sn timeout, hata fatal değil) OpenRouter /models listesiyle doğrula ve listede
   olmayanları WARNING olarak logla. Güncel model adlarını openrouter.ai/models'ten seçip
   README'de "örnek" olarak göster (sabit varsayılan olarak değil). MVP §6'daki model adlarını
   "örnek, env ile ayarlanır" olarak güncelle. `os.environ.get(K) or default` kalıbını kullan.
2. Hız sınırı (kullanıcı kimliğine göre, sınıfa kapsüllü, testte sıfırlanabilir):
   retrospective: dakikada 5 ve günde 30 (kullanıcı başına; mevcut karar başına 60 sn kuralı
   kalsın); narrative: dakikada 5 ve günde 30; sınır aşımı 429 + Retry-After. Günlük sınırlar
   env ile ayarlanabilir (AI_DAILY_LIMIT_PER_USER). Çok worker notu README'de.
3. Hata gövdesi sızıntısını kapat: AIGenerationError'a iki alan ver (public_message: genel metin,
   detail: loglanacak, anahtar/URL içermeyen, 300 karaktere kırpılmış). İstemciye yalnızca
   genel mesaj: 502 "AI sağlayıcısı geçici olarak yanıt vermedi", 503 "AI yapılandırılmamış".
   benchmarks/stress-test/narrative'deki `500, str(e)` çağrılarını genel mesaja çevir ve
   ayrıntıyı logla (exception handler ile tek yerde).
4. Narrative girdisi: `simulation_result`/`portfolio_context` boyutu (örn. 16 KB) ve derinlik
   sınırı; prompt'a girmeden önce <user_input> sarmalayıcısıyla ve etiket kaçırmayla (mevcut
   sanitizer) geçsin.
5. İsteğe bağlı (MVP "vade sonunda AI retrospektifi"): AUTO_RETROSPECTIVE=false varsayılanlı bir
   zamanlayıcı adımı ekle; açıkken yalnızca EXPIRED ve henüz retrospektifi olmayan kararlar için,
   kullanıcı başına günlük sınıra uyarak üretir (P7 ile birlikte karar).

Kabul kriterleri (OpenRouter HTTP mock'lı):
- Mock'lanmış OpenRouter 500 yanıtı `{"secret":"sk-or-test-123"}` içerirse API yanıt gövdesinde bu
  metin ve "OpenRouter hatası" ayrıntısı YOK; log'da anahtar yok.
- 6. ardışık narrative çağrısı (1 dk içinde) 429; farklı kullanıcının sayacı bağımsız.
- OPENROUTER_MODELS="" iken varsayılan listeye değil açık hataya/uyarıya düşer; listede olmayan
  model adı açılışta WARNING üretir.
- retrospective günlük sınırı aşılınca 429; sınır sıfırlanabilir (test).
```

---

## Prompt 5 – value-series DoS ve N+1 (ORTA)

```text
Mevcut durum [ölçüm]: api/app.py `portfolio_value_series` önce `while` döngüsüyle tüm tarih listesini
üretiyor, 400 nokta sınırını SONRA kontrol ediyor. start=0001-01-01, end=9999-12-31, step=daily ->
~3,65 milyon tarih, ~9 sn, ~148 MB, sonunda date.max taşması (OverflowError, HTTP 500).
Ayrıca her nokta için ayrı snapshot (PB işlem sorgusu + fiyat sorgusu: N+1) ve hız sınırı yok.

Yapılacaklar:
1. Nokta sayısını döngüden ÖNCE aritmetikle hesapla (daily: gün farkı+1; weekly: gün farkı//7+1;
   monthly: ay farkı+1); >400 ise 422. Ayrıca aralık üst sınırı (örn. 20 yıl) ve start>=1900.
   OverflowError/ValueError -> 422. step için Literal["daily","weekly","monthly"] doğrulaması.
2. N+1'i kaldır: `get_portfolio_snapshots(user_id, dates)` toplu fonksiyonu: işlemleri BİR KEZ
   get_full_list ile çek, tarih başına holdings'i bellekte hesapla; fiyatları price_service ile
   sembol başına TEK aralık çekimiyle (tarih aralığı + cache) al. Eski tekil snapshot davranışı
   aynı sonuçları vermeli (golden test).
3. Aynı kullanıcı için value-series çağrılarına hız sınırı (örn. dakikada 10) ve kısa TTL cache
   (aynı parametreler 30 sn).
4. benzer sınırlar: `/api/portfolio/benchmarks`, `/real-valuation` tarih aralığı doğrulaması
   (start<=end, makul sınır).

Kabul kriterleri:
- 0001-01-01..9999-12-31 isteği 1 sn altında 422 (500 değil), bellek artışı ihmal edilebilir.
- 400 noktalık haftalık seri için PB istek sayısı sabit (işlem listesi tek sorgu; sembol başına
  fiyat çekimi tek) — PB istek sayacı/log ile test et.
- Toplu snapshot sonuçları tekil `get_portfolio_snapshot` sonuçlarıyla eşleşir.
- 11. ardışık çağrı 429.
```

---

## Prompt 6 – CSP, /health, ölü kod, küçük sertleştirmeler (ORTA)

```text
Mevcut durum [kod]:
- CSP script-src `https://cdn.jsdelivr.net` host'unun tamamına izin veriyor (SRI yalnızca ilgili
  etiketi korur; jsDelivr herkesin yayımladığı paketleri sunar). frame-ancestors, form-action,
  X-Frame-Options, Permissions-Policy yok; API yanıtlarında Cache-Control yok.
- /health yalnızca önbellekteki admin token'ın geçerliliğine bakıyor: PB düşse de token süresi
  dolana kadar `pb: ok` dönebilir.
- api/app.py `_init_pocketbase` PB'yi `pocketbase migrate` ile (--dir vermeden, yanlış veri
  dizininde) çalıştırmaya çalışıyor; Docker'da çalışmaz, dağınık/ölü kod.
- services/ledger_service.py `_user_locks` (defaultdict(Lock)) hiç temizlenmiyor (kullanıcı sayısıyla büyür).
- Sentiment/aksiyon Literal listeleri api/app.py'de birkaç yerde kopyalanmış; services/enums.py ile
  tek kaynak değil.
- EVDS anahtarı sorgu parametresi (key=) olarak gönderiliyor; EVDS'nin güncel kimlik doğrulama
  biçimi (başlık/parametre) doğrulanmadı.

Yapılacaklar:
1. Chart.js'i sürüm sabitli olarak web_app/static/vendor/ altına koy (lisans notuyla), şablondan
   CDN etiketini kaldır, CSP'yi `script-src 'self'` yap. Ek başlıklar: `frame-ancestors 'none'`,
   `form-action 'self'`, `X-Frame-Options: DENY`, `Permissions-Policy` (kamera/mikrofon/konum kapalı),
   HTTPS arkasında `Strict-Transport-Security` (env: ENABLE_HSTS), /api/* için
   `Cache-Control: no-store`.
2. /health: PB'ye gerçek kısa istek (`GET {POCKETBASE_URL}/api/health`, 2 sn timeout); PB kapalıysa
   `pb: "down"` (HTTP 200 kalsın ama konteyner healthcheck'i pb down'da başarısız sayılabilir) ve
   ayrıntı vermesin.
3. `_init_pocketbase` içindeki subprocess/migrate kısmını sil: yalnızca koleksiyon/alan doğrulaması
   (verify_collections) ve eksikse açık hata. Migration'lar PB konteynerinin entrypoint'inde zaten
   uygulanıyor.
4. `_user_locks`: sınırlı bir yapı (LRU ya da WeakValueDictionary) kullan; testle büyümediğini doğrula.
5. Enum tekilleştirme: Literal'leri services/enums.py'den türet (`Literal[*...]` veya Enum + Pydantic).
6. EVDS: resmî dokümana göre anahtarın nasıl gönderilmesi gerektiğini doğrula (başlık/parametre),
   fixture ile ayrıştırmayı test et; anahtar yokken "veri yok" davranışı korunsun.

Kabul kriterleri:
- `/web/` HTML'inde ve CSP başlığında "jsdelivr" yok; Chart.js /static/vendor'dan yükleniyor ve
  dashboard grafikleri çalışıyor (tarayıcı duman testi, konsolda CSP ihlali yok).
- PB süreci durdurulunca /health `pb: down` döner (admin token geçerli olsa bile).
- 100.000 farklı user_id ile ledger kilidi alındıktan sonra kilit sözlüğü sınırı aşmaz.
- grep: app.py'de sentiment/aksiyon değer listesi tek kaynaktan.
```

---

## Prompt 7 – MVP kapsam kararı ve doküman senkronu (ORTA)

```text
Kod ile MVP.md/TODO.md arasındaki farklar [kod]:
1. MVP §1/§2 "TÜİK/ENAG TÜFE": ENAG yok. ENAG'ın resmî bir API'si olmadığından kapsam kararı gerekir.
2. MVP §3.4 "Ortalama Ev/Kira katsayısı": kodda yok.
3. MVP mimari diyagramı "Monte Carlo & VaR": VaR/CVaR hesaplanmıyor.
4. MVP §3.2 "Vade sonunda AI retrospektifi": yalnızca elle tetikleniyor (P4 adım 5 isteğe bağlı otomasyon).
5. MVP §5.4 macro_data alanları `gold_try` diyor; migration `gold_try_gram` (+ source, is_estimate);
   price_history alanları MVP'de hiç tanımlı değil.
6. MVP §5.3 shadow_portfolios'ta `user` alanı yok; şemada zorunlu.
7. TODO.md: başlık "101/101", Hızlı Kontrol "100/100"; Prompt 10 ve 15 başlıkları 🟡 ama içerikleri
   ✅; Prompt 15 "dokümanlar v4", başlık v5; CI kanıtı (run/commit) güncel HEAD'den eski.
8. Repo kökünde eski prompt dosyaları (FUTUREWALLET_DUZELTME_PROMPTLARI*.md) geçerli plan gibi duruyor.

Yapılacaklar:
1. Kapsam kararlarını MVP.md'ye açıkça yaz:
   - ENAG: kapsam dışı (Faz 2) veya kullanıcı yüklemeli opsiyonel seri; "TÜİK TÜFE ve US CPI" olarak
     düzelt.
   - Ev/Kira: ya Faz 2'ye ertele ya da EVDS konut fiyat endeksi serisiyle uygula (seri kodunu
     doğrula, macro_data'ya `housing_index` alanı ekle, benchmarks çıktısına katsayı ekle).
   - VaR/CVaR: uygula — Monte Carlo dağılımından VaR(95/99) = başlangıç − p5/p1 ve CVaR = kuyruk
     ortalaması; /monte-carlo yanıtına `risk: {var_95, var_99, cvar_95, cvar_99}`, UI'da kart.
2. MVP.md §5'i migration'larla birebir eşitle: macro_data (`gold_try_gram`, `source`, `is_estimate`),
   price_history alanları, shadow `user`, P3'te değişen yazma kuralları; §6 model adlarını
   "örnek / env" yap (P4).
3. TODO.md'yi tek tutarlı sürüme getir: test sayısı, başlık durumları, v numaraları; her [x] bir test
   dosyası/adına bağlı; "CI yeşil" ifadesi güncel HEAD için gerçek bir run'a bağlansın. Eski
   FUTUREWALLET_DUZELTME_PROMPTLARI*.md dosyalarını docs/archive/ altına taşı ("geçersiz" notu).
4. SPRINT_PLANI_KALANLAR.md ve GUNCEL_IS_PLANI.md varsa TODO.md ile birleştir (tek plan dosyası).

Kabul kriterleri:
- MVP.md'de yer alan her özellik ya kodda test edilmiş ya da "kapsam dışı/Faz 2" olarak işaretli.
- VaR/CVaR için birim test: bilinen dağılımda (örn. sabit seed) p5 ve kuyruk ortalaması doğru.
- Doküman tutarlılık testi/CI adımı: TODO'daki test sayısı pytest --collect-only sonucuyla eşit.
```

---

## Prompt 8 – Probe testlerini kalıcı regresyon testine çevir

```text
Aşağıdaki dosyayı tests/test_hardening.py olarak ekle (gerekirse fixture adlarını mevcut
conftest'e uyarla). Her test ilgili prompt uygulanmadan ÖNCE başarısız olmalı. Doğrudan PB
çağrıları için `make_user` fixture'ının döndürdüğü user-scoped client kullanılır.
```

```python
"""Sertleştirme regresyon testleri (v4). Her biri ilgili düzeltmeden önce başarısız olmalıdır."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml  # pyyaml (dev bağımlılığı)

ROOT = Path(__file__).resolve().parents[1]


def _raises(fn) -> bool:
    try:
        fn()
    except Exception:
        return True
    return False


# --- P3: PB doğrudan yazma kapalı ------------------------------------------------------
@pytest.mark.pb
def test_pb_direct_writes_blocked(make_user):
    uid, _tok, client = make_user("hard_a@t.local")
    assert _raises(lambda: client.collection("transactions").create({
        "user": uid, "asset_symbol": "BTC", "type": "SELL", "quantity": 999, "price": 1,
        "fee": 0, "timestamp": "2024-01-01 00:00:00.000Z", "voided": False}))
    assert _raises(lambda: client.collection("decisions").create({
        "user": uid, "asset_symbol": "BTC", "action": "BUY", "sentiment": "FOMO",
        "status": "REVIEWED", "ai_retrospective": "SAHTE",
        "decision_date": "2024-01-01 00:00:00.000Z"}))


@pytest.mark.pb
def test_pb_existing_records_immutable(make_user, api_client):
    uid, tok, client = make_user("hard_b@t.local")
    h = {"Authorization": f"Bearer {tok}"}
    r = api_client.post("/api/transactions", headers=h, json={
        "asset_symbol": "BTC", "tx_type": "BUY", "quantity": 1, "price": 10})
    assert r.status_code == 201
    tid = r.json()["id"]
    assert _raises(lambda: client.collection("transactions").update(tid, {"quantity": 5}))
    assert _raises(lambda: client.collection("transactions").delete(tid))


@pytest.mark.pb
def test_put_decision_cannot_set_system_fields(make_user, api_client):
    uid, tok, _ = make_user("hard_c@t.local")
    h = {"Authorization": f"Bearer {tok}"}
    d = api_client.post("/api/decisions", headers=h, json={
        "asset_symbol": "BTC", "action": "BUY", "sentiment": "FOMO"}).json()
    api_client.put(f"/api/decisions/{d['id']}", headers=h, json={
        "status": "REVIEWED", "ai_retrospective": "x"})
    after = api_client.get(f"/api/decisions/{d['id']}", headers=h).json()
    assert after["status"] == "OPEN" and not after.get("ai_retrospective")


@pytest.mark.pb
def test_pb_rate_limiter_enabled(pb_admin):
    st = pb_admin.settings.get_all()
    assert st["rateLimits"]["enabled"] is True


# --- P5: value-series DoS ---------------------------------------------------------------
@pytest.mark.pb
def test_value_series_huge_range_rejected_fast(api_client, auth_headers):
    t0 = time.time()
    r = api_client.get("/api/portfolio/value-series", headers=auth_headers, params={
        "start_date": "0001-01-01", "end_date": "9999-12-31", "step": "daily"})
    assert r.status_code == 422 and time.time() - t0 < 1.0


# --- P2: zamanlayıcı ilk çalışma ------------------------------------------------------------
def test_scheduler_first_run_soon():
    from fastapi.testclient import TestClient

    import api.app as appmod
    with TestClient(appmod.app):
        if appmod._scheduler is None:
            pytest.skip("scheduler kapalı")
        from datetime import datetime, timezone
        for jid in ("expire_decisions", "refresh_macro"):
            nrt = appmod._scheduler.get_job(jid).next_run_time
            assert (nrt - datetime.now(timezone.utc)).total_seconds() < 120


# --- P4: AI hız sınırı ve hata sızıntısı ------------------------------------------------------
@pytest.mark.pb
def test_narrative_rate_limited(api_client, auth_headers, monkeypatch):
    import api.app as appmod
    monkeypatch.setattr(appmod, "srv_generate_risk_narrative", lambda **k: "ok")
    codes = [api_client.post("/api/simulation/narrative", headers=auth_headers, json={}).status_code
             for _ in range(8)]
    assert 429 in codes


@pytest.mark.pb
def test_ai_error_does_not_leak_provider_body(api_client, auth_headers, monkeypatch):
    import api.app as appmod
    from services.ai_service import AIGenerationError

    def boom(**k):
        raise AIGenerationError("OpenRouter hatası: HTTP 500 - {'secret':'sk-or-test-123'}")
    monkeypatch.setattr(appmod, "srv_generate_risk_narrative", boom)
    r = api_client.post("/api/simulation/narrative", headers=auth_headers, json={})
    assert r.status_code == 502 and "sk-or-test-123" not in r.text and "OpenRouter" not in r.text


# --- P6: başlıklar ---------------------------------------------------------------------------
def test_csp_hardened(api_client):
    r = api_client.get("/web/login")
    csp = r.headers["content-security-policy"]
    assert "jsdelivr" not in csp and "frame-ancestors 'none'" in csp
    assert r.headers.get("x-frame-options") == "DENY"


# --- P1: dağıtım dosyaları (statik) ----------------------------------------------------------
def test_compose_and_dockerignore():
    comp = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    app = comp["services"]["futurewallet"]
    env = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in app["environment"] if "=" in e}
    assert env.get("APP_HOST") == "0.0.0.0"
    assert app.get("user") != "root"
    assert "PUBLIC_POCKETBASE_URL" in env
    ign = (ROOT / ".dockerignore").read_text()
    for needle in ("pb_data", "pb_bin", "pb_test_data", "tests", "docs"):
        assert needle in ign


def test_login_meta_uses_public_pb_url(api_client, monkeypatch):
    import config
    monkeypatch.setattr(config, "PUBLIC_POCKETBASE_URL", "http://localhost:8080", raising=False)
    html = api_client.get("/web/login").text
    assert 'content="http://localhost:8080"' in html and "pocketbase:8090" not in html
```

```text
Not: yaml için `pyyaml`ı requirements-dev.in'e ekle. Testler gerçek PB'ye karşı çalışır
(`pytest -m pb`); P2 testi scheduler'ı gerçekten başlatmak için ENABLE_SCHEDULER=true gerektirir
(conftest'te ayarla). P3'ten sonra FastAPI yazma yolu admin client kullandığı için 101 mevcut
test yeşil kalmalıdır; kalmıyorsa servis imzalarını P3 adım 2'ye göre güncelle.
```

---

## Son doğrulama listesi (tüm promptlar bitince)

```text
1. `docker compose up --build`: host'tan /health 200; tarayıcıdan giriş -> dashboard çalışır;
   konteyner root değil; imajda pb_data/tests/docs yok.
2. İki kullanıcı: PB'ye doğrudan yazma/silme/güncelleme reddedilir; FastAPI yolu çalışır;
   başkasının verisine hiçbir yoldan erişilemez.
3. Zamanlayıcı job'ları başlangıçtan <2 dk içinde ilk kez çalışır; EXPIRED akışı uçtan uca çalışır.
4. PB rate limiter etkin; art arda hatalı girişte 429.
5. AI: model listesi güncel ve açılışta doğrulanıyor; hız sınırı çalışıyor; hata gövdelerinde
   sağlayıcı yanıtı/anahtar yok.
6. value-series: aşırı aralık <1 sn 422; 400 noktalık seri sabit sayıda PB isteğiyle döner.
7. CSP'de harici host yok, Chart.js yerelden yükleniyor, ek başlıklar mevcut; /health gerçek PB durumunu gösterir.
8. MVP.md'deki her özellik testli ya da "kapsam dışı"; VaR/CVaR çıktıda; TODO sayıları gerçekle eşit.
9. `pytest -q` yeşil (101 + yeni testler), `ruff check .` ve `ruff format --check .` temiz, CI güncel HEAD'de yeşil.
```
