from edison_core.database import SQLiteDatabase
from edison_core.schemas import ChatMode, ConversationCreate, MessageCreate, MessageRole, SessionStateUpdate
from edison_core.services.conversation_store import ConversationStore
from edison_core.services.session_state import SessionStateStore


def test_conversation_messages_persist(tmp_path):
    database = SQLiteDatabase(tmp_path / "edison.sqlite3")
    store = ConversationStore(database)
    store.initialize()

    conversation = store.create_conversation(
        ConversationCreate(title="Architecture pass", mode=ChatMode.REASONING)
    )
    message = store.add_message(
        conversation.id,
        MessageCreate(
            role=MessageRole.USER,
            content="Map the first EDISON V2 services.",
            metadata={"source": "test"},
        ),
    )

    loaded = store.get_conversation(conversation.id)

    assert loaded.id == conversation.id
    assert loaded.mode == ChatMode.REASONING
    assert loaded.messages[0].id == message.id
    assert loaded.messages[0].metadata == {"source": "test"}


def test_session_state_updates_are_durable(tmp_path):
    database = SQLiteDatabase(tmp_path / "edison.sqlite3")
    store = SessionStateStore(database)
    store.initialize()

    updated = store.update(
        "session-main",
        SessionStateUpdate(
            current_task="Build the V2 foundation",
            current_plan=["audit", "scaffold", "validate"],
            selected_mode=ChatMode.CODING,
            selected_model="local-coding",
        ),
    )

    loaded = store.get_or_create("session-main")

    assert updated.current_task == "Build the V2 foundation"
    assert loaded.current_plan == ["audit", "scaffold", "validate"]
    assert loaded.selected_mode == ChatMode.CODING
    assert loaded.selected_model == "local-coding"