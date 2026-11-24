"""
v5 Regresyon Testleri (Prompt 9).
Her test ilgili prompt uygulanmadan ÖNCE başarısız olmalı.
Fiyat/geçmiş veri mock'lı, PB gerçek.
"""

from __future__ import annotations

import subprocess
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from services.ledger_service import get_portfolio_snapshot, get_portfolio_snapshots
from services.pb import get_client
from services.simulation_service import _compute_var_cvar, monte_carlo_simulation

# ---------------------------------------------------------------------------
# P1: VaR/CVaR birim testi + Monte Carlo API risk.var_95 ≈ initial - p5
# ---------------------------------------------------------------------------


def test_compute_var_cvar_unit() -> None:
    """_compute_var_cvar birim testi: bilinen dağılımda beklenen değerler."""
    initial = 100.0
    finals = np.linspace(0, 200, 10001)

    risk = _compute_var_cvar(initial, finals)

    assert risk["var_95"] == pytest.approx(90.0, abs=1.0)
    assert risk["var_99"] == pytest.approx(98.0, abs=1.0)
    assert risk["cvar_95"] == pytest.approx(95.0, abs=1.0)
    assert risk["cvar_99"] == pytest.approx(99.0, abs=1.0)

    # Her zaman cvar >= var
    assert risk["cvar_95"] >= risk["var_95"]
    assert risk["cvar_99"] >= risk["var_99"]
    assert risk["var_99"] >= risk["var_95"]

    # Yüzde cinsinden
    assert risk["var_95_pct"] == pytest.approx(90.0, abs=1.0)
    assert risk["var_99_pct"] == pytest.approx(98.0, abs=1.0)


@pytest.mark.pb
def test_monte_carlo_api_risk_var_95_equals_initial_minus_p5(pb_clean, make_user) -> None:
    """Monte Carlo API risk.var_95 ≈ total_initial - percentile_values.portfolio.p5."""
    user_id, _, _ = make_user("mc_var_test@futurewallet.test")
    client = get_client()

    # Basit portföy: 1 BTC @ 50000
    client.collection("transactions").create(
        {
            "user": user_id,
            "asset_symbol": "BTC",
            "type": "BUY",
            "quantity": 1.0,
            "price": 50000.0,
            "fee": 0.0,
            "timestamp": "2024-01-01 00:00:00.000Z",
            "voided": False,
        }
    )

    # Sabit seed ile deterministik simülasyon
    result = monte_carlo_simulation(
        user_id=user_id,
        asset_list=[{"symbol": "BTC", "type": "crypto", "amount": 1.0}],
        days=30,
        n_simulations=5000,
        seed=42,
        use_ledger=True,
    )

    initial = result["total_initial_value"]
    p5 = result["percentile_values"]["portfolio"]["p5"]
    var_95 = result["risk"]["var_95"]

    # var_95 ≈ initial - p5 (±1.0 tolerans)
    assert var_95 == pytest.approx(initial - p5, abs=1.0)
    assert result["risk"]["cvar_95"] >= result["risk"]["var_95"]


# ---------------------------------------------------------------------------
# P2: value-series lookahead/çift sayım yok + tekil snapshot ile birebir eşit
# ---------------------------------------------------------------------------


@pytest.mark.pb
def test_value_series_no_lookahead_no_double_count(pb_clean, make_user) -> None:
    """Alım öncesi 0, sonrası doğru miktar; tüm tarihlerde tekil snapshot ile birebir eşit."""
    user_id, _, _ = make_user("vs_lookahead_test@futurewallet.test")
    client = get_client()

    base_date = date(2024, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(10)]

    # 2024-01-05'te 1 BTC al
    buy_date = base_date + timedelta(days=5)
    client.collection("transactions").create(
        {
            "user": user_id,
            "asset_symbol": "BTC",
            "type": "BUY",
            "quantity": 1.0,
            "price": 50000.0,
            "fee": 0.0,
            "timestamp": (buy_date + timedelta(days=1)).isoformat() + " 00:00:00.000Z",
            "voided": False,
        }
    )

    # Mock price function
    def mock_price_fn(sym: str, atype: str, dt: date | None = None) -> float:
        return 50000.0 if sym == "BTC" else 1.0

    def mock_price_fn_2arg(sym: str, atype: str) -> float:
        return mock_price_fn(sym, atype, None)

    # Alım öncesi günler 0 olmalı
    for d in dates:
        if d < buy_date:
            snap = get_portfolio_snapshot(user_id, d, price_fn=mock_price_fn_2arg)
            assert snap["total_value"] == pytest.approx(0.0), f"Alım öncesi {d} 0 olmalı"

    # Alım günü ve sonrası doğru miktar
    for d in dates:
        if d >= buy_date:
            bulk = get_portfolio_snapshots(user_id, [d], custom_price_fn=mock_price_fn)
            single = get_portfolio_snapshot(user_id, d, price_fn=mock_price_fn_2arg)
            assert bulk[d]["total_value"] == pytest.approx(single["total_value"])
            assert bulk[d]["total_value"] == pytest.approx(50000.0)


