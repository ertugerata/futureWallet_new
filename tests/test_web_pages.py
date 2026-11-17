"""Web sayfa sözleşmesi testleri (P14): /web/login, /web/, statikler, CSP uyumu."""

from __future__ import annotations

from fastapi import status

CHART_SRI = "sha384-e6nUZLBkQ86NJ6TVVKAeSaK8jWa3NhkYWZFomE39AvDbQWeie9PlQqM3pmYW5d1g"


def test_login_page_served(api_client) -> None:
    resp = api_client.get("/web/login")
    assert resp.status_code == status.HTTP_200_OK
    html = resp.text
    assert 'name="pb-base"' in html, "pbBase enjekte edilmeli"
    assert 'id="loginForm"' in html
    assert "/static/login.js" in html


def test_dashboard_has_sri_panels_and_disclaimer(api_client) -> None:
    resp = api_client.get("/web/")
    assert resp.status_code == status.HTTP_200_OK
    html = resp.text
    assert CHART_SRI in html, "Chart.js SRI ile yüklenmeli"
    assert 'id="currencySelect"' in html
    assert 'id="transactions"' in html
    assert 'id="shadowForm"' in html
    assert 'id="btnStress"' in html
    assert 'class="disclaimer"' in html


def test_static_assets_served(api_client) -> None:
    for path in (
        "/static/app.js",
        "/static/login.js",
        "/static/decision_form.js",
        "/static/style.css",
    ):
        resp = api_client.get(path)
        assert resp.status_code == status.HTTP_200_OK, path


def test_csp_header_blocks_inline_style(api_client) -> None:
    """CSP policy'sinde 'unsafe-inline' style/script olmamalı; sayfalarda inline style= yok."""
    resp = api_client.get("/web/")
    csp = resp.headers.get("content-security-policy", "")
    assert "style-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert "connect-src 'self' http://127.0.0.1:8090" in csp, "PB origin connect-src'te olmalı"
    assert 'style="' not in resp.text, "dashboard inline style içermemeli (CSP ihlali)"


def test_csp_header_decision_form(api_client) -> None:
    resp = api_client.get("/web/decisions/new")
    assert resp.status_code == status.HTTP_200_OK
    assert 'style="' not in resp.text
    assert "/static/decision_form.js" in resp.text
