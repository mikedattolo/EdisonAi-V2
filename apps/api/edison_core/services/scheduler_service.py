"""Background scheduler that runs Edison chat/agent tasks on a cadence.

Ticks once a minute; due tasks are executed against the local model gateway.
Tasks flagged include_briefing get the realtime time/weather context prepended."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from edison_core.schemas import ChatMode, InferenceRequest, ScheduledTaskRecord
from edison_core.services.model_gateway import ModelGateway
from edison_core.services.scheduled_task_store import ScheduledTaskStore

logger = logging.getLogger("edison.scheduler")


class SchedulerService:
    def __init__(self, store: ScheduledTaskStore, gateway: ModelGateway, realtime=None) -> None:
        self.store = store
        self.gateway = gateway
        self.realtime = realtime
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:  # noqa: BLE001 - the scheduler must never die
                logger.exception("scheduler tick failed")
            await asyncio.sleep(60)

    async def _tick(self) -> None:
        due = self.store.due(datetime.now())
        for task in due:
            loop = asyncio.get_event_loop()
            try:
                status, content = await loop.run_in_executor(None, self._run_sync, task)
            except Exception as error:  # noqa: BLE001
                status, content = "error", str(error)[:1000]
            self.store.record_run(task.id, status, content, datetime.now())

    def _run_sync(self, task: ScheduledTaskRecord) -> tuple[str, str]:
        prompt = task.prompt
        if task.include_briefing and self.realtime is not None:
            try:
                summary = self.realtime.summary()
                if summary:
                    prompt = f"Live context for this briefing: {summary}\n\n{task.prompt}"
            except Exception:  # noqa: BLE001
                pass
        _selection, inference = self.gateway.complete(
            InferenceRequest(
                prompt=prompt,
                mode=ChatMode.CHAT,
                metadata={"source": "scheduler", "timeout_seconds": 180},
            )
        )
        if inference.finish_reason in ("error", "not_configured"):
            return ("error", inference.content[:4000])
        return ("complete", inference.content[:4000])

    def run_now(self, task: ScheduledTaskRecord) -> ScheduledTaskRecord:
        try:
            status, content = self._run_sync(task)
        except Exception as error:  # noqa: BLE001
            status, content = "error", str(error)[:1000]
        self.store.record_run(task.id, status, content, datetime.now())
        return self.store.get(task.id)
