from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from edison_core.api.dependencies import get_agent_run_store
from edison_core.schemas import (
    AgentRunCreate,
    AgentRunEventCreate,
    AgentRunEventRecord,
    AgentRunRecord,
    AgentRunStatusUpdate,
    AgentRunWithEvents,
)
from edison_core.services.agent_run_store import AgentRunNotFoundError, AgentRunStore


router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.get("/runs", response_model=list[AgentRunRecord])
def list_agent_runs(
    limit: int = Query(default=50, ge=1, le=200),
    store: AgentRunStore = Depends(get_agent_run_store),
) -> list[AgentRunRecord]:
    return store.list_runs(limit)


@router.post("/runs", response_model=AgentRunWithEvents, status_code=status.HTTP_201_CREATED)
def create_agent_run(
    payload: AgentRunCreate,
    store: AgentRunStore = Depends(get_agent_run_store),
) -> AgentRunWithEvents:
    return store.create_run(payload)


@router.get("/runs/{run_id}", response_model=AgentRunWithEvents)
def get_agent_run(
    run_id: str,
    store: AgentRunStore = Depends(get_agent_run_store),
) -> AgentRunWithEvents:
    try:
        return store.get_run(run_id)
    except AgentRunNotFoundError as error:
        raise HTTPException(status_code=404, detail="Agent run not found") from error


@router.post("/runs/{run_id}/events", response_model=AgentRunEventRecord, status_code=status.HTTP_201_CREATED)
def add_agent_run_event(
    run_id: str,
    payload: AgentRunEventCreate,
    store: AgentRunStore = Depends(get_agent_run_store),
) -> AgentRunEventRecord:
    try:
        return store.add_event(run_id, payload)
    except AgentRunNotFoundError as error:
        raise HTTPException(status_code=404, detail="Agent run not found") from error


@router.put("/runs/{run_id}/status", response_model=AgentRunWithEvents)
def update_agent_run_status(
    run_id: str,
    payload: AgentRunStatusUpdate,
    store: AgentRunStore = Depends(get_agent_run_store),
) -> AgentRunWithEvents:
    try:
        return store.update_run_status(run_id, payload)
    except AgentRunNotFoundError as error:
        raise HTTPException(status_code=404, detail="Agent run not found") from error
