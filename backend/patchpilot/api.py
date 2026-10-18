from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from patchpilot import __version__
from patchpilot.models import (
    DecisionRequest,
    DiffResponse,
    HealthResponse,
    RunCreate,
    RunEvent,
    RunRecord,
    RunReport,
)
from patchpilot.patching import parse_patch_summary
from patchpilot.reporting import build_run_report

router = APIRouter(prefix="/api")


def _service(request: Request):
    return request.app.state.service


def _store(request: Request):
    return request.app.state.store


def _safe_cursor(value: str | None) -> int:
    """将游标字符串转换为非负整数，若无效则返回 0。"""
    if value is None:
        return 0
    try:
        number = int(value)
    except ValueError:
        return 0
    if number < 0:
        return 0
    return number


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    service = _service(request)
    database = _store(request).ping()
    docker = service.workflow.runner.available()
    llm = service.workflow.llm.configured
    git_available = shutil.which("git") is not None
    ready_for_repair = database and docker and llm and git_available
    ready_for_push = ready_for_repair and bool(service.settings.github_token)
    return HealthResponse(
        status="ok" if ready_for_repair else "degraded",
        database=database,
        git=git_available,
        docker=docker,
        llm_configured=llm,
        ready_for_repair=ready_for_repair,
        ready_for_push=ready_for_push,
        version=__version__,
    )


@router.post("/runs", response_model=RunRecord, status_code=202)
def create_run(payload: RunCreate, request: Request) -> RunRecord:
    try:
        return _service(request).create(payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/runs", response_model=list[RunRecord])
def list_runs(request: Request, limit: int = Query(default=30, ge=1, le=100)) -> list[RunRecord]:
    return _store(request).list_runs(limit)


@router.get("/runs/{run_id}", response_model=RunRecord)
def get_run(run_id: str, request: Request) -> RunRecord:
    run = _store(request).get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/diff", response_model=DiffResponse)
def get_diff(run_id: str, request: Request) -> DiffResponse:
    run = get_run(run_id, request)
    files = parse_patch_summary(run.patch)
    additions = sum(f.additions for f in files)
    deletions = sum(f.deletions for f in files)
    return DiffResponse(
        run_id=run_id,
        patch=run.patch,
        files=files,
        additions=additions,
        deletions=deletions,
        changed_lines=additions + deletions,
    )


@router.get("/runs/{run_id}/report", response_model=RunReport)
def get_report(run_id: str, request: Request) -> RunReport:
    run = get_run(run_id, request)
    if not run.status.terminal:
        raise HTTPException(status_code=409, detail="Run is not finished yet")
    return build_run_report(run)


@router.post("/runs/{run_id}/decisions", response_model=RunRecord, status_code=202)
def decide(run_id: str, payload: DecisionRequest, request: Request) -> RunRecord:
    try:
        return _service(request).decide(run_id, payload)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Run not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/runs/{run_id}/cancel", response_model=RunRecord)
def cancel(run_id: str, request: Request) -> RunRecord:
    try:
        return _service(request).cancel(run_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Run not found") from error


@router.get("/runs/{run_id}/events")
def events(run_id: str, request: Request, after: int = Query(default=0, ge=0)) -> StreamingResponse:
    if _store(request).get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")

    async def stream() -> AsyncIterator[str]:
        last_event_id = _safe_cursor(request.headers.get("Last-Event-ID"))
        cursor = max(after, last_event_id)
        idle_ticks = 0
        while True:
            if await request.is_disconnected():
                break
            batch: list[RunEvent] = _store(request).get_events(run_id, cursor)
            for event in batch:
                cursor = event.id
                yield f"id: {event.id}\nevent: {event.event_type}\ndata: {event.model_dump_json()}\n\n"
            run = _store(request).get_run(run_id)
            if run is None or run.status.terminal:
                yield f"event: end\ndata: {json.dumps({'status': run.status.value if run else 'missing'})}\n\n"
                break
            if batch:
                idle_ticks = 0
            else:
                idle_ticks += 1
            if idle_ticks % 20 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")
