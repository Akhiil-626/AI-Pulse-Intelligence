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
    upsert_item,
    upsert_items,
    get_items,
    get_item_by_id,
    count_items,
    update_read_status,
    update_bookmark_status,
    get_connection,
    count_correlated_cves,
    get_correlated_cves,
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
    assert count_items(source="s1", db_path=test_db_path) == 2
    assert count_items(source="s2", db_path=test_db_path) == 1
    assert count_items(source="nonexistent", db_path=test_db_path) == 0
    assert count_items(is_read=1, db_path=test_db_path) == 2
    assert count_items(is_bookmarked=1, db_path=test_db_path) == 2

    # Verify get_items with source filter
    s1_items = get_items(source="s1", db_path=test_db_path)
    assert len(s1_items) == 2
    assert all(it["source"] == "s1" for it in s1_items)

    # Verify multiple source filtering with list/tuple
    assert count_items(source=["s1", "s2"], db_path=test_db_path) == 3
    multi_items = get_items(source=("s1", "s2"), db_path=test_db_path)
    assert len(multi_items) == 3
    assert set(it["source"] for it in multi_items) == {"s1", "s2"}


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


def test_github_releases_source_query_and_count(test_db_path: Path):
    """Verifies storing and retrieving GitHub Releases items with domain='dev-tools'."""
    releases = [
        {
            "source": "GitHub Releases",
            "source_id": "gh_rel_1",
            "domain": "dev-tools",
            "title": "FastAPI v0.115.0",
            "url": "https://github.com/tiangolo/fastapi/releases/tag/0.115.0",
            "text": "Support for newest Pydantic versions.",
            "is_read": 0,
            "is_bookmarked": 1,
        },
        {
            "source": "GitHub Releases",
            "source_id": "gh_rel_2",
            "domain": "dev-tools",
            "title": "Streamlit v1.40.0",
            "url": "https://github.com/streamlit/streamlit/releases/tag/1.40.0",
            "text": "New interactive layout primitives.",
            "is_read": 1,
            "is_bookmarked": 0,
        },
    ]
    inserted = insert_items(releases, db_path=test_db_path)
    assert inserted == 2

    assert count_items(source="GitHub Releases", db_path=test_db_path) == 2
    assert count_items(source="GitHub Releases", domain="dev-tools", db_path=test_db_path) == 2
    assert count_items(source="GitHub Releases", is_bookmarked=1, db_path=test_db_path) == 1
    assert count_items(source="GitHub Releases", is_read=0, db_path=test_db_path) == 1

    items = get_items(source="GitHub Releases", db_path=test_db_path)
    assert len(items) == 2
    assert all(it["source"] == "GitHub Releases" for it in items)
    assert all(it["domain"] == "dev-tools" for it in items)


def test_nvd_cve_source_query_and_count(test_db_path: Path):
    """Verifies storing and retrieving NVD CVE items with domain='cybersecurity'."""
    cves = [
        {
            "source": "NVD CVE",
            "source_id": "CVE-2025-62819",
            "domain": "cybersecurity",
            "title": "Buffer overflow in network stack leading to arbitrary code execution",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2025-62819",
            "text": "Detailed vulnerability description regarding buffer overflow in packet handling.",
            "published_at": "2026-11-02T15:17:11.403",
            "is_read": 0,
            "is_bookmarked": 1,
        },
        {
            "source": "NVD CVE",
            "source_id": "CVE-2025-62820",
            "domain": "cybersecurity",
            "title": "Improper input validation in web console",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2025-62820",
            "text": "Cross-site scripting (XSS) vulnerability in admin portal.",
            "published_at": "2026-11-02T16:00:00.000",
            "is_read": 1,
            "is_bookmarked": 0,
        },
    ]
    inserted = insert_items(cves, db_path=test_db_path)
    assert inserted == 2

    assert count_items(source="NVD CVE", db_path=test_db_path) == 2
    assert count_items(source="NVD CVE", domain="cybersecurity", db_path=test_db_path) == 2
    assert count_items(source="NVD CVE", is_bookmarked=1, db_path=test_db_path) == 1
    assert count_items(source="NVD CVE", is_read=0, db_path=test_db_path) == 1

    items = get_items(source="NVD CVE", db_path=test_db_path)
    assert len(items) == 2
    assert all(it["source"] == "NVD CVE" for it in items)
    assert all(it["domain"] == "cybersecurity" for it in items)


