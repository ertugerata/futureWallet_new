"""
FutureWallet - Monte Carlo & Stres Testi Servisi

MVP §3.5, TODO 3.1.

Tarihsel getiri, volatilite ve korelasyon verilerine dayanarak
Monte Carlo simülasyonu (10.000 patika) ve makro stres testleri yapar.
AI Risk Anlatısı (LLM) ile sonuçları Türkçe metne dönüştürür.
"""

from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from sqlalchemy import select
from sqlalchemy.orm import Session

from db import MacroData
from services.multi_asset_manager import AssetManager
import config


# --------------------------------------------------------------------
# Tip tanımları
# --------------------------------------------------------------------

MonteCarloResult = Dict  # {'days': int, 'n_simulations': int, 'percentiles': List[int],
                          #  'percentile_values': {'portfolio': {'p5': ..., 'p50': ..., 'p95': ...}},
                          #  'asset_names': List[str], 'asset_final_values': List[Dict],
                          #  'total_initial_value': float}

StressTestResult = Dict  # {'original_value': float, 'stressed_values': Dict[str, Dict],
                          #  'worst_case': float, 'worst_case_name': str}


# --------------------------------------------------------------------
# Yardımcı: varlık getiri verilerini çek
# --------------------------------------------------------------------

def _fetch_asset_returns(
    symbol: str,
    asset_type: str,
    days: int = 504,
) -> Optional[pd.Series]:
    """
    Bir varlığın günlük log getiri serisi.

    Args:
        symbol: Varlık sembolü
        asset_type: crypto | stock_tr | stock_us | commodity | cash
        days: Kaç günlük geçmiş veri (varsayılan 504 = 2 yıl)

    Returns:
        İndeksi date (datetime.date), değerleri log getiri (float).
        Boşsa None.
    """
    mgr = AssetManager()
    data = mgr.get_historical_data(symbol, asset_type, days=days)
    if data is None or data.empty:
        return None

    # Close sütununu bul
    if isinstance(data.columns, pd.MultiIndex):
        close_series = data["Close"]
        if isinstance(close_series, pd.DataFrame):
            close_series = close_series.iloc[:, 0]
    else:
        close_series = data.get("Close", data.iloc[:, 0])

    if close_series is None or close_series.empty:
        return None

    # Log getiri
    log_returns = np.log(close_series / close_series.shift(1)).dropna()
    log_returns.index = pd.to_datetime(log_returns.index).date

    return log_returns


def _fetch_all_asset_returns(
    assets: List[Dict],
    days: int = 504,
) -> Dict[str, Optional[pd.Series]]:
    """Birden fazla varlık için log getiri serileri."""
    returns = {}
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
    """
    Varlıkların günlük log getiri kovaryans matrisi.

    Verisi olmayan varlıkların kovaryansı 0 olarak bırakılır
    (bu durum simülasyon sonuçlarını etkiler — gerçek uygulamada daha
    iyi bir yaklaşım gerekir).
    """
    n = len(asset_symbols)
    cov_matrix = np.zeros((n, n))

    available = [sym for sym in asset_symbols if sym in returns_dict and returns_dict[sym] is not None]

    if len(available) == 0:
        return cov_matrix

    df = pd.DataFrame({sym: returns_dict[sym] for sym in available})
    df = df.dropna()

    if df.empty:
        for i, sym in enumerate(asset_symbols):
            if sym in returns_dict and returns_dict[sym] is not None:
                rets = returns_dict[sym].dropna()
                if len(rets) > 1:
                    cov_matrix[i, i] = float(np.var(rets))
        return cov_matrix

    cov = df.cov().values

    for i, sym_i in enumerate(available):
        for j, sym_j in enumerate(available):
            idx_i = asset_symbols.index(sym_i)
            idx_j = asset_symbols.index(sym_j)
            cov_matrix[idx_i, idx_j] = cov[i, j]

    return cov_matrix


