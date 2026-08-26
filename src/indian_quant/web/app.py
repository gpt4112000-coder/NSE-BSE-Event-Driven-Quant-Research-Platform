"""FastAPI web dashboard for the NSE-BSE quant platform."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from indian_quant.web import data_loader as dl

app = FastAPI(title="NSE-BSE Quant Platform", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    papers = dl.get_paper_summary()
    gate = dl.get_gate_progress()
    signals = dl.get_latest_signals()
    return templates.TemplateResponse(request, "dashboard.html", {
        "papers": papers,
        "gate": gate,
        "signals": signals,
    })


@app.get("/signals", response_class=HTMLResponse)
async def signals_page(request: Request):
    signals = dl.get_latest_signals()
    return templates.TemplateResponse(request, "signals.html", {
        "signals": signals,
    })


@app.get("/positions", response_class=HTMLResponse)
async def positions_page(request: Request):
    papers = dl.get_paper_summary()
    gate = dl.get_gate_progress()
    return templates.TemplateResponse(request, "positions.html", {
        "papers": papers,
        "gate": gate,
    })


@app.get("/research", response_class=HTMLResponse)
async def research_page(request: Request):
    research = dl.get_research_results()
    return templates.TemplateResponse(request, "research.html", {
        "research": research,
    })


@app.get("/announcements/{symbol}", response_class=HTMLResponse)
async def announcements_page(request: Request, symbol: str):
    announcements = dl.get_announcements(symbol.upper())
    available = dl.get_available_announcement_symbols()
    return templates.TemplateResponse(request, "announcements.html", {
        "symbol": symbol.upper(),
        "announcements": announcements,
        "available_symbols": available,
    })


@app.get("/api/signals")
async def api_signals():
    return JSONResponse(dl.get_latest_signals())


@app.get("/api/papers")
async def api_papers():
    return JSONResponse(dl.get_paper_summary())


@app.get("/api/gate")
async def api_gate():
    return JSONResponse(dl.get_gate_progress())


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
