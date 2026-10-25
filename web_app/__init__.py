"""
FutureWallet Web Dashboard - FastAPI Jinja2 Templates
"""

from fastapi import Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "web_app" / "templates"
STATIC_DIR  = PROJECT_ROOT / "web_app" / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def mount_web(app):
    """
    FastAPI uygulamasına web dashboard mount'ları ekler.
    Arayüz: mount_web(app) → app.mount("/static", ...) ve @app.get("/web/")
    """
    # Statik dosyalar (CSS, JS, CDN bağımlı değil)
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="static",
    )

    @app.get("/web/", response_class=HTMLResponse)
    async def web_dashboard(request: Request):
        """Ana dashboard sayfası: 4 panel + Chart.js ile API entegrasyonu."""
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request},
        )

    @app.get("/web/decisions/new", response_class=HTMLResponse)
    async def web_decision_new(request: Request):
        """Karar giriş sayfası (modal alternatifi)."""
        return templates.TemplateResponse(
            "decision_form.html",
            {"request": request},
        )
