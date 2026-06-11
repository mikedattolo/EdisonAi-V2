"""Bridges the on-box Brio voice listener to Edison's chat.

The Brio listener (a separate process) transcribes "hey edison ..." commands and
POSTs them here; we run them through the model gateway, store a conversation the
web UI can open, and queue a voice event the UI polls + speaks via the browser."""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from edison_core.schemas import (
    ChatMode,
    ConversationCreate,
    InferenceRequest,
    MessageCreate,
    MessageRole,
    VoiceEvent,
    VoiceStatus,
)
from edison_core.services.conversation_store import ConversationStore
from edison_core.services.model_gateway import ModelGateway


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VoiceBridgeService:
    def __init__(self, conversation_store: ConversationStore, gateway: ModelGateway) -> None:
        self.conversation_store = conversation_store
        self.gateway = gateway
        self._events: list[VoiceEvent] = []
        self._counter = 0
        self._last_ping: datetime | None = None
        self.last_heard_at: str | None = None
        self.last_transcript: str | None = None
        self._lock = threading.Lock()

    def ping(self) -> None:
        self._last_ping = datetime.now(timezone.utc)

    def handle_command(self, transcript: str, source: str = "brio") -> VoiceEvent:
        transcript = transcript.strip()
        self.last_heard_at = _now()
        self.last_transcript = transcript
        self.ping()

        conversation = self.conversation_store.create_conversation(
            ConversationCreate(title=transcript[:60] or "Voice command", mode=ChatMode.CHAT, memory_enabled=True)
        )
        self.conversation_store.add_message(
            conversation.id,
            MessageCreate(role=MessageRole.USER, content=transcript, metadata={"source": f"voice-{source}"}),
        )
        voice_system = (
            "You are Edison, a friendly British AI voice assistant in the style of Jarvis. "
            "Answer in 1-3 short, natural spoken sentences. Be direct and conversational. "
            "Never use markdown, lists, code blocks, or emoji - your reply is read aloud."
        )
        framed = f"{voice_system}\n\nUser: {transcript}\nEdison:"
        try:
            _selection, inference = self.gateway.complete(
                InferenceRequest(
                    prompt=framed,
                    mode=ChatMode.CHAT,
                    preferred_model="local-fast-chat",
                    metadata={"source": f"voice-{source}", "timeout_seconds": 60},
                )
            )
            reply = inference.content if inference.finish_reason not in ("error", "not_configured") else (
                "Sorry, I couldn't process that right now."
            )
            model_id = inference.model_id
        except Exception as error:  # noqa: BLE001
            reply = f"Voice command failed: {error}"
            model_id = None

        self.conversation_store.add_message(
            conversation.id,
            MessageCreate(role=MessageRole.ASSISTANT, content=reply, model=model_id, metadata={"source": f"voice-{source}"}),
        )

        with self._lock:
            self._counter += 1
            event = VoiceEvent(
                id=self._counter,
                source=source,
                transcript=transcript,
                reply=reply,
                conversation_id=conversation.id,
                created_at=_now(),
            )
            self._events.append(event)
            self._events = self._events[-50:]
        return event

    def events_after(self, after: int) -> list[VoiceEvent]:
        with self._lock:
            return [event for event in self._events if event.id > after]

    def status(self) -> VoiceStatus:
        listening = False
        if self._last_ping is not None:
            listening = (datetime.now(timezone.utc) - self._last_ping).total_seconds() < 45
        with self._lock:
            return VoiceStatus(
                listening=listening,
                last_heard_at=self.last_heard_at,
                last_transcript=self.last_transcript,
                event_count=self._counter,
                events=self._events[-10:],
            )
