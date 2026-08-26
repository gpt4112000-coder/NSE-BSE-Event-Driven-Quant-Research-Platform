"""FastAPI web dashboard for the NSE-BSE quant platform."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from indian_quant.web import data_loader as dl
from indian_quant.web import suggestion_loader as sl

app = FastAPI(title="NSE-BSE Quant Platform", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    papers = dl.get_paper_summary()
    gate = dl.get_gate_progress()
    signals = dl.get_latest_signals()
    sugg = sl.get_suggestion_summary()
    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "papers": papers,
        "gate": gate,
        "signals": signals,
        "sugg": sugg,
    })


@app.get("/signals", response_class=HTMLResponse)
async def signals_page(request: Request):
    signals = dl.get_latest_signals()
    return templates.TemplateResponse(request, "signals.html", {
        "request": request,
        "signals": signals,
    })


@app.get("/positions", response_class=HTMLResponse)
async def positions_page(request: Request):
    papers = dl.get_paper_summary()
    gate = dl.get_gate_progress()
    return templates.TemplateResponse(request, "positions.html", {
        "request": request,
        "papers": papers,
        "gate": gate,
    })


@app.get("/research", response_class=HTMLResponse)
async def research_page(request: Request):
    research = dl.get_research_results()
    return templates.TemplateResponse(request, "research.html", {
        "request": request,
        "research": research,
    })


@app.get("/suggestions", response_class=HTMLResponse)
async def suggestions_page(request: Request):
    settings = dl._settings()
    from indian_quant.storage import MetadataStore
    md = MetadataStore(settings.storage.metadata_dsn)
    summary = md.suggestions_summary()
    # Get recent suggestions grouped by date
    import sqlite3 as _sq
    con = _sq.connect(str(Path(settings.storage.metadata_dsn.removeprefix("sqlite:///"))))
    con.row_factory = _sq.Row
    recent = [dict(r) for r in con.execute(
        "SELECT * FROM daily_suggestions ORDER BY suggestion_date DESC, symbol LIMIT 100"
    ).fetchall()]
    by_type = [dict(r) for r in con.execute(
        """SELECT signal_type, COUNT(*) n, AVG(actual_return_bps) avg_net,
           SUM(hit)*1.0/COUNT(*)*100 accuracy
           FROM daily_suggestions WHERE status='REALIZED'
           GROUP BY signal_type ORDER BY avg_net DESC"""
    ).fetchall()]
    con.close()

    return templates.TemplateResponse(request, "suggestions.html", {
        "request": request,
        "summary": summary,
        "recent": recent,
        "by_type": by_type,
    })


@app.get("/announcements/{symbol}", response_class=HTMLResponse)
async def announcements_page(request: Request, symbol: str):
    announcements = dl.get_announcements(symbol.upper())
    available = dl.get_available_announcement_symbols()
    return templates.TemplateResponse(request, "announcements.html", {
        "request": request,
        "symbol": symbol.upper(),
        "announcements": announcements,
        "available_symbols": available,
    })


# --- JSON API endpoints ---

@app.get("/api/signals")
async def api_signals():
    return JSONResponse(dl.get_latest_signals())


@app.get("/api/papers")
async def api_papers():
    return JSONResponse(dl.get_paper_summary())


@app.get("/api/gate")
async def api_gate():
    return JSONResponse(dl.get_gate_progress())


@app.get("/api/suggestions")
async def api_suggestions():
    settings = dl._settings()
    from indian_quant.storage import MetadataStore
    md = MetadataStore(settings.storage.metadata_dsn)
    return JSONResponse(md.suggestions_summary())


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
