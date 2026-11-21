"""Sertleştirme regresyon testleri (v4). Her biri ilgili düzeltmeden önce başarısız olmalıdır."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

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
    from services.ai_service import AIGenerationError, reset_ai_rate_limits

    reset_ai_rate_limits()
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
    assert "POCKETBASE_PUBLIC_URL" in env
    ign = (ROOT / ".dockerignore").read_text()
    for needle in ("pb_data", "pb_bin", "pb_test_data", "tests", "docs"):
        assert needle in ign


def test_login_meta_uses_public_pb_url(api_client, monkeypatch):
    import config
    monkeypatch.setattr(config, "POCKETBASE_PUBLIC_URL", "http://localhost:8080", raising=False)
    html = api_client.get("/web/login").text
    assert 'content="http://localhost:8080"' in html and "pocketbase:8090" not in html
