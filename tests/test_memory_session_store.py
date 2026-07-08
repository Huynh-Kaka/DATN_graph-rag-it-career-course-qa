import asyncio

from app.session.memory_store import MemorySessionStore


async def _run() -> None:
    store = MemorySessionStore()
    state = await store.get_or_create(None)
    assert state.session_id

    await store.append_message(state, "user", "Xin chào")
    await store.append_message(state, "assistant", "Chào bạn!")
    await store.save(state)

    loaded = await store.get_or_create(state.session_id)
    assert len(loaded.messages) == 2
    assert loaded.messages[0].role == "user"

    history = await store.list_messages(state.session_id)
    assert len(history) == 2


def test_memory_session_store_async():
    asyncio.run(_run())
