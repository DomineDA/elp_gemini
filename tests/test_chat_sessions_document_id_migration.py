"""chat_sessions.document_id column migration tests (#175)."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.migrations.chat_sessions_document_id import (
    ensure_chat_sessions_document_id_column,
)

PATH = "fileSearchStores/s1/documents/d1"


@pytest.fixture
async def legacy_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE chat_sessions (id INTEGER PRIMARY KEY, "
                "user_id INTEGER NOT NULL, title VARCHAR(255))"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO chat_sessions (id, user_id, title) "
                f"VALUES (1, 1, '{PATH}'), (2, 1, '내 수업')"
            )
        )
    yield engine
    await engine.dispose()


def _schema(sync_conn):
    inspector = inspect(sync_conn)
    columns = {c["name"] for c in inspector.get_columns("chat_sessions")}
    indexes = {i["name"] for i in inspector.get_indexes("chat_sessions")}
    return columns, indexes


async def _document_ids(engine):
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT id, document_id FROM chat_sessions ORDER BY id")
        )
        return dict(rows.all())


async def test_adds_column_index_and_backfills_path_titles(legacy_engine):
    added = await ensure_chat_sessions_document_id_column(legacy_engine)

    assert added is True
    async with legacy_engine.connect() as conn:
        columns, indexes = await conn.run_sync(_schema)
    assert "document_id" in columns
    assert "idx_chat_sessions_document_id" in indexes
    assert await _document_ids(legacy_engine) == {1: PATH, 2: None}


async def test_second_run_is_idempotent(legacy_engine):
    await ensure_chat_sessions_document_id_column(legacy_engine)

    added = await ensure_chat_sessions_document_id_column(legacy_engine)

    assert added is False
    assert await _document_ids(legacy_engine) == {1: PATH, 2: None}


async def test_missing_table_is_skipped():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool
    )
    try:
        assert await ensure_chat_sessions_document_id_column(engine) is False
    finally:
        await engine.dispose()
