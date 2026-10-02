"""Dashboard pages and the three live actions."""

import html
import threading
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from caseboard.domain.enums import Audience
from caseboard.errors import CaseboardError
from caseboard.web.present import finding_rows, group_rows, timeline_rows

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()


def _audience(value: str | None) -> Audience:
    if value == Audience.provider.value:
        return Audience.provider
    return Audience.firm


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, audience: str = "firm") -> HTMLResponse:
    chosen = _audience(audience)
    settings = request.app.state.settings
    return TEMPLATES.TemplateResponse(
        request,
        "dashboard.html",
        {
            "audience": chosen.value,
            "gemini_ready": settings.gemini_ready,
            "clio_ready": settings.clio_ready,
            "clio_connected": request.app.state.clio.connected(),
            "counts": request.app.state.store.counts(),
        },
    )


@router.get("/partials/timeline", response_class=HTMLResponse)
def timeline(request: Request, audience: str = "firm") -> HTMLResponse:
    chosen = _audience(audience)
    return TEMPLATES.TemplateResponse(
        request,
        "partials/timeline.html",
        {"events": timeline_rows(request.app.state.store, chosen), "audience": chosen.value},
    )


@router.get("/partials/groups", response_class=HTMLResponse)
def groups(request: Request, audience: str = "firm") -> HTMLResponse:
    chosen = _audience(audience)
    return TEMPLATES.TemplateResponse(
        request,
        "partials/groups.html",
        {"groups": group_rows(request.app.state.store, chosen), "audience": chosen.value},
    )


@router.get("/partials/findings", response_class=HTMLResponse)
def findings(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "partials/findings.html",
        {"findings": finding_rows(request.app.state.store)},
    )


@router.get("/partials/status", response_class=HTMLResponse)
def status(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "partials/status.html",
        {
            "job": request.app.state.job.snapshot(),
            "counts": request.app.state.store.counts(),
        },
    )


@router.post("/actions/extract", response_class=HTMLResponse)
def extract(request: Request) -> HTMLResponse:
    return _start(request, "extract", request.app.state.actions.extract)


@router.post("/actions/sync", response_class=HTMLResponse)
def sync(request: Request) -> HTMLResponse:
    return _start(request, "sync", request.app.state.actions.sync)


@router.post("/actions/validate", response_class=HTMLResponse)
def validate(request: Request) -> HTMLResponse:
    try:
        request.app.state.actions.validate()
    except CaseboardError as exc:
        return HTMLResponse(_error(exc), status_code=409)
    return findings(request)


@router.get("/clio/connect", response_model=None)
def clio_connect(request: Request) -> RedirectResponse | HTMLResponse:
    try:
        url = request.app.state.clio.authorize_url()
    except CaseboardError as exc:
        return HTMLResponse(_error(exc), status_code=400)
    return RedirectResponse(url)


@router.get("/clio/callback", response_model=None)
@router.get("/callback", response_model=None)
def clio_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse | HTMLResponse:
    try:
        request.app.state.clio.exchange(code, state)
    except CaseboardError as exc:
        return HTMLResponse(_error(exc), status_code=400)
    return RedirectResponse("/", status_code=303)


def _start(request: Request, name: str, target) -> HTMLResponse:
    job = request.app.state.job
    try:
        job.start(name)
    except CaseboardError as exc:
        return HTMLResponse(_error(exc), status_code=409)
    threading.Thread(target=target, daemon=True).start()
    return status(request)


def _error(exc: CaseboardError) -> str:
    return f"<p class='error'>{html.escape(str(exc))}</p>"