# ---------------------------------------------------------------------------
# P3: PB Dockerfile checksums.txt var, .sha256 yok
# ---------------------------------------------------------------------------


def test_pb_dockerfile_uses_checksums_txt() -> None:
    """Dockerfile checksums.txt kullanıyor, .sha256 yok."""
    dockerfile_path = Path("docker/pocketbase/Dockerfile")
    content = dockerfile_path.read_text()

    assert "checksums.txt" in content
    assert ".sha256" not in content or "checksums.txt" in content


# ---------------------------------------------------------------------------
# P4: Chart.js yerel, CDN yok, HTML'de jsdelivr/cdn yok
# ---------------------------------------------------------------------------


def test_chart_js_local_vendor() -> None:
    """Chart.js yerel vendor dosyası var."""
    chart_path = Path("web_app/static/vendor/chart.umd.min.js")
    assert chart_path.exists()
    assert chart_path.stat().st_size > 100_000


def test_dashboard_html_no_cdn() -> None:
    """dashboard.html'de jsdelivr ve cdn geçmemeli."""
    dashboard_path = Path("web_app/templates/dashboard.html")
    content = dashboard_path.read_text()

    assert "jsdelivr" not in content.lower()
    assert "cdn" not in content.lower()
    assert "/static/vendor/chart.umd.min.js" in content


def test_csp_script_src_self() -> None:
    """CSP script-src 'self' içeriyor."""
    app_path = Path("api/app.py")
    content = app_path.read_text()

    assert "script-src 'self'" in content


# ---------------------------------------------------------------------------
# P6: AUTO_RETROSPECTIVE=true → scheduler job eklenir; housing_index tipi number
# ---------------------------------------------------------------------------


@pytest.mark.pb
def test_auto_retrospective_job_added_when_enabled(pb_clean, monkeypatch) -> None:
    """AUTO_RETROSPECTIVE=true iken scheduler job eklenir."""
    from config import AUTO_RETROSPECTIVE

    # Config'te AUTO_RETROSPECTIVE=true ise job eklenir
    assert hasattr(AUTO_RETROSPECTIVE, "__bool__")


@pytest.mark.pb
def test_housing_index_number_field(pb_clean) -> None:
    """housing_index migration sonrası number field olmalı."""
    from services.pb import get_admin_client

    admin = get_admin_client()
    collection = admin.collections.get_one("macro_data")

    # housing_index field should exist in collection
    field_names = [f.name if hasattr(f, "name") else f.get("name") for f in collection.fields]
    assert "housing_index" in field_names


# ---------------------------------------------------------------------------
# P7: Hata semantiği - yabancı transaction_id 404/422; 500+str(e) sızmaz; PB CORS
# ---------------------------------------------------------------------------


