"""Dashboard pages and the three live actions."""

import html
import threading
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from caseboard.clio.tokens import SESSION_COOKIE
from caseboard.domain.enums import DocType
from caseboard.domain.models import Finding
from caseboard.errors import CaseboardError
from caseboard.web.pages import find_pdf, render_page
from caseboard.web.workspace import Workspace, parse_query

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()


def _context(request: Request, *, refresh: bool = False) -> dict:
    board = Workspace(request.app.state.store, parse_query(request))
    settings = request.app.state.settings
    payload = board.context()
    payload.update(
        {
            "gemini_ready": settings.gemini_ready,
            "clio_ready": settings.clio_ready,
            "clio_connected": request.app.state.clio.connected(),
            "job": request.app.state.job.snapshot(),
            "refresh": refresh,
        }
    )
    return payload


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    _open_session(request)
    response = TEMPLATES.TemplateResponse(request, "dashboard.html", _context(request))
    return _keep_session(response, request)


@router.get("/partials/stage", response_class=HTMLResponse)
def stage(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, "partials/stage_response.html", _context(request))


@router.get("/partials/viewer", response_class=HTMLResponse)
def viewer(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, "partials/viewer.html", _context(request))


@router.get("/partials/status", response_class=HTMLResponse)
def status(request: Request) -> HTMLResponse:
    _open_session(request)
    response = TEMPLATES.TemplateResponse(request, "partials/status.html", _status_context(request))
    return _keep_session(response, request)


@router.get("/pages")
def page_image(request: Request, document: str, page: int = 1) -> Response:
    path = find_pdf(request.app.state.settings, document)
    png, _scanned, _count = render_page(path, page)
    return Response(content=png, media_type="image/png")


@router.post("/findings/{finding_id}/resolved", response_class=HTMLResponse)
def toggle_finding(request: Request, finding_id: str) -> HTMLResponse:
    store = request.app.state.store
    for row in store.list_type(DocType.validation):
        if row["id"] != finding_id:
            continue
        finding = Finding.model_validate(row)
        finding.resolved = not finding.resolved
        store.put(DocType.validation, finding.id, finding)
        break
    return TEMPLATES.TemplateResponse(request, "partials/stage_response.html", _context(request))


@router.post("/actions/extract", response_class=HTMLResponse)
def extract(request: Request) -> HTMLResponse:
    return _start(request, "extract", request.app.state.actions.extract)


@router.post("/actions/sync", response_class=HTMLResponse)
def sync(request: Request) -> HTMLResponse:
    return _start(request, "sync", request.app.state.actions.sync)


@router.post("/actions/validate", response_class=HTMLResponse)
def validate(request: Request) -> HTMLResponse:
    _open_session(request)
    try:
        request.app.state.actions.validate()
    except CaseboardError as exc:
        return HTMLResponse(_error(exc), status_code=409)
    response = TEMPLATES.TemplateResponse(
        request,
        "partials/status.html",
        _status_context(request, refresh=True),
    )
    return _keep_session(response, request)


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
    response = RedirectResponse("/", status_code=303)
    return _keep_session(response, request)


def _status_context(request: Request, *, refresh: bool = False) -> dict:
    return {"job": request.app.state.job.snapshot(), "refresh": refresh}


def _open_session(request: Request) -> None:
    request.app.state.clio.tokens.adopt(request.cookies.get(SESSION_COOKIE))


def _keep_session(response: Response, request: Request) -> Response:
    raw = request.app.state.clio.tokens.export()
    if not raw:
        return response
    response.set_cookie(
        SESSION_COOKIE,
        raw,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return response


def _start(request: Request, name: str, target) -> HTMLResponse:
    _open_session(request)
    job = request.app.state.job
    try:
        job.start(name)
    except CaseboardError as exc:
        return HTMLResponse(_error(exc), status_code=409)
    threading.Thread(target=target, daemon=True).start()
    return status(request)


def _error(exc: CaseboardError) -> str:
    return f"<p class='error'>{html.escape(str(exc))}</p>"