def _simulate_paths_gbm(
    initial_value: float,
    mean_return: float,
    daily_vol: float,
    days: int,
    n_simulations: int,
    seed: Optional[int] = None,
) -> np.ndarray:
    """
    Geometric Brownian Motion ile n_simulations patika simüle et.

    Args:
        initial_value: Başlangıç değeri
        mean_return: Günlük ortalama log getiri
        daily_vol: Günlük volatilite
        days: Kaç gün
        n_simulations: Kaç patika
        seed: RNG seed (opsiyonel)

    Returns:
        (n_simulations, days) numpy array. Son sütün = son gün değerleri.
    """
    rng = np.random.default_rng(seed)
    paths = np.zeros((n_simulations, days))
    paths[:, 0] = initial_value

    for t in range(1, days):
        Z = rng.standard_normal(n_simulations)
        drift = (mean_return - 0.5 * daily_vol**2)
        diffusion = daily_vol * Z
        paths[:, t] = paths[:, t-1] * np.exp(drift + diffusion)

    return paths


def _percentile_values(paths: np.ndarray, percentiles: List[int]) -> Dict[str, float]:
    """Son gün değerlerinin percentillerini hesapla."""
    final_values = paths[:, -1]
    return {f"p{p}": round(float(np.percentile(final_values, p)), 2) for p in percentiles}


# --------------------------------------------------------------------
# 1. Monte Carlo Simülasyonu
# --------------------------------------------------------------------

def monte_carlo_simulation(
    session: Session,
    asset_list: List[Dict],
    days: int = 252,
    n_simulations: int = 10000,
    percentiles: Optional[List[int]] = None,
    seed: Optional[int] = None,
) -> MonteCarloResult:
    """
    Portföy için Monte Carlo simülasyonu.

    Her varlık için tarihsel getiri kullanılarak:
      1. Ortalama getiri ve volatilite hesaplanır
      2. Kovaryans matrisi hesaplanır
      3. GBM ile n_simulations patika simüle edilir
      4. Son gün değerlerinin percentillerü hesaplanır

    Args:
        session: SQLAlchemy Session
        asset_list: [{'symbol': 'BTC', 'type': 'crypto', 'amount': 0.5}, ...]
        days: Kaç gün (varsayılan 252 = 1 yıl)
        n_simulations: Kaç patika (varsayılan 10,000)
        percentiles: Hangileri hesaplanır (varsayılan [5, 50, 95])
        seed: RNG seed (opsiyonel; reproducibility için)

    Returns:
        {
            "days":             int,
            "n_simulations":    int,
            "percentiles":      List[int],
            "percentile_values": {
                "portfolio": { "p5": ..., "p50": ..., "p95": ... },
            },
            "asset_names":      List[str],
            "asset_final_values": [
                {"symbol": "BTC", "initial_value": ..., "p5": ..., "p50": ..., "p95": ...},
                ...
            ],
            "total_initial_value": float,
        }
    """
    if percentiles is None:
        percentiles = [5, 50, 95]

    asset_symbols = [a["symbol"] for a in asset_list]

    # Her bir varlık için başlangıç değeri
    initial_values = []
    for a in asset_list:
        amount = a.get("amount", 1.0)
        mgr = AssetManager()
        price = mgr.get_price(a["symbol"], a.get("type", "crypto"))
        if price is None:
            price = 1.0
        initial_values.append(amount * price)

    total_initial = sum(initial_values)

    # Her varlık için log getiri serileri
    returns_dict = _fetch_all_asset_returns(asset_list, days=min(days * 2, 504))

    # Ortalama getiri ve volatilite
    means = []
    volds = []
    for i, sym in enumerate(asset_symbols):
        rets = returns_dict.get(sym)
        if rets is not None and len(rets) > 1:
            mean = float(rets.mean())
            vol = float(rets.std())
        else:
            mean = 0.0
            vol = 0.0008  # ~20% yıllık volatilite → günlük
        means.append(mean)
        volds.append(vol)

    # Kovaryans matrisi
    cov_matrix = _calculate_covariance_matrix(returns_dict, asset_symbols)

    # Portföy ağırlıkları
    weights = np.array([v / total_initial for v in initial_values])

    # Portföy parametreleri
    daily_mean = float(np.dot(weights, means))
    daily_vol = float(np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))))

    # Portföy patikaları
    rng = np.random.default_rng(seed)
    portfolio_paths = np.zeros((n_simulations, days))
    portfolio_paths[:, 0] = total_initial

    for t in range(1, days):
        Z = rng.standard_normal(n_simulations)
        drift = (daily_mean - 0.5 * daily_vol**2)
        diffusion = daily_vol * Z
        portfolio_paths[:, t] = portfolio_paths[:, t-1] * np.exp(drift + diffusion)

    # Percentiller
    portfolio_percentiles = _percentile_values(portfolio_paths, percentiles)

    # Her varlık için de ayrı percentiller (bağımsız GBM)
    asset_final_values = []
    for i, sym in enumerate(asset_symbols):
        asset_paths = _simulate_paths_gbm(
            initial_values[i],
            means[i],
            volds[i],
            days,
            n_simulations,
            seed=None,
        )
        asset_pcts = _percentile_values(asset_paths, percentiles)
        asset_final_values.append({
            "symbol":           sym,
            "initial_value":    round(initial_values[i], 2),
            **asset_pcts,
        })

    return {
        "days":               days,
        "n_simulations":      n_simulations,
        "percentiles":        percentiles,
        "percentile_values":  {
            "portfolio": portfolio_percentiles,
        },
        "asset_names":        asset_symbols,
        "asset_final_values": asset_final_values,
        "total_initial_value": round(total_initial, 2),
    }