def test_upsert_item_insertion_and_update(test_db_path: Path):
    """Verifies upsert_item inserts new items and updates content fields when duplicate exists."""
    item = {
        "source": "arXiv",
        "source_id": "2411.9999",
        "domain": "AI research",
        "title": "Initial Paper Title",
        "url": "http://arxiv.org/abs/2411.9999v1",
        "text": "Initial abstract text.",
        "published_at": "2024-11-20T10:00:00Z",
    }
    item_id, action = upsert_item(item, db_path=test_db_path)
    assert action == "inserted"
    assert item_id is not None
    assert count_items(db_path=test_db_path) == 1

    # Update item with revised metadata
    updated_item = {
        "source": "arXiv",
        "source_id": "2411.9999",
        "domain": "AI research",
        "title": "Revised Paper Title (v2)",
        "url": "http://arxiv.org/abs/2411.9999v2",
        "text": "Revised and expanded abstract text.",
        "published_at": "2024-11-25T10:00:00Z",
    }
    updated_id, update_action = upsert_item(updated_item, db_path=test_db_path)
    assert update_action == "updated"
    assert updated_id == item_id
    assert count_items(db_path=test_db_path) == 1

    stored = get_item_by_id(item_id, db_path=test_db_path)
    assert stored["title"] == "Revised Paper Title (v2)"
    assert stored["url"] == "http://arxiv.org/abs/2411.9999v2"
    assert stored["text"] == "Revised and expanded abstract text."
    assert stored["published_at"] == "2024-11-25T10:00:00Z"


