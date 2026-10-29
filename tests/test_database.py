"""Tests for SQLite database service using pytest.

All tests utilize temporary database files via pytest's tmp_path fixture,
ensuring the development database is never touched.
"""

from pathlib import Path
import sqlite3
import pytest

from services.database import (
    init_db,
    insert_item,
    insert_items,
    get_items,
    get_item_by_id,
    count_items,
    update_read_status,
    update_bookmark_status,
    get_connection,
)


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    """Provides a fresh isolated temporary database path with initialized schema."""
    db_file = tmp_path / "test_ai_pulse.db"
    init_db(db_file)
    return db_file


def test_init_db_creates_table_and_indexes(test_db_path: Path):
    """Verifies that init_db creates intelligence_items table and indices."""
    conn = get_connection(test_db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='intelligence_items';"
        )
        assert cursor.fetchone() is not None

        # Check unique constraint index exists
        cursor.execute("PRAGMA index_list('intelligence_items');")
        indices = [row["name"] for row in cursor.fetchall()]
        assert any("uq_source_source_id" in idx or "idx" in idx for idx in indices)
    finally:
        conn.close()


def test_automatic_creation_of_missing_parent_directory(tmp_path: Path):
    """Verifies that database functions automatically create deeply nested parent directories."""
    deep_db = tmp_path / "nested" / "sub_dir" / "deep_pulse.db"
    assert not deep_db.parent.exists()

    init_db(deep_db)

    assert deep_db.parent.exists()
    assert deep_db.is_file()


def test_successful_insertion_and_retrieval(test_db_path: Path):
    """Verifies inserting a single item and retrieving it by ID."""
    sample_item = {
        "source": "arxiv",
        "source_id": "2401.12345",
        "domain": "AI research",
        "title": "Reasoning Capabilities of Modern LLMs",
        "url": "https://arxiv.org/abs/2401.12345",
        "text": "Exploration of chain-of-thought paradigms.",
        "published_at": "2026-01-15T10:00:00Z",
        "fetched_at": "2026-01-15T11:00:00Z",
        "summary": None,
        "relevance_score": 4,
        "relevance_reason": "High relevance to agent reasoning",
        "is_read": 0,
        "is_bookmarked": 1,
    }

    item_id = insert_item(sample_item, db_path=test_db_path)
    assert item_id is not None
    assert isinstance(item_id, int)

    retrieved = get_item_by_id(item_id, db_path=test_db_path)
    assert retrieved is not None
    assert retrieved["id"] == item_id
    assert retrieved["source"] == "arxiv"
    assert retrieved["source_id"] == "2401.12345"
    assert retrieved["domain"] == "AI research"
    assert retrieved["title"] == "Reasoning Capabilities of Modern LLMs"
    assert retrieved["url"] == "https://arxiv.org/abs/2401.12345"
    assert retrieved["relevance_score"] == 4
    assert retrieved["is_read"] == 0
    assert retrieved["is_bookmarked"] == 1
    assert retrieved["created_at"] is not None


def test_insert_multiple_items_in_transaction(test_db_path: Path):
    """Verifies safe batch insertion of multiple items within a single transaction."""
    items = [
        {
            "source": "cisa",
            "source_id": f"CVE-2026-{1000 + i}",
            "domain": "cybersecurity",
            "title": f"Vulnerability Disclosure {i}",
            "url": f"https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2026-{1000 + i}",
            "text": "Critical remote code execution advisory.",
        }
        for i in range(5)
    ]

    inserted_count = insert_items(items, db_path=test_db_path)
    assert inserted_count == 5
    assert count_items(db_path=test_db_path) == 5


def test_duplicate_source_and_source_id_handling(test_db_path: Path):
    """Verifies duplicate items are safely ignored and existing data is preserved."""
    original_item = {
        "source": "github_trending",
        "source_id": "repo/awesome-agent",
        "domain": "dev-tools",
        "title": "Awesome Agent Framework",
        "url": "https://github.com/repo/awesome-agent",
    }
    first_id = insert_item(original_item, db_path=test_db_path)
    assert first_id is not None

    # Duplicate attempt with altered title
    duplicate_item = {
        "source": "github_trending",
        "source_id": "repo/awesome-agent",
        "domain": "dev-tools",
        "title": "Different Title That Should Be Ignored",
        "url": "https://github.com/repo/awesome-agent",
    }
    duplicate_id = insert_item(duplicate_item, db_path=test_db_path)
    assert duplicate_id is None  # Ignored

    # Verify count is still 1 and original title is preserved
    assert count_items(db_path=test_db_path) == 1
    stored = get_item_by_id(first_id, db_path=test_db_path)
    assert stored["title"] == "Awesome Agent Framework"

    # Batch insertion with duplicate
    batch = [
        duplicate_item,  # existing
        {
            "source": "github_trending",
            "source_id": "repo/new-agent",
            "domain": "dev-tools",
            "title": "New Agent Tool",
        },
    ]
    batch_inserted = insert_items(batch, db_path=test_db_path)
    assert batch_inserted == 1
    assert count_items(db_path=test_db_path) == 2