# --------------------------------------------------------------------
# 2. Stres Testi
# --------------------------------------------------------------------

def stress_test(
    session: Session,
    portfolio_value: float,
    shocks: Dict[str, float],
    days: int = 252,
    n_simulations: int = 1000,
) -> StressTestResult:
    """
    Makro şok senaryoları altında portföy değerlerini simüle et.

    Şok tipleri:
      - 'interest_rate_shock': Faiz değişimi → volatilite artış
      - 'fx_shock': Döviz kuru şoku → değer değişimi
      - 'inflation_shock': Enflasyon şoku → reel değer düşüş
      - 'market_crash': Piyasa çökmesi → ani değer kaybı

    Args:
        session: SQLAlchemy Session
        portfolio_value: Başlangıç portföy değeri
        shocks: Şok parametreleri (key: şok adı, value: şok büyüklüğü)
        days: Simülasyon süresi
        n_simulations: Kaç patika

    Returns:
        {
            "original_value":   float,
            "stressed_values":  {
                "interest_rate_shock": {"expected_value": ..., "p5": ..., "p50": ..., "p95": ..., "loss_pct": ...},
                ...
            },
            "worst_case":       float,
            "worst_case_name":  str,
        }
    """
    stressed_values = {}

    for shock_name, shock_magnitude in shocks.items():
        if shock_name == "interest_rate_shock":
            stressed_vol = 0.0008 * (1 + shock_magnitude)
            stressed_mean = -0.0001 * shock_magnitude
            paths = _simulate_paths_gbm(portfolio_value, stressed_mean, stressed_vol, days, n_simulations)
            final_values = paths[:, -1]

        elif shock_name == "fx_shock":
            adjusted_value = portfolio_value * (1 - shock_magnitude)
            paths = _simulate_paths_gbm(adjusted_value, 0.0, 0.0008, days, n_simulations)
            final_values = paths[:, -1]

        elif shock_name == "inflation_shock":
            paths = _simulate_paths_gbm(portfolio_value, 0.0, 0.0008, days, n_simulations)
            final_values = paths[:, -1] / (1 + shock_magnitude)

        elif shock_name == "market_crash":
            crash_day = min(10, days // 3)
            paths = _simulate_paths_gbm(portfolio_value, 0.0, 0.0008, days, n_simulations)
            paths[:, crash_day] = paths[:, crash_day] * (1 - shock_magnitude)
            final_values = paths[:, -1]

        else:
            adjusted_value = portfolio_value * (1 - shock_magnitude)
            paths = _simulate_paths_gbm(adjusted_value, 0.0, 0.0008, days, n_simulations)
            final_values = paths[:, -1]

        stressed_values[shock_name] = {
            "expected_value": round(float(np.mean(final_values)), 2),
            "p5":            round(float(np.percentile(final_values, 5)), 2),
            "p50":           round(float(np.percentile(final_values, 50)), 2),
            "p95":           round(float(np.percentile(final_values, 95)), 2),
            "loss_pct":      round(float(np.mean(final_values)) / portfolio_value - 1, 6),
        }

    worst_value = portfolio_value
    worst_name = "none"
    for sn, sv in stressed_values.items():
        if sv["expected_value"] < worst_value:
            worst_value = sv["expected_value"]
            worst_name = sn

    return {
        "original_value":     round(portfolio_value, 2),
        "days":               days,
        "n_simulations":      n_simulations,
        "stressed_values":    stressed_values,
        "worst_case":         round(worst_value, 2),
        "worst_case_name":    worst_name,
    }


# --------------------------------------------------------------------
# 3. AI Risk Anlatısı
# --------------------------------------------------------------------

def generate_risk_narrative(
    simulation_result: MonteCarloResult,
    portfolio_context: Optional[Dict] = None,
    api_key: Optional[str] = None,
) -> str:
    """
    Monte Carlo simülasyon sonuçlarını Türkçe risk/fırsat analiz metnine
    dönüştürür (LLM over Gemini).

    Args:
        simulation_result: monte_carlo_simulation return value
        portfolio_context: Portföy bağlamı (opsiyonel)
        api_key: Gemini API key. None → config.GOOGLE_API_KEY kullanılır.

    Returns:
        Türkçe analiz metni. API key yoksa hata mesajı.
    """
    if api_key is None:
        api_key = config.GOOGLE_API_KEY

    if not api_key:
        return (
            "⚠️ AI Risk Anlatısı üretilemedi: Google API key tanımlı değil. "
            "GOOGLE_API_KEY environment değişkenini ayarlayın."
        )

    pv = simulation_result.get("percentile_values", {}).get("portfolio", {})
    p5 = pv.get("p5", 0)
    p50 = pv.get("p50", 0)
    p95 = pv.get("p95", 0)
    initial = simulation_result.get("total_initial_value", 0)

    gain_pct = ((p50 - initial) / initial * 100) if initial > 0 else 0.0
    days = simulation_result.get("days", 252)

    prompt = f"""
    SEN BİR YATIRIM RISK ANALİSTİSİNSIN.

    VERİLER:
    - Portföy başlangıç değeri: {initial:,.2f} TL
    - {days} günlük Monte Carlo simülasyon ({simulation_result.get('n_simulations', 10000)} patika)
    - %5 güven aralığı (Bear/En kötü): {p5:,.2f} TL
    - %50 güven aralığı (Base/Medyan): {p50:,.2f} TL
    - %95 güven aralığı (Bull/En iyi): {p95:,.2f} TL
    - Ortalama beklenen getiri: %{gain_pct:+.2f}

    GÖREV:
    1. Bu simülasyon sonucunu sade Türkçe bir paragrafta özetle
    2. En iyi, en kötü ve en gerçekçi (medyan) senaryoları açıkla
    3. Portföyün risk profili hakkında genel bir değerlendirme ver
    4. Kesin alım/satım tavsiyesi VERME

    CEVAP FORMATI:
    📊 Simülasyon Özeti:
    [Türkçe özet]

    💡 Senaryolar:
    - En iyi (Bull, %95): ...
    - En gerçekçi (Medyan, %50): ...
    - En kötü (Bear, %5): ...

    🎯 Genel değerlendirme:
    [Risk profili yorumu, kesin yön vermeden]
    """

    try:
        from services.ai_service import DecisionSupportAI
        ai = DecisionSupportAI(api_key=api_key)
        return ai.get_ai_recommendation({"user_question": prompt})
    except Exception as e:
        return f"❌ AI Risk Anlatısı hatası: {e}"
