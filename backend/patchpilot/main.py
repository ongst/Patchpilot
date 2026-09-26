from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from patchpilot.api import router
from patchpilot.config import get_settings
from patchpilot.db import RunStore
from patchpilot.service import RunService
from patchpilot.workflow import WorkflowEngine


def create_app() -> FastAPI:
    settings = get_settings()
    store = RunStore(settings.database_path)
    workflow = WorkflowEngine(settings, store)
    service = RunService(settings, store, workflow)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        workflow.close()

    app = FastAPI(
        title="PatchPilot API",
        version="0.1.0",
        description="Human-approved code repair agent for public Python and npm repositories.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.settings = settings
    app.state.store = store
    app.state.workflow = workflow
    app.state.service = service
    app.include_router(router)
    return app


app = create_app()


def run() -> None:
    uvicorn.run("patchpilot.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