def test_pagination_behavior(test_db_path: Path):
    """Verifies limit and offset pagination operations."""
    items = [
        {
            "source": "test_feed",
            "source_id": f"item_{i:02d}",
            "title": f"Page Item {i:02d}",
        }
        for i in range(10)
    ]
    insert_items(items, db_path=test_db_path)

    # Page 1: 4 items
    page_1 = get_items(limit=4, offset=0, db_path=test_db_path)
    assert len(page_1) == 4

    # Page 2: 4 items
    page_2 = get_items(limit=4, offset=4, db_path=test_db_path)
    assert len(page_2) == 4

    # Page 3: remaining 2 items
    page_3 = get_items(limit=4, offset=8, db_path=test_db_path)
    assert len(page_3) == 2

    # Verify page 1 and page 2 do not overlap
    page_1_ids = {item["id"] for item in page_1}
    page_2_ids = {item["id"] for item in page_2}
    assert page_1_ids.isdisjoint(page_2_ids)

    # Verify invalid pagination parameters raise ValueError
    with pytest.raises(ValueError, match="limit"):
        get_items(limit=0, db_path=test_db_path)

    with pytest.raises(ValueError, match="offset"):
        get_items(limit=5, offset=-1, db_path=test_db_path)


def test_item_count_with_and_without_filters(test_db_path: Path):
    """Verifies total count and filtered count behavior."""
    items = [
        {
            "source": "s1",
            "source_id": "1",
            "domain": "AI research",
            "title": "Item 1",
            "is_read": 1,
            "is_bookmarked": 0,
        },
        {
            "source": "s1",
            "source_id": "2",
            "domain": "AI research",
            "title": "Item 2",
            "is_read": 0,
            "is_bookmarked": 1,
        },
        {
            "source": "s2",
            "source_id": "3",
            "domain": "cybersecurity",
            "title": "Item 3",
            "is_read": 1,
            "is_bookmarked": 1,
        },
    ]
    insert_items(items, db_path=test_db_path)

    assert count_items(db_path=test_db_path) == 3
    assert count_items(domain="AI research", db_path=test_db_path) == 2
    assert count_items(domain="cybersecurity", db_path=test_db_path) == 1
    assert count_items(domain="dev-tools", db_path=test_db_path) == 0
    assert count_items(is_read=1, db_path=test_db_path) == 2
    assert count_items(is_bookmarked=1, db_path=test_db_path) == 2


def test_updating_read_and_bookmark_status(test_db_path: Path):
    """Verifies updating read and bookmark status flags."""
    item_id = insert_item(
        {
            "source": "source",
            "source_id": "status_test",
            "title": "Status Update Test",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        db_path=test_db_path,
    )

    # Mark as read
    assert update_read_status(item_id, True, db_path=test_db_path) is True
    item = get_item_by_id(item_id, db_path=test_db_path)
    assert item["is_read"] == 1

    # Toggle read off
    assert update_read_status(item_id, False, db_path=test_db_path) is True
    item = get_item_by_id(item_id, db_path=test_db_path)
    assert item["is_read"] == 0

    # Mark as bookmarked
    assert update_bookmark_status(item_id, 1, db_path=test_db_path) is True
    item = get_item_by_id(item_id, db_path=test_db_path)
    assert item["is_bookmarked"] == 1

    # Updating non-existent item returns False
    assert update_read_status(999999, True, db_path=test_db_path) is False
    assert update_bookmark_status(999999, True, db_path=test_db_path) is False


def test_missing_required_fields_and_bounds_validation(test_db_path: Path):
    """Verifies that missing required fields or out-of-bounds scores raise ValueError."""
    # Missing source
    with pytest.raises(ValueError, match="source"):
        insert_item({"source_id": "1", "title": "Test"}, db_path=test_db_path)

    # Empty source
    with pytest.raises(ValueError, match="source"):
        insert_item({"source": "   ", "source_id": "1", "title": "Test"}, db_path=test_db_path)

    # Missing source_id
    with pytest.raises(ValueError, match="source_id"):
        insert_item({"source": "src", "title": "Test"}, db_path=test_db_path)

    # Missing title
    with pytest.raises(ValueError, match="title"):
        insert_item({"source": "src", "source_id": "1"}, db_path=test_db_path)

    # Relevance score out of bounds
    with pytest.raises(ValueError, match="relevance_score"):
        insert_item(
            {"source": "src", "source_id": "1", "title": "Test", "relevance_score": 6},
            db_path=test_db_path,
        )

    with pytest.raises(ValueError, match="relevance_score"):
        insert_item(
            {"source": "src", "source_id": "1", "title": "Test", "relevance_score": 0},
            db_path=test_db_path,
        )

    with pytest.raises(ValueError, match="relevance_score"):
        insert_item(
            {"source": "src", "source_id": "1", "title": "Test", "relevance_score": "high"},
            db_path=test_db_path,
        )


def test_persistence_after_closing_and_reopening(tmp_path: Path):
    """Verifies that committed data persists across completely separate database connections."""
    db_file = tmp_path / "persistent.db"
    init_db(db_file)

    item_id = insert_item(
        {
            "source": "news",
            "source_id": "persist_1",
            "title": "Persistent Intelligence Item",
        },
        db_path=db_file,
    )
    assert item_id is not None

    # Open a completely fresh raw connection to verify persistence
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM intelligence_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row["title"] == "Persistent Intelligence Item"
        assert row["source_id"] == "persist_1"
    finally:
        conn.close()
