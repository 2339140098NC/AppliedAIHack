"""FastAPI entrypoint for the case board."""

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from caseboard.clio.client import ClioClient
from caseboard.config import ROOT, Settings
from caseboard.store.factory import open_store, open_tokens
from caseboard.web.actions import Actions
from caseboard.web.jobs import Job
from caseboard.web.routes import router


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or Settings()
    app = FastAPI(title="Proximate")
    app.state.settings = current
    app.state.store = open_store(current)
    app.state.clio = ClioClient(current, open_tokens(current))
    app.state.job = Job()
    app.state.actions = Actions(current, app.state.store, app.state.clio, app.state.job)
    app.mount("/static", StaticFiles(directory=ROOT / "caseboard" / "static"), name="static")
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    uvicorn.run("caseboard.main:app", host="127.0.0.1", port=8765, reload=False)
