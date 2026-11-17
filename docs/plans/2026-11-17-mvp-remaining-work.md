# FutureWallet MVP Kalan İşler (P9 + EXPIRED E2E + Review Minörleri) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TODO.md v4 "Öncelik Sırası"ndaki 4 açık maddeyi kapat: dinamik `currency`, EXPIRED job'ının gerçek PB uçtan uca testi, shadow-create karar sahipliği + PB ID girdi doğrulaması, CI import duman adımı.

**Architecture:** `currency` karar çıktısı tek kaynaktan (`services/asset_types.py` taban-parası helper'ı) üretilir; API'den beslenen web seçici ona bağlanır. Güvenlik minörleri servis + Pydantic/Path pattern katmanında düzeltilir.

**Tech Stack:** FastAPI, PocketBase 0.40.6 (gerçek binary fixture), pytest, ruff, mypy, uv.

**Spec:** `MVP.md` (v2) + `TODO.md` (v4, "Öncelik Sırası" maddeleri 1–3, P1 kalan madde)

## Global Constraints

- Yalnızca gerçek PocketBase entegrasyon testinden geçen maddeler `[x]` yapılabilir (TODO.md Temel İlke). Dış AI/HTTP mock'lanabilir; PB mock'lanamaz.
- `ruff check .` + `ruff format --check .` + `mypy api services config.py web_app` (gevşek mod) temiz kalmalı.
- Python 3.11; paket işlemleri `uv` ile (`./bin/uv`).
- Testler ağa çıkmamalı: fiyat seed'lemesi PB `price_history` cache üzerinden veya `AssetManager.get_price` patch'i ile.
- PB autogenerate ID biçimi: `^[a-z0-9]{15}$`.

## Review Focus

- Cash-only portföy (holdings'te yalnız `CASH` kovası): sembol seti boş kalır → `currency:"TRY"` (varsayılan), crash yok → T1 testi.
- Karışık tabanlı sepet (BTC+THYAO.IS): çoğunluk-kuralı deterministik; eşitlikte TRY → T1 birim testi.
- 15 karakter dışı/büyük harfli ID girdisi path/query/body'de: 422, servise ulaşmadan → T4 testi.
- Body'de biçimli ama var olmayan / yabancı `decision_id` ile shadow create: 400 (PB sessiz düşürme/500 yerine) → T4 testi.
- MC cevabında `currency` alanı yoksa web seçici eski davranışı korur (graceful) → T2 kod incelemesi.

---

### Task 1: P9 dinamik currency (API)

**Files:**
- Modify: `services/asset_types.py` (sona ekle)
- Modify: `api/app.py:618-690` (value-series), import satırı `asset_types`
- Modify: `services/simulation_service.py:355` (`currency = "TRY"` satırı)
- Test: `tests/test_price_valuation.py` (ekleme), `tests/test_simulation_stress.py` (varsa currency assertion'ı genişlet)

**Interfaces:**
- Produces: `base_currency(symbol: str) -> str` (`"TRY"|"USD"`), `infer_portfolio_currency(symbols: Sequence[str]) -> str` (boş → `"TRY"`; USD > TRY → `"USD"`, aksi → `"TRY"`). Value-series ve MC cevabında `currency` alanı artık bu helper'dan.

- [ ] **Step 1: failing test yaz** — `tests/test_price_valuation.py` içine:
  - `test_base_currency_mapping`: `THYAO.IS`→TRY, `GARAN`→TRY, `BTC/USDT`→USD, `GC=F`→USD, `TRY`→TRY, `USDT`→USD.
  - `test_infer_portfolio_currency`: `[]`→TRY, `["BTC","ETH"]`→USD, `["THYAO.IS","GARAN"]`→TRY, `["BTC","THYAO.IS"]`→TRY (eşitlik), `["BTC","ETH","THYAO.IS"]`→USD.
  - `test_value_series_currency_usd_for_crypto_portfolio` (pb): kullanıcı BTC BUY; `services.multi_asset_manager.AssetManager.get_price` None'a patch'lenmiş halde 3 günlük value-series → `currency == "USD"`; `patch` olmaksızın dış servis çağrılmadığını da doğrula (seed yoksa değer 0 ama sembol yine toplanır).
  - `test_value_series_currency_try_for_bist_portfolio` (pb): THYAO.IS BUY → `currency == "TRY"`.
- [ ] **Step 2:** `pytest tests/test_price_valuation.py -v` → FAIL (ImportError / sabit TRY).
- [ ] **Step 3: Implement** `services/asset_types.py`:
  ```python
  def base_currency(symbol: str) -> str: ...
  def infer_portfolio_currency(symbols) -> str: ...
  ```
  Kural: `stock_tr` veya sembol `TRY`/`TL` → `"TRY"`, diğer her sembol → `"USD"`. `CASH` kovası çağrı tarafında elenir (kuralı bozan sinyal değil). Karışık sepette çoğunluk; eşitlikte TRY. Kod içine tek satır `shortcut: tek para birimli gösterim; çoklu-currency değerleme gelince upgrade edilir`.
- [ ] **Step 4: wire** `api/app.py` value-series: snapshot döngüsünde `snap["holdings"]` içinden `type != "cash"` sembollerini `set`'e topla; iki return dalında da `"currency": infer_portfolio_currency(sorted(syms))`; docstring'deki `"currency": "TRY"` satırını dinamik notla değiştir. `services/simulation_service.py:355` → `currency = infer_portfolio_currency(asset_symbols)` (+import).
- [ ] **Step 5:** `pytest tests/test_price_valuation.py tests/test_simulation_stress.py -v` → PASS. `test_simulation_stress` içinde MC cevabı üreten test varsa `result["currency"]` assertion'ı ekle (BTC tabanlıysa `"USD"`).
- [ ] **Step 6: Commit** `feat(p9): dynamic base-currency inference for value-series and monte-carlo`

### Task 2: Web seçici → API currency bağlama

**Files:**
- Modify: `web_app/static/app.js` (`runMonteCarlo` ~L514 sonrası)

- [ ] **Step 1:** `runMonteCarlo`'da `result` alındıktan sonra kartlar çizilmeden önce:
  ```js
  if (result.currency) { const sel = $('#currencySelect'); sel.value = result.currency; setCurrency(result.currency); }
  ```
  `currency` yoksa hiçbir şey olmasın (graceful).
- [ ] **Step 2: Check** `node --check web_app/static/app.js` (yoksa `bun build --target=bun` / temp eval) sözdizimi temiz.
- [ ] **Step 3: Commit** `feat(web): bind currency selector to API currency field`

### Task 3: EXPIRED job gerçek PB uçtan uca testi

**Files:**
- Test: `tests/test_expiry_e2e.py` (create)

**Interfaces:**
- Consumes: `services.decision_service.auto_close_expired_decisions()`, PB `price_history` cache seed'i (`pb_admin` fixture), `POST /api/decisions` (decision_date geçmiş, target_date=dün), `GET /api/decisions/{id}`.

- [ ] **Step 1: test yaz** (pb marker): BTC için `price_history`'e `decision_date`te 50000, `target_date`te 60000 seed'le (format `YYYY-MM-DD 00:00:00.000Z`, cache-hit zinceri dış servise gitmez). Karar oluştur (BUY, decision_date=today-5, target_date=today-1) → `auto_close_expired_decisions()` çağır → dönen listede id var; API'den GET → `status=="EXPIRED"`, `outcome_price==60000`, `outcome_return_pct==20.0`. Hedef tarihi geçmemiş ikinci bir OPEN karar EXPIRED **olmamalı**.
- [ ] **Step 2:** `pytest tests/test_expiry_e2e.py -v` → PASS (kod değişikliği beklenmiyor; test önce gerçekten FAIL üreten boşluk — job body'si hiç tetiklenmemişti; FAIL görürse hata düzeltilir).
- [ ] **Step 3: Commit** `test(scheduler): end-to-end PB test for EXPIRED job`

### Task 4: Review minörleri — shadow create sahiplik + PB ID doğrulaması

**Review:** per-task — security/auth

**Files:**
- Modify: `services/counterfactual_service.py` (`create_shadow_position` başı)
- Modify: `api/app.py` (PB_ID pattern: path/query/body alanları; `Path`, `Annotated` import)
- Test: `tests/test_review_fixes.py` (ekleme)

**Interfaces:**
- Produces: `api/app.py` içinde `PB_ID_PATTERN = "^[a-z0-9]{15}$"`, `PbId = Annotated[str, Path(pattern=PB_ID_PATTERN)]`. `create_shadow_position` yabancı/olmayan karar için `ValueError` → endpoint 400.

- [ ] **Step 1: failing tests yaz:**
  - `test_shadow_position_rejects_foreign_decision` (pb): B'nin kararına A shadow create → 400.
  - `test_shadow_position_rejects_missing_decision` (pb): biçimli (15 karakter lowercase alnum) ama olmayan id → 400.
  - `test_invalid_pb_id_paths_return_422`: `GET /api/decisions/BADID` → 422; `DELETE /api/transactions/TOO_LONG_TRANSACTION_ID` → 422; `GET /api/counterfactual?decision_id=nope` → 422.
- [ ] **Step 2:** çalıştır → FAIL (şu an 200/404/500 üreten yollar).
- [ ] **Step 3: implement**
  - `counterfactual_service.create_shadow_position`: girişte `dec = get_decision(decision_id); if not dec or dec.get("user") != user_id: raise ValueError("decision geçersiz veya bu kullanıcıya ait değil")` (endpoint'in mevcut `except ValueError→400`'ünü kullanır; internal çağrı kendi yeni kararını geçtiğinden etkilenmez).
  - `api/app.py`: 7 decision path-uçu (`GET/PUT/DELETE /{decision_id}`, `/close`, `/target-check`, `/evaluate`, `/retrospective`) + `position_id` + `transaction_id` path paramlarını `PbId`'ye çevir; `/api/counterfactual` query `decision_id` ve shadow-list query `decision_id`'e `pattern=PB_ID_PATTERN`; `ShadowPositionCreateRequest.decision_id` ve `DecisionCreateRequest.transaction_id` Field'larına `pattern=PB_ID_PATTERN` (transaction_id'deki `max_length=36` pattern'e bırakır).
- [ ] **Step 4:** `pytest tests/test_review_fixes.py tests/test_counterfactual.py tests/test_security_auth.py -v` → PASS (mevcut testler gerçek 15-karakter PB id kullandığı için kırılmamalı; kırılan olursa test id'si düzeltilir, davranış değil).
- [ ] **Step 5: Commit** `fix(security): shadow-create decision ownership + PB record id validation`

### Task 5: CI import duman adımı

**Files:**
- Modify: `.github/workflows/ci.yml` (`test` job, pytest adımı öncesi)

- [ ] **Step 1:** ekle:
  ```yaml
  - name: Import smoke check
    env:
      POCKETBASE_URL: http://127.0.0.1:8090
      POCKETBASE_EMAIL: ci@futurewallet.test
      POCKETBASE_PASSWORD: ci-dummy-password
    run: python -c "import api.app"
  ```
- [ ] **Step 2: Check** Yerelde aynı env ile `python -c "import api.app"` → exit 0; `ruff`/`actionlint` varsa workflow YAML geçerli.
- [ ] **Step 3: Commit** `ci: add standalone import api.app smoke step`

### Task 6: Doküman senkronu + tam doğrulama

**Files:**
- Modify: `TODO.md` (P1 CI, P8 google-genai kutusu, P9 currency, P14 seçici, Hızlı Kontrol 11/13, Öncelik Sırası), `MVP.md` (durum notu + Sprint 4 satırı), `GUNCEL_IS_PLANI.md` (kalan açıklar tablosu/satırları)

- [ ] **Step 1:** Tam suite: `pytest tests` (gerçek PB) → hepsi geçmeli; `ruff check .` + `ruff format --check .`; `mypy api services config.py web_app`.
- [ ] **Step 2:** Dokümanlardaki `[ ]` kutuları gerçek sonuçla eşitlle (yalnız geçenler `[x]`), sürüm notunu 2026-11-17 durumuna güncelle; Öncelik Sırası'nı "kalan: yok / gözlem listesi"ne çevir.
- [ ] **Step 3: Commit** `docs: sync TODO/MVP/GUNCEL after P9 + expiry E2E + review minors`

---

## Self-Review notları

- Kapsam: TODO v4 kalan 3 öncelik + P1 duman + P8 bayat kutu — hepsi bir göreve bağlı. README'ye dokunma gerekmiyor (kullanıcı akışı değişmedi).
- Tip tutarlılığı: `infer_portfolio_currency(symbols)` T1'de tanımlı, T1/T2 tüketir; `PbId` yalnız T4.
- Oran: plan, dokunulan kodun ~2 katı satır — kabul edilebilir; MC currency'si için ayrı endpoint testi yerine mevcut dosyaya tek assertion.
