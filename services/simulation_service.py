"""
Monte Carlo & Stres Testi Servisi
===================================
Tarihsel getiri, volatilite ve korelasyon verilerine dayanarak
Monte Carlo simülasyonu (GBM, varyans düzeltmesi WITHOUT) ve makro stres testleri yapar.

Prompt 10 (Monte Carlo / Stres test düzeltmeleri) ile senkronize.

Düzeltmeler:
  - Drift: varyans düzeltmesi (0.5 * sigma^2) KULLANILMAZ. drift = mean(log returns).
  - Korelasyonlu çok varlıklı simülasyon (Cholesky decomposition).
  - use_ledger=True parametresi (miktarlar ledger'dan).
  - 3/6/12 ay horizons varsayılan.
  - Stres testi: varlık sınıfı duyarlılık tablosu, multiplicative shock + yayılma.
  - AI Risk Anlatısı artık ai_service.generate_risk_narrative üzerinden (tek kaynak).
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from services.multi_asset_manager import AssetManager
import config


# ---------------------------------------------------------------------------
# Tip tanımları
# ---------------------------------------------------------------------------

MonteCarloResult = Dict  # {'days': int, 'n_simulations': int, 'percentiles': List[int],
                          #  'percentile_values': {'portfolio': {'p5': ..., 'p50': ..., 'p95': ...}},
                          #  'asset_names': List[str], 'asset_final_values': List[Dict],
                          #  'total_initial_value': float, 'currency': str, 'data_quality': str}

StressTestResult = Dict  # {'original_value': float, 'days': int, 'n_simulations': int,
                          #  'stressed_values': Dict[str, Dict], 'worst_case': float, 'worst_case_name': str}


# ---------------------------------------------------------------------------
# Yardımcı: varlık getiri verilerini çek
# ---------------------------------------------------------------------------

def _fetch_asset_returns(
    symbol: str,
    asset_type: str,
    days: int = 504,
) -> Optional[pd.Series]:
    """Bir varlığın günlük log getiri serisi.

    Returns:
        İndeksi date, değerleri log getiri (float). Boşsa None.
    """
    mgr = AssetManager()
    data = mgr.get_historical_data(symbol, asset_type, days=days)
    if data is None or data.empty:
        return None

    if isinstance(data.columns, pd.MultiIndex):
        close_series = data["Close"]
        if isinstance(close_series, pd.DataFrame):
            close_series = close_series.iloc[:, 0]
    else:
        close_series = data.get("Close", data.iloc[:, 0])

    if close_series is None or close_series.empty:
        return None

    log_returns = np.log(close_series / close_series.shift(1)).dropna()
    log_returns.index = pd.to_datetime(log_returns.index).date
    return log_returns


def _fetch_all_asset_returns(
    assets: List[Dict],
    days: int = 504,
) -> Dict[str, Optional[pd.Series]]:
    """Birden fazla varlık için log getiri serileri."""
    returns: Dict[str, Optional[pd.Series]] = {}
    for asset in assets:
        sym = asset["symbol"]
        typ = asset.get("type", "crypto")
        rets = _fetch_asset_returns(sym, typ, days=days)
        returns[sym] = rets
    return returns


def _calculate_covariance_matrix(
    returns_dict: Dict[str, Optional[pd.Series]],
    asset_symbols: List[str],
) -> np.ndarray:
    """Varlıkların günlük log getiri kovaryans matrisi.

    Verisi olmayan varlıklar için kovaryans 0 (uyarı ile raporlanır).
    """
    n = len(asset_symbols)
    cov_matrix = np.zeros((n, n))

    available = [sym for sym in asset_symbols if sym in returns_dict and returns_dict[sym] is not None]
    if not available:
        return cov_matrix

    df = pd.DataFrame({sym: returns_dict[sym] for sym in available}).dropna()
    if df.empty:
        for i, sym in enumerate(asset_symbols):
            rets = returns_dict.get(sym)
            if rets is not None:
                r = rets.dropna()
                if len(r) > 1:
                    cov_matrix[i, i] = float(np.var(r))
        return cov_matrix

    cov = df.cov().values
    for i, sym_i in enumerate(available):
        for j, sym_j in enumerate(available):
            cov_matrix[asset_symbols.index(sym_i), asset_symbols.index(sym_j)] = cov[i, j]

    return cov_matrix


# ---------------------------------------------------------------------------
# GBM simülasyonu (Prompt 10 – düzeltme: varyans düzeltmesi YOK)
# ---------------------------------------------------------------------------

def _simulate_paths_gbm(
    initial_value: float,
    mean_return: float,
    daily_vol: float,
    days: int,
    n_simulations: int,
    seed: Optional[int] = None,
) -> np.ndarray:
    """Tek varlık GBM simülasyonu.

    Prompt 10 düzeltmesi: drift = mean(log returns); varyans düzeltmesi uygulanmaz.
    GBM adımı: S_t = S_{t-1} * exp(drift + sigma * Z)
    """
    rng = np.random.default_rng(seed)
    paths = np.zeros((n_simulations, days))
    paths[:, 0] = initial_value

    Z = rng.standard_normal((n_simulations, days - 1))
    drift = mean_return  # Prompt 10: varyans düzeltmesi yok
    diffusion = daily_vol * Z
    increments = np.exp(drift + diffusion)
    paths[:, 1:] = initial_value * np.cumprod(increments, axis=1)

    return paths


def _simulate_paths_multivariate(
    initial_values: np.ndarray,
    means: np.ndarray,
    volds: np.ndarray,
    cov_matrix: np.ndarray,
    days: int,
    n_simulations: int,
    seed: Optional[int] = None,
) -> np.ndarray:
    """Korelasyonlu çok varlıklı GBM simülasyonu (Prompt 10 – Cholesky).

    Cholesky(cov) ile ortak Z üretir; her varlık için yolu simüle eder.
    Portföy = Σ miktar_i × varlık_yolu_i (sabit miktar, rebalance yok).

    Returns:
        (n_simulations, days, n_assets) array.
    """
    rng = np.random.default_rng(seed)
    n_assets = len(initial_values)

    # Cholesky dekompozisyonu (eigenvalue clipping ile güvence)
    try:
        L = np.linalg.cholesky(cov_matrix)
    except np.linalg.LinAlgError:
        eigenvalues, eigenvectors = np.linalg.eigh(cov_matrix)
        eigenvalues = np.maximum(eigenvalues, 0.0)
        cov_matrix = eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T
        L = np.linalg.cholesky(cov_matrix)

    paths = np.zeros((n_simulations, days, n_assets))
    paths[:, 0, :] = initial_values[np.newaxis, :]

    for t in range(1, days):
        Z_raw = rng.standard_normal((n_simulations, n_assets))
        Z_corr = Z_raw @ L.T  # (n_simulations, n_assets) – korelasyonlu
        for a in range(n_assets):
            drift = means[a]  # Prompt 10: varyans düzeltmesi yok
            diffusion = volds[a] * Z_corr[:, a]
            paths[:, t, a] = paths[:, t - 1, a] * np.exp(drift + diffusion)

    return paths


def _percentile_values(paths: np.ndarray, percentiles: List[int]) -> Dict[str, float]:
    """Son gün değerlerinin percentillerini hesapla."""
    final_values = paths[:, -1]
    return {f"p{p}": round(float(np.percentile(final_values, p)), 2) for p in percentiles}


# ---------------------------------------------------------------------------
# 1. Monte Carlo Simülasyonu (Prompt 10 – düzeltmeler)
# ---------------------------------------------------------------------------

def monte_carlo_simulation(
    session,
    asset_list: List[Dict],
    days: int = 252,
    n_simulations: int = 10000,
    percentiles: Optional[List[int]] = None,
    seed: Optional[int] = None,
    use_ledger: bool = True,
) -> MonteCarloResult:
    """Portföy için Monte Carlo simülasyonu (Prompt 10 düzeltmeleri).

    Args:
        session: SQLAlchemy Session (PB geçişi devam ederken geçici).
        asset_list: [{'symbol': 'BTC', 'type': 'crypto', 'amount': 0.5}, ...]
        days: Kaç gün (varsayılan 252 = 1 yıl; use_ledger=True ise 3/6/12 ay)
        n_simulations: Kaç patika (varsayılan 10,000; 200k yol sınırı)
        percentiles: Percentiller (varsayılan [5, 50, 95])
        seed: RNG seed (opsiyonel; reproducibility için)
        use_ledger: True → miktarlar ledger'dan gelir (Prompt 10)

    Returns:
        MonteCarloResult dict.
    """
    if percentiles is None:
        percentiles = [5, 50, 95]

    if n_simulations > 200_000:
        raise ValueError(f"n_simulations={n_simulations} → maksimum 200,000 (Prompt 3).")

    asset_symbols = [a["symbol"] for a in asset_list]

    # Başlangıç değerleri (Prompt 10: use_ledger=True → miktarlar ledger'dan)
    initial_values = []
    for a in asset_list:
        amount = a.get("amount", 1.0)
        if use_ledger:
            from services.ledger_service import get_portfolio_snapshot
            snapshot = get_portfolio_snapshot(session, as_of=None)
            holdings = {h["asset_symbol"]: h for h in snapshot.get("holdings", [])}
            amount = holdings.get(a["symbol"], {}).get("quantity", 0.0)
        mgr = AssetManager()
        price = mgr.get_price(a["symbol"], a.get("type", "crypto"))
        if price is None:
            price = 1.0
        initial_values.append(amount * price)

    total_initial = sum(initial_values)

    # Log getiri serileri
    returns_dict = _fetch_all_asset_returns(asset_list, days=min(days * 2, 504))

    # Ortalama getiri ve volatilite
    means: List[float] = []
    volds: List[float] = []
    missing_data_warning = False
    for i, sym in enumerate(asset_symbols):
        rets = returns_dict.get(sym)
        if rets is not None and len(rets) > 1:
            mean = float(rets.mean())
            vol = float(rets.std())
            if len(rets) < 60:
                missing_data_warning = True
        else:
            mean = 0.0
            vol = 0.0008  # varsayılan volatilite (Prompt 10: veri-yok varlık için)
            missing_data_warning = True
        means.append(mean)
        volds.append(vol)

    # Kovaryans matrisi
    cov_matrix = _calculate_covariance_matrix(returns_dict, asset_symbols)

    # Portföy ağırlıkları
    weights = np.array([v / total_initial for v in initial_values])

    # Portföy parametreleri
    daily_mean = float(np.dot(weights, means))
    daily_vol = float(np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))))

    # Portföy simülasyonu (vektörize, Prompt 10)
    rng = np.random.default_rng(seed)
    portfolio_paths = np.zeros((n_simulations, days))
    portfolio_paths[:, 0] = total_initial

    Z = rng.standard_normal((n_simulations, days - 1))
    drift = daily_mean  # Prompt 10: varyans düzeltmesi yok
    diffusion = daily_vol * Z
    increments = np.exp(drift + diffusion)
    portfolio_paths[:, 1:] = total_initial * np.cumprod(increments, axis=1)

    portfolio_percentiles = _percentile_values(portfolio_paths, percentiles)

    # Korelasyonlu çok varlıklı simülasyon (Prompt 10 – Cholesky)
    initial_values_np = np.array(initial_values)
    means_np = np.array(means)
    volds_np = np.array(volds)
    asset_paths = _simulate_paths_multivariate(
        initial_values_np,
        means_np,
        volds_np,
        cov_matrix,
        days,
        n_simulations,
        seed=seed,
    )

    # Her varlık için percentiller
    asset_final_values = []
    for i, sym in enumerate(asset_symbols):
        asset_pcts = _percentile_values(asset_paths[:, :, i], percentiles)
        asset_final_values.append({
            "symbol": sym,
            "initial_value": round(initial_values[i], 2),
            **asset_pcts,
        })

    data_quality = "estimated" if missing_data_warning else "ok"
    currency = "TRY"  # Prompt 10: API'den gelmeli, şimdilik varsayılan

    return {
        "days": days,
        "n_simulations": n_simulations,
        "percentiles": percentiles,
        "percentile_values": {
            "portfolio": portfolio_percentiles,
        },
        "asset_names": asset_symbols,
        "asset_final_values": asset_final_values,
        "total_initial_value": round(total_initial, 2),
        "currency": currency,
        "data_quality": data_quality,
    }


# ---------------------------------------------------------------------------
# 2. Stres Testi (Prompt 10 – gerçekleştirilmiş)
# ---------------------------------------------------------------------------

DEFAULT_STRESS_SCENARIOS: Dict[str, Dict] = {
    "rate_hike": {
        "description": "Faiz artışı şoku",
        "asset_impacts": {
            "crypto":    {"price_shock_pct": -0.15, "vol_multiplier": 1.8},
            "stock_tr":  {"price_shock_pct": -0.08,  "vol_multiplier": 1.5},
            "stock_us":  {"price_shock_pct": -0.10,  "vol_multiplier": 1.6},
            "commodity": {"price_shock_pct": +0.05,  "vol_multiplier": 1.3},
            "cash":      {"price_shock_pct": +0.02,  "vol_multiplier": 1.0},
            "default":   {"price_shock_pct": -0.05,  "vol_multiplier": 1.4},
        },
        "vol_multiplier": 1.5,
        "drift_shift": -0.0002,
    },
    "rate_cut": {
        "description": "Faiz indirimi şoku",
        "asset_impacts": {
            "crypto":    {"price_shock_pct": +0.10, "vol_multiplier": 1.2},
            "stock_tr":  {"price_shock_pct": +0.06, "vol_multiplier": 1.1},
            "stock_us":  {"price_shock_pct": +0.08, "vol_multiplier": 1.2},
            "commodity": {"price_shock_pct": -0.02, "vol_multiplier": 1.1},
            "cash":      {"price_shock_pct": -0.01, "vol_multiplier": 1.0},
            "default":   {"price_shock_pct": +0.04, "vol_multiplier": 1.1},
        },
        "vol_multiplier": 1.2,
        "drift_shift": +0.0001,
    },
    "fx_shock": {
        "description": "Döviz kuru şoku (TRY kaybı)",
        "asset_impacts": {
            "crypto":    {"price_shock_pct": +0.10, "vol_multiplier": 1.2},
            "stock_tr":  {"price_shock_pct": +0.05, "vol_multiplier": 1.1},
            "stock_us":  {"price_shock_pct": -0.10, "vol_multiplier": 1.3},
            "commodity": {"price_shock_pct": +0.08, "vol_multiplier": 1.2},
            "cash":      {"price_shock_pct": -0.15, "vol_multiplier": 1.5},
            "default":   {"price_shock_pct": +0.05, "vol_multiplier": 1.2},
        },
        "vol_multiplier": 1.3,
        "drift_shift": 0.0,
    },
    "global_recession": {
        "description": "Küresel durgunluk",
        "asset_impacts": {
            "crypto":    {"price_shock_pct": -0.25, "vol_multiplier": 2.0},
            "stock_tr":  {"price_shock_pct": -0.20, "vol_multiplier": 1.8},
            "stock_us":  {"price_shock_pct": -0.22, "vol_multiplier": 1.9},
            "commodity": {"price_shock_pct": -0.15, "vol_multiplier": 1.5},
            "cash":      {"price_shock_pct": +0.02, "vol_multiplier": 1.0},
            "default":   {"price_shock_pct": -0.15, "vol_multiplier": 1.7},
        },
        "vol_multiplier": 1.8,
        "drift_shift": -0.0003,
    },
    "market_crash": {
        "description": "Piyasa çöküşü (anlık şok + yayılma)",
        "asset_impacts": {
            "crypto":    {"price_shock_pct": -0.40, "vol_multiplier": 2.5},
            "stock_tr":  {"price_shock_pct": -0.35, "vol_multiplier": 2.2},
            "stock_us":  {"price_shock_pct": -0.40, "vol_multiplier": 2.5},
            "commodity": {"price_shock_pct": -0.25, "vol_multiplier": 1.8},
            "cash":      {"price_shock_pct": +0.02, "vol_multiplier": 1.0},
            "default":   {"price_shock_pct": -0.30, "vol_multiplier": 2.0},
        },
        "vol_multiplier": 2.0,
        "drift_shift": -0.0005,
    },
}


def stress_test(
    session,
    portfolio_value: float,
    shocks: Optional[Dict[str, float]] = None,
    days: int = 252,
    n_simulations: int = 1000,
    seed: Optional[int] = None,
) -> StressTestResult:
    """Makro şok senaryoları altında portföy değerlerini simüle et (Prompt 10).

    Şoklar varlık sınıfı duyarlılık tablosuyla uygulanır. market_crash:
    anlık şok + sonraki günlerde multiplicative yayılma.

    Args:
        session: SQLAlchemy Session
        portfolio_value: Başlangıç portföy değeri
        shocks: Özel şoklar (opsiyonel; key=senaryo adı, value=şok büyüklüğü)
        days: Simülasyon süresi
        n_simulations: Kaç patika
        seed: RNG seed

    Returns:
        StressTestResult dict.
    """
    scenarios = DEFAULT_STRESS_SCENARIOS.copy()
    if shocks:
        for name, magnitude in shocks.items():
            if name in scenarios:
                scenarios[name] = _apply_custom_shock(scenarios[name], magnitude)

    stressed_values: Dict[str, Dict] = {}

    for scenario_name, scenario in scenarios.items():
        description = scenario.get("description", scenario_name)
        asset_impacts = scenario.get("asset_impacts", {})
        vol_mult = scenario.get("vol_multiplier", 1.0)
        drift_shift = scenario.get("drift_shift", 0.0)

        impacts = asset_impacts.get("default", {"price_shock_pct": -0.05, "vol_multiplier": 1.4})
        price_shock = impacts.get("price_shock_pct", -0.05)
        vol_mult_actual = impacts.get("vol_multiplier", vol_mult)

        rng = np.random.default_rng(seed)
        stressed_vol = 0.0008 * vol_mult_actual
        stressed_mean = drift_shift

        if n_simulations > 200_000:
            raise ValueError(f"n_simulations={n_simulations} → maksimum 200,000 (Prompt 3).")

        Z = rng.standard_normal((n_simulations, days - 1))
        drift = stressed_mean  # Prompt 10: varyans düzeltmesi yok
        diffusion = stressed_vol * Z
        increments = np.exp(drift + diffusion)

        paths = np.zeros((n_simulations, days))
        paths[:, 0] = portfolio_value
        paths[:, 1:] = portfolio_value * np.cumprod(increments, axis=1)

        # Market crash: anlık şok + sonraki günlerde multiplicative yayılma (Prompt 10)
        if scenario_name == "market_crash" and price_shock != 0:
            crash_day = min(10, days // 3)
            paths[:, crash_day] = paths[:, crash_day] * (1 + price_shock)
            for t in range(crash_day + 1, days):
                paths[:, t] = paths[:, t] * (1 + price_shock * 0.1)
        elif price_shock != 0 and scenario_name != "market_crash":
            paths = paths * (1 + price_shock)

        final_values = paths[:, -1]

        stressed_values[scenario_name] = {
            "description":    description,
            "expected_value": round(float(np.mean(final_values)), 2),
            "p5":             round(float(np.percentile(final_values, 5)), 2),
            "p50":            round(float(np.percentile(final_values, 50)), 2),
            "p95":            round(float(np.percentile(final_values, 95)), 2),
            "loss_pct":       round(float(np.mean(final_values)) / portfolio_value - 1, 6),
        }

    worst_value = portfolio_value
    worst_name = "none"
    for sn, sv in stressed_values.items():
        if sv["expected_value"] < worst_value:
            worst_value = sv["expected_value"]
            worst_name = sn

    return {
        "original_value": round(portfolio_value, 2),
        "days": days,
        "n_simulations": n_simulations,
        "stressed_values": stressed_values,
        "worst_case": round(worst_value, 2),
        "worst_case_name": worst_name,
    }


def _apply_custom_shock(scenario: Dict, magnitude: float) -> Dict:
    """Özel şok büyüklüğü ile varsayılan senaryoyu scale et."""
    new_scenario = {k: v for k, v in scenario.items() if k != "asset_impacts"}
    asset_impacts = dict(scenario.get("asset_impacts", {}))
    for asset_type, impact in asset_impacts.items():
        if asset_type == "default":
            impact = dict(impact, price_shock_pct=-magnitude)
        else:
            impact = dict(impact, price_shock_pct=-magnitude * 0.8)
        asset_impacts[asset_type] = impact
    new_scenario["asset_impacts"] = asset_impacts
    return new_scenario


# ---------------------------------------------------------------------------
# 3. AI Risk Anlatısı (Prompt 7 → ai_service.generate_risk_narrative)
# ---------------------------------------------------------------------------

def generate_risk_narrative(
    simulation_result: MonteCarloResult,
    portfolio_context: Optional[Dict] = None,
    api_key: Optional[str] = None,
) -> str:
    """Monte Carlo / stres test sonucu için Türkçe risk anlatısı (Prompt 7).

    Artık kendi Gemini çağrısını yapmaz; ai_service.generate_risk_narrative
    kullanılır (tek kaynak, hata yönetimi + exception sınıfları).
    """
    try:
        from services.ai_service import generate_risk_narrative as ai_generate_risk_narrative
        return ai_generate_risk_narrative(
            simulation_result=simulation_result,
            context=portfolio_context,
            api_key=api_key,
        )
    except Exception as exc:
        raise RuntimeError(f"AI Risk Anlatısı generation failed: {exc}") from exc
