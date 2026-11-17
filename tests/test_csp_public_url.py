"""POCKETBASE_PUBLIC_URL: tarayicinin erisebildigi PB origin'i CSP connect-src'ye ve
login sayfasindaki pb-base meta'sina servis-ici URL yerine bunu yazmali (docker
compose'ta POCKETBASE_URL=http://pocketbase:8090 host tarayicidan cozulemez)."""

from __future__ import annotations

import pytest

import config as cfg


@pytest.mark.pb
def test_public_pb_url_drives_csp_and_page(api_client, pb_server, monkeypatch) -> None:
    monkeypatch.setattr(cfg, "POCKETBASE_URL", "http://pocketbase:8090")
    monkeypatch.setattr(cfg, "POCKETBASE_PUBLIC_URL", "http://127.0.0.1:8080")

    r = api_client.get("/web/login")
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    assert "http://127.0.0.1:8080" in csp
    assert "pocketbase:8090" not in csp
    assert 'content="http://127.0.0.1:8080"' in r.text


@pytest.mark.pb
def test_public_pb_url_falls_back_to_service_url(api_client, pb_server, monkeypatch) -> None:
    monkeypatch.setattr(cfg, "POCKETBASE_URL", "http://localhost:8080")
    monkeypatch.setattr(cfg, "POCKETBASE_PUBLIC_URL", "")

    r = api_client.get("/web/login")
    assert "http://localhost:8080" in r.headers["content-security-policy"]
    assert 'content="http://localhost:8080"' in r.text
