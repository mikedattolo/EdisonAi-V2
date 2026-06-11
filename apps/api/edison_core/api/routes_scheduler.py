from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from edison_core.api.dependencies import get_scheduled_task_store, get_scheduler_service
from edison_core.schemas import (
    ScheduledTaskCreate,
    ScheduledTaskRecord,
    ScheduledTasksStatus,
    ScheduledTaskUpdate,
)
from edison_core.services.scheduled_task_store import ScheduledTaskNotFoundError, ScheduledTaskStore
from edison_core.services.scheduler_service import SchedulerService

router = APIRouter(prefix="/api/v1/scheduler", tags=["scheduler"])


@router.get("/tasks", response_model=ScheduledTasksStatus)
def list_tasks(store: ScheduledTaskStore = Depends(get_scheduled_task_store)) -> ScheduledTasksStatus:
    return ScheduledTasksStatus(server_time=datetime.now().isoformat(), tasks=store.list())


@router.post("/tasks", response_model=ScheduledTaskRecord)
def create_task(
    payload: ScheduledTaskCreate,
    store: ScheduledTaskStore = Depends(get_scheduled_task_store),
) -> ScheduledTaskRecord:
    return store.create(payload)


@router.patch("/tasks/{task_id}", response_model=ScheduledTaskRecord)
def update_task(
    task_id: str,
    payload: ScheduledTaskUpdate,
    store: ScheduledTaskStore = Depends(get_scheduled_task_store),
) -> ScheduledTaskRecord:
    try:
        return store.update(task_id, payload)
    except ScheduledTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Scheduled task not found")


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, store: ScheduledTaskStore = Depends(get_scheduled_task_store)) -> dict:
    store.delete(task_id)
    return {"status": "deleted", "id": task_id}


@router.post("/tasks/{task_id}/run", response_model=ScheduledTaskRecord)
def run_task(
    task_id: str,
    store: ScheduledTaskStore = Depends(get_scheduled_task_store),
    scheduler: SchedulerService = Depends(get_scheduler_service),
) -> ScheduledTaskRecord:
    try:
        task = store.get(task_id)
    except ScheduledTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return scheduler.run_now(task)