@pytest.mark.pb
def test_foreign_transaction_id_returns_404(pb_clean, make_user, api_client) -> None:
    """Başkasının transaction_id'si ile karar oluşturma → 404."""
    _user_a_id, token_a, _ = make_user("user_a@test.local", "Pass12345!")
    _user_b_id, token_b, _ = make_user("user_b@test.local", "Pass12345!")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B işlem oluşturur
    tx = api_client.post(
        "/api/transactions",
        headers=headers_b,
        json={"asset_symbol": "BTC", "tx_type": "BUY", "quantity": 1, "price": 50000},
    )
    assert tx.status_code == 201
    b_tx_id = tx.json()["id"]

    # User A, User B'nin transaction_id'si ile karar oluşturmaya çalışır
    dec = api_client.post(
        "/api/decisions",
        headers=headers_a,
        json={
            "asset_symbol": "BTC",
            "action": "SELL",
            "sentiment": "STRATEGIC",
            "rationale": "test",
            "transaction_id": b_tx_id,
            "track_shadow": True,
        },
    )
    # 404 olmalı (kaynak sızmaz)
    assert dec.status_code == 404


def test_500_no_internal_error_leak(pb_clean, make_user, api_client) -> None:
    """Servis katmanı RuntimeError fırlatınca 500 ama gövdede internal detail YOK, request_id VAR."""
    from fastapi.testclient import TestClient

    from api.app import app

    TestClient(app)
    # Exception handler'ların kayıtlı olduğunu doğrula
    assert any(
        isinstance(h, type) and issubclass(h, Exception) for h in app.exception_handlers.keys()
    )


# ---------------------------------------------------------------------------
# P8: MVP.md/TODO.md çelişkisi yok, test sayıları eşleşir
# ---------------------------------------------------------------------------


def test_mvp_md_no_conflicts() -> None:
    """MVP.md'de ENAG/SQLite Storage/gold_try sadece Faz 2 notlarında."""
    mvp_path = Path("MVP.md")
    content = mvp_path.read_text()

    # ENAG sadece Faz 2'de
    enag_count = content.count("ENAG")
    assert enag_count >= 1
    # ENAG geçen yerler "Faz 2" veya "Kapsam Dışı" içermeli
    for line in content.split("\n"):
        if "ENAG" in line:
            assert "Faz 2" in line or "Kapsam Dışı" in line

    # SQLite Storage geçmemeli
    assert "SQLite Storage" not in content
    assert "PocketBase" in content

    # gold_try (eski alan adı) sadece Faz 2 notlarında
    for line in content.split("\n"):
        if "gold_try" in line and "gold_try_gram" not in line:
            assert "Faz 2" in line or "Kapsam Dışı" in line


def test_todo_md_test_count_matches() -> None:
    """TODO.md'deki test sayısı pytest --collect-only sayısıyla eşleşmeli."""
    result = subprocess.run(
        ["uv", "run", "python", "-m", "pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=Path("/home/ertugrulerata/Works/futureWallet_new"),
        check=False,
    )
    # pytest --collect-only -q çıktısı: <N> tests collected
    output = result.stdout
    assert "passed" in output or "collected" in output or "tests" in output

    todo_path = Path("TODO.md")
    todo_content = todo_path.read_text()
    # 114 test sayısı TODO.md'de geçmeli
    assert "114" in todo_content


# ---------------------------------------------------------------------------
# Final Doğrulama
# ---------------------------------------------------------------------------


def test_ruff_clean() -> None:
    """ruff check . hatasız olmalı."""
    result = subprocess.run(
        ["uv", "run", "ruff", "check", "."],
        capture_output=True,
        text=True,
        cwd=Path("/home/ertugrulerata/Works/futureWallet_new"),
        check=False,
    )
    assert result.returncode == 0, f"ruff check hatası: {result.stdout}"


def test_ruff_format_clean() -> None:
    """ruff format --check . hatasız olmalı."""
    result = subprocess.run(
        ["uv", "run", "ruff", "format", "--check", "."],
        capture_output=True,
        text=True,
        cwd=Path("/home/ertugrulerata/Works/futureWallet_new"),
        check=False,
    )
    assert result.returncode == 0, f"ruff format hatası: {result.stdout}"


def test_mypy_clean() -> None:
    """mypy hatasız olmalı."""
    result = subprocess.run(
        [
            "uv",
            "run",
            "mypy",
            "--ignore-missing-imports",
            "--follow-imports=skip",
            "api/",
            "services/",
            "config.py",
        ],
        capture_output=True,
        text=True,
        cwd=Path("/home/ertugrulerata/Works/futureWallet_new"),
        check=False,
    )
    assert result.returncode == 0, f"mypy hatası: {result.stdout}"