def test_upsert_items_content_update_and_flag_preservation(test_db_path: Path):
    """Verifies upsert_items updates content fields while strictly preserving is_bookmarked and is_read."""
    initial_items = [
        {
            "source": "Hacker News",
            "source_id": "hn_100",
            "domain": "dev-tools",
            "title": "Initial HN Post",
            "url": "https://news.ycombinator.com/item?id=100",
            "text": "Initial body.",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        {
            "source": "GitHub Releases",
            "source_id": "gh_100",
            "domain": "dev-tools",
            "title": "Initial Release Title",
            "url": "https://github.com/org/repo/releases/tag/v1",
            "text": "Draft release notes.",
            "is_read": 0,
            "is_bookmarked": 0,
        },
    ]
    res1 = upsert_items(initial_items, db_path=test_db_path)
    assert res1 == {"inserted": 2, "updated": 0}

    # User interacts with both items: sets bookmark and read flags
    items = get_items(db_path=test_db_path)
    hn_id = next(it["id"] for it in items if it["source"] == "Hacker News")
    gh_id = next(it["id"] for it in items if it["source"] == "GitHub Releases")

    update_bookmark_status(hn_id, 1, db_path=test_db_path)
    update_read_status(hn_id, 1, db_path=test_db_path)
    update_bookmark_status(gh_id, 1, db_path=test_db_path)

    # Ingestion pipeline re-sends both with corrected titles, urls, descriptions, plus 1 brand new item
    revised_batch = [
        {
            "source": "Hacker News",
            "source_id": "hn_100",
            "domain": "dev-tools",
            "title": "Updated HN Post with Discussion",
            "url": "https://news.ycombinator.com/item?id=100_revised",
            "text": "Updated discussion body with insights.",
            "is_read": 0,       # Incoming payload tries 0, should NOT overwrite user flag
            "is_bookmarked": 0, # Incoming payload tries 0, should NOT overwrite user flag
        },
        {
            "source": "GitHub Releases",
            "source_id": "gh_100",
            "domain": "dev-tools",
            "title": "v1.0.0 Stable Production Release",
            "url": "https://github.com/org/repo/releases/tag/v1.0.0",
            "text": "Official release notes with breaking changes.",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        {
            "source": "arXiv",
            "source_id": "arxiv_new_01",
            "domain": "AI research",
            "title": "Brand New arXiv Paper",
            "url": "http://arxiv.org/abs/2411.5555",
            "text": "New abstract.",
        },
    ]

    res2 = upsert_items(revised_batch, db_path=test_db_path)
    assert res2 == {"inserted": 1, "updated": 2}
    assert count_items(db_path=test_db_path) == 3

    # Verify HN item: content updated, user flags preserved
    hn_stored = get_item_by_id(hn_id, db_path=test_db_path)
    assert hn_stored["title"] == "Updated HN Post with Discussion"
    assert hn_stored["url"] == "https://news.ycombinator.com/item?id=100_revised"
    assert hn_stored["text"] == "Updated discussion body with insights."
    assert hn_stored["is_bookmarked"] == 1
    assert hn_stored["is_read"] == 1

    # Verify GitHub item: content updated, bookmark preserved
    gh_stored = get_item_by_id(gh_id, db_path=test_db_path)
    assert gh_stored["title"] == "v1.0.0 Stable Production Release"
    assert gh_stored["url"] == "https://github.com/org/repo/releases/tag/v1.0.0"
    assert gh_stored["text"] == "Official release notes with breaking changes."
    assert gh_stored["is_bookmarked"] == 1


def test_upsert_items_same_batch_duplicates(test_db_path: Path):
    """Verifies that multiple occurrences of the same (source, source_id) in a single batch upsert correctly."""
    batch = [
        {
            "source": "GitHub Releases",
            "source_id": "duplicate_in_batch",
            "domain": "dev-tools",
            "title": "First Version In Batch",
            "url": "https://github.com/example/repo/releases/tag/v1",
            "text": "First text.",
        },
        {
            "source": "GitHub Releases",
            "source_id": "duplicate_in_batch",
            "domain": "dev-tools",
            "title": "Final Corrected Version In Batch",
            "url": "https://github.com/example/repo/releases/tag/v1-final",
            "text": "Final text.",
        },
    ]
    counts = upsert_items(batch, db_path=test_db_path)
    assert counts == {"inserted": 1, "updated": 1}
    assert count_items(db_path=test_db_path) == 1

    items = get_items(db_path=test_db_path)
    assert len(items) == 1
    assert items[0]["title"] == "Final Corrected Version In Batch"
    assert items[0]["url"] == "https://github.com/example/repo/releases/tag/v1-final"
    assert items[0]["text"] == "Final text."


# ==============================================================================
# Phase 4.2: CVE Correlation Tests (get_correlated_cves & count_correlated_cves)
# ==============================================================================

def test_correlated_cves_matching_both(test_db_path: Path):
    """Verifies that a CVE present in both NVD CVE and CISA KEV returns status 'both'."""
    nvd_item = {
        "source": "NVD CVE",
        "source_id": "CVE-2026-0001",
        "domain": "cybersecurity",
        "title": "NVD Description for Flaw",
        "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-0001",
        "text": "Technical flaw details.",
        "published_at": "2026-01-10T12:00:00Z",
        "is_read": 1,
        "is_bookmarked": 0,
    }
    cisa_item = {
        "source": "CISA KEV",
        "source_id": "CVE-2026-0001",
        "domain": "cybersecurity",
        "title": "Vendor Product RCE",
        "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-0001",
        "text": "Known exploited in wild advisory.",
        "published_at": "2026-01-15",
        "is_read": 0,
        "is_bookmarked": 1,
    }
    insert_items([nvd_item, cisa_item], db_path=test_db_path)

    assert count_correlated_cves("all", db_path=test_db_path) == 1
    assert count_correlated_cves("both", db_path=test_db_path) == 1
    assert count_correlated_cves("nvd_only", db_path=test_db_path) == 0
    assert count_correlated_cves("cisa_only", db_path=test_db_path) == 0

    results = get_correlated_cves(filter_status="both", db_path=test_db_path)
    assert len(results) == 1
    row = results[0]
    assert row["cve_id"] == "CVE-2026-0001"
    assert row["correlation_status"] == "both"
    assert row["nvd_id"] is not None
    assert row["nvd_title"] == "NVD Description for Flaw"
    assert row["nvd_published_at"] == "2026-01-10T12:00:00Z"
    assert row["cisa_id"] is not None
    assert row["cisa_title"] == "Vendor Product RCE"
    assert row["cisa_date_added"] == "2026-01-15"


def test_correlated_cves_nvd_only(test_db_path: Path):
    """Verifies that an NVD-only CVE returns status 'nvd_only' with None for CISA fields."""
    nvd_item = {
        "source": "NVD CVE",
        "source_id": "CVE-2026-0002",
        "domain": "cybersecurity",
        "title": "Buffer overflow in demo component",
        "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-0002",
        "text": "Heap buffer overflow.",
        "published_at": "2026-02-01T08:00:00Z",
    }
    insert_item(nvd_item, db_path=test_db_path)

    assert count_correlated_cves("all", db_path=test_db_path) == 1
    assert count_correlated_cves("both", db_path=test_db_path) == 0
    assert count_correlated_cves("nvd_only", db_path=test_db_path) == 1
    assert count_correlated_cves("cisa_only", db_path=test_db_path) == 0

    results = get_correlated_cves(filter_status="nvd_only", db_path=test_db_path)
    assert len(results) == 1
    row = results[0]
    assert row["cve_id"] == "CVE-2026-0002"
    assert row["correlation_status"] == "nvd_only"
    assert row["nvd_id"] is not None
    assert row["nvd_title"] == "Buffer overflow in demo component"
    assert row["cisa_id"] is None
    assert row["cisa_title"] is None
    assert row["cisa_url"] is None
    assert row["cisa_text"] is None
    assert row["cisa_date_added"] is None
    assert row["cisa_is_read"] is None
    assert row["cisa_is_bookmarked"] is None


def test_correlated_cves_cisa_only(test_db_path: Path):
    """Verifies that a CISA-only CVE returns status 'cisa_only' with None for NVD fields."""
    cisa_item = {
        "source": "CISA KEV",
        "source_id": "CVE-2026-0003",
        "domain": "cybersecurity",
        "title": "Legacy Server Remote Code Execution",
        "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-0003",
        "text": "Known exploited advisory from catalog.",
        "published_at": "2026-02-15",
    }
    insert_item(cisa_item, db_path=test_db_path)

    assert count_correlated_cves("all", db_path=test_db_path) == 1
    assert count_correlated_cves("both", db_path=test_db_path) == 0
    assert count_correlated_cves("nvd_only", db_path=test_db_path) == 0
    assert count_correlated_cves("cisa_only", db_path=test_db_path) == 1

    results = get_correlated_cves(filter_status="cisa_only", db_path=test_db_path)
    assert len(results) == 1
    row = results[0]
    assert row["cve_id"] == "CVE-2026-0003"
    assert row["correlation_status"] == "cisa_only"
    assert row["cisa_id"] is not None
    assert row["cisa_title"] == "Legacy Server Remote Code Execution"
    assert row["cisa_date_added"] == "2026-02-15"
    assert row["nvd_id"] is None
    assert row["nvd_title"] is None
    assert row["nvd_url"] is None
    assert row["nvd_text"] is None
    assert row["nvd_published_at"] is None
    assert row["nvd_is_read"] is None
    assert row["nvd_is_bookmarked"] is None


def test_correlated_cves_all_returns_distinct_rows(test_db_path: Path):
    """Verifies that 'all' returns exactly one row per distinct CVE across both sources."""
    items = [
        # CVE 1: both
        {"source": "NVD CVE", "source_id": "CVE-2026-0010", "domain": "cybersecurity", "title": "NVD 10"},
        {"source": "CISA KEV", "source_id": "CVE-2026-0010", "domain": "cybersecurity", "title": "CISA 10"},
        # CVE 2: NVD only
        {"source": "NVD CVE", "source_id": "CVE-2026-0020", "domain": "cybersecurity", "title": "NVD 20"},
        # CVE 3: CISA only
        {"source": "CISA KEV", "source_id": "CVE-2026-0030", "domain": "cybersecurity", "title": "CISA 30"},
    ]
    insert_items(items, db_path=test_db_path)

    assert count_correlated_cves("all", db_path=test_db_path) == 3
    results = get_correlated_cves(filter_status="all", db_path=test_db_path)
    assert len(results) == 3

    cve_ids = {r["cve_id"] for r in results}
    assert cve_ids == {"CVE-2026-0010", "CVE-2026-0020", "CVE-2026-0030"}

    status_by_id = {r["cve_id"]: r["correlation_status"] for r in results}
    assert status_by_id["CVE-2026-0010"] == "both"
    assert status_by_id["CVE-2026-0020"] == "nvd_only"
    assert status_by_id["CVE-2026-0030"] == "cisa_only"


def test_correlated_cves_excludes_other_sources(test_db_path: Path):
    """Verifies that items from arXiv, Hacker News, and GitHub Releases are excluded from CVE correlation."""
    mixed_items = [
        {"source": "arXiv", "source_id": "2411.9999", "domain": "AI research", "title": "Paper on LLMs"},
        {"source": "Hacker News", "source_id": "50999999", "domain": "dev-tools", "title": "Show HN: Tool"},
        {"source": "GitHub Releases", "source_id": "49999999", "domain": "dev-tools", "title": "Release 1.0"},
        {"source": "NVD CVE", "source_id": "CVE-2026-0040", "domain": "cybersecurity", "title": "NVD 40"},
    ]
    insert_items(mixed_items, db_path=test_db_path)

    assert count_items(db_path=test_db_path) == 4
    assert count_correlated_cves("all", db_path=test_db_path) == 1
    results = get_correlated_cves(filter_status="all", db_path=test_db_path)
    assert len(results) == 1
    assert results[0]["cve_id"] == "CVE-2026-0040"


def test_correlated_cves_duplicate_upsert_prevention(test_db_path: Path):
    """Verifies that re-ingesting or upserting records does not create duplicate correlation rows."""
    initial = [
        {"source": "NVD CVE", "source_id": "CVE-2026-0050", "domain": "cybersecurity", "title": "Initial Title"},
        {"source": "CISA KEV", "source_id": "CVE-2026-0050", "domain": "cybersecurity", "title": "Initial CISA"},
    ]
    upsert_items(initial, db_path=test_db_path)
    assert count_correlated_cves("all", db_path=test_db_path) == 1

    # Re-upsert with updated content
    updated = [
        {"source": "NVD CVE", "source_id": "CVE-2026-0050", "domain": "cybersecurity", "title": "Updated Title"},
        {"source": "CISA KEV", "source_id": "CVE-2026-0050", "domain": "cybersecurity", "title": "Updated CISA"},
    ]
    upsert_items(updated, db_path=test_db_path)

    assert count_correlated_cves("all", db_path=test_db_path) == 1
    results = get_correlated_cves(filter_status="all", db_path=test_db_path)
    assert len(results) == 1
    assert results[0]["nvd_title"] == "Updated Title"
    assert results[0]["cisa_title"] == "Updated CISA"


def test_correlated_cves_metadata_attribution(test_db_path: Path):
    """Verifies that NVD and CISA metadata remain strictly attributed to their respective columns."""
    items = [
        {
            "source": "NVD CVE",
            "source_id": "CVE-2026-0060",
            "domain": "cybersecurity",
            "title": "NVD Unique Advisory Title",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-0060",
            "text": "NVD technical advisory body text.",
            "published_at": "2026-03-01T10:00:00.000",
        },
        {
            "source": "CISA KEV",
            "source_id": "CVE-2026-0060",
            "domain": "cybersecurity",
            "title": "CISA Unique Vulnerability Name",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-0060",
            "text": "CISA catalog description and action required.",
            "published_at": "2026-03-10",
        },
    ]
    insert_items(items, db_path=test_db_path)

    results = get_correlated_cves(filter_status="both", db_path=test_db_path)
    assert len(results) == 1
    row = results[0]

    # Explicit attribution checks
    assert row["nvd_title"] == "NVD Unique Advisory Title"
    assert row["nvd_text"] == "NVD technical advisory body text."
    assert row["nvd_published_at"] == "2026-03-01T10:00:00.000"

    assert row["cisa_title"] == "CISA Unique Vulnerability Name"
    assert row["cisa_text"] == "CISA catalog description and action required."
    assert row["cisa_date_added"] == "2026-03-10"


def test_correlated_cves_independent_read_bookmark_states(test_db_path: Path):
    """Verifies that read and bookmark toggles on NVD record do not alter CISA record and vice versa."""
    nvd_item = {
        "source": "NVD CVE",
        "source_id": "CVE-2026-0070",
        "domain": "cybersecurity",
        "title": "NVD Item",
        "is_read": 0,
        "is_bookmarked": 0,
    }
    cisa_item = {
        "source": "CISA KEV",
        "source_id": "CVE-2026-0070",
        "domain": "cybersecurity",
        "title": "CISA Item",
        "is_read": 0,
        "is_bookmarked": 0,
    }
    insert_items([nvd_item, cisa_item], db_path=test_db_path)

    results = get_correlated_cves(filter_status="both", db_path=test_db_path)
    nvd_id = results[0]["nvd_id"]
    cisa_id = results[0]["cisa_id"]

    # Toggle NVD to read=1, bookmarked=1; CISA remains 0
    update_read_status(nvd_id, 1, db_path=test_db_path)
    update_bookmark_status(nvd_id, 1, db_path=test_db_path)

    results_after_nvd = get_correlated_cves(filter_status="both", db_path=test_db_path)
    assert results_after_nvd[0]["nvd_is_read"] == 1
    assert results_after_nvd[0]["nvd_is_bookmarked"] == 1
    assert results_after_nvd[0]["cisa_is_read"] == 0
    assert results_after_nvd[0]["cisa_is_bookmarked"] == 0

    # Toggle CISA to read=1; CISA bookmarked remains 0
    update_read_status(cisa_id, 1, db_path=test_db_path)

    results_after_cisa = get_correlated_cves(filter_status="both", db_path=test_db_path)
    assert results_after_cisa[0]["nvd_is_read"] == 1
    assert results_after_cisa[0]["nvd_is_bookmarked"] == 1
    assert results_after_cisa[0]["cisa_is_read"] == 1
    assert results_after_cisa[0]["cisa_is_bookmarked"] == 0


def test_correlated_cves_pagination_and_counting(test_db_path: Path):
    """Verifies limit, offset, and count across multiple statuses."""
    items = []
    # 5 NVD-only
    for i in range(1, 6):
        items.append({
            "source": "NVD CVE",
            "source_id": f"CVE-2026-100{i}",
            "domain": "cybersecurity",
            "title": f"NVD {i}",
            "published_at": f"2026-01-0{i}",
        })
    # 3 CISA-only
    for i in range(1, 4):
        items.append({
            "source": "CISA KEV",
            "source_id": f"CVE-2026-200{i}",
            "domain": "cybersecurity",
            "title": f"CISA {i}",
            "published_at": f"2026-02-0{i}",
        })
    # 2 Both
    for i in range(1, 3):
        items.append({
            "source": "NVD CVE",
            "source_id": f"CVE-2026-300{i}",
            "domain": "cybersecurity",
            "title": f"Both NVD {i}",
            "published_at": f"2026-03-0{i}",
        })
        items.append({
            "source": "CISA KEV",
            "source_id": f"CVE-2026-300{i}",
            "domain": "cybersecurity",
            "title": f"Both CISA {i}",
            "published_at": f"2026-03-1{i}",
        })

    insert_items(items, db_path=test_db_path)

    # Total distinct CVEs = 5 + 3 + 2 = 10
    assert count_correlated_cves("all", db_path=test_db_path) == 10
    assert count_correlated_cves("nvd_only", db_path=test_db_path) == 5
    assert count_correlated_cves("cisa_only", db_path=test_db_path) == 3
    assert count_correlated_cves("both", db_path=test_db_path) == 2

    # Pagination: page 1 (limit=4, offset=0)
    page1 = get_correlated_cves(filter_status="all", limit=4, offset=0, db_path=test_db_path)
    assert len(page1) == 4

    # Pagination: page 2 (limit=4, offset=4)
    page2 = get_correlated_cves(filter_status="all", limit=4, offset=4, db_path=test_db_path)
    assert len(page2) == 4

    # Pagination: page 3 (limit=4, offset=8)
    page3 = get_correlated_cves(filter_status="all", limit=4, offset=8, db_path=test_db_path)
    assert len(page3) == 2

    # Disjoint check across pages
    ids_p1 = {r["cve_id"] for r in page1}
    ids_p2 = {r["cve_id"] for r in page2}
    ids_p3 = {r["cve_id"] for r in page3}
    assert ids_p1.isdisjoint(ids_p2)
    assert ids_p2.isdisjoint(ids_p3)
    assert len(ids_p1 | ids_p2 | ids_p3) == 10


def test_correlated_cves_invalid_filter_validation(test_db_path: Path):
    """Verifies that invalid filter values and out-of-range pagination parameters raise ValueError."""
    with pytest.raises(ValueError, match="Invalid filter_status 'invalid_status'"):
        count_correlated_cves("invalid_status", db_path=test_db_path)

    with pytest.raises(ValueError, match="Invalid filter_status 'unknown'"):
        get_correlated_cves(filter_status="unknown", db_path=test_db_path)

    with pytest.raises(ValueError, match="Parameter 'limit' must be greater than or equal to 1."):
        get_correlated_cves(filter_status="all", limit=0, offset=0, db_path=test_db_path)

    with pytest.raises(ValueError, match="Parameter 'offset' must be greater than or equal to 0."):
        get_correlated_cves(filter_status="all", limit=10, offset=-1, db_path=test_db_path)
