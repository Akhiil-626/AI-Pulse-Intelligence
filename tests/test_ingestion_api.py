"""Tests for the authenticated ingestion API using pytest and FastAPI TestClient.

All tests utilize temporary SQLite databases and mock credentials, ensuring
the development database is never modified.
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from services.database import (
    count_items,
    get_item_by_id,
    get_items,
    init_db,
    insert_item,
    update_bookmark_status,
    update_read_status,
)
from services.ingestion_api import app, get_active_db_path

TEST_TOKEN = "test_secure_ingest_token_xyz987"


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Creates a temporary, isolated SQLite database file."""
    db_file = tmp_path / "test_api_pulse.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def client(temp_db: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Configures TestClient with temporary DB and mock ingestion token."""
    monkeypatch.setenv("INGEST_API_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(temp_db))

    app.dependency_overrides[get_active_db_path] = lambda: temp_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_valid_authenticated_request_inserts_records(client: TestClient, temp_db: Path):
    """Verifies that an authenticated request persists valid records to the database."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    payload = [
        {
            "id": "2401.9999",
            "source": "arXiv",
            "domain": "AI research",
            "title": "Frontier Agent Reasoning with Tool Use",
            "url": "https://arxiv.org/abs/2401.9999",
            "text": "Abstract discussing autonomous agent verification.",
            "published_at": "2026-02-01T12:00:00Z",
            "fetched_at": "2026-02-01T12:05:00Z",
        },
        {
            "id": "CVE-2026-99999",
            "source": "NVD CVE",
            "domain": "cybersecurity",
            "title": "Remote Execution Vulnerability in Parser",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-99999",
            "text": "Buffer overflow in legacy protocol decoder.",
        },
    ]

    response = client.post("/api/v1/ingest", json=payload, headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["received"] == 2
    assert data["inserted"] == 2
    assert data["skipped"] == 0

    # Verify rows in database
    items = get_items(db_path=temp_db)
    assert len(items) == 2
    sources = {item["source"] for item in items}
    assert sources == {"arXiv", "NVD CVE"}

    # Verify id mapped to source_id
    arxiv_item = next(it for it in items if it["source"] == "arXiv")
    assert arxiv_item["source_id"] == "2401.9999"
    assert arxiv_item["domain"] == "AI research"


def test_missing_bearer_token_returns_401(client: TestClient, temp_db: Path):
    """Verifies that requests missing the Authorization header return HTTP 401."""
    payload = [
        {
            "id": "1",
            "source": "Hacker News",
            "domain": "dev-tools",
            "title": "Show HN: New Fast SQLite Tool",
        }
    ]

    response = client.post("/api/v1/ingest", json=payload)
    assert response.status_code == 401
    assert "detail" in response.json()
    assert count_items(db_path=temp_db) == 0


def test_incorrect_bearer_token_returns_401(client: TestClient, temp_db: Path):
    """Verifies that requests with an incorrect bearer token return HTTP 401."""
    headers = {"Authorization": "Bearer wrong_invalid_token"}
    payload = [
        {
            "id": "1",
            "source": "Hacker News",
            "domain": "dev-tools",
            "title": "Show HN: New Fast SQLite Tool",
        }
    ]

    response = client.post("/api/v1/ingest", json=payload, headers=headers)
    assert response.status_code == 401
    assert "Invalid bearer token" in response.json()["detail"]
    assert count_items(db_path=temp_db) == 0


def test_unconfigured_server_token_rejects_safely(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, temp_db: Path
):
    """Verifies that an unconfigured or empty server token rejects requests safely with 401."""
    monkeypatch.setenv("INGEST_API_TOKEN", "")
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    payload = [
        {
            "id": "1",
            "source": "Hacker News",
            "domain": "dev-tools",
            "title": "Show HN: SQLite Tool",
        }
    ]

    response = client.post("/api/v1/ingest", json=payload, headers=headers)
    assert response.status_code == 401
    assert count_items(db_path=temp_db) == 0


def test_malformed_records_return_422(client: TestClient, temp_db: Path):
    """Verifies that records with missing required fields return HTTP 422."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}

    # Missing title
    payload_no_title = [
        {
            "id": "100",
            "source": "Hacker News",
            "domain": "dev-tools",
        }
    ]
    response = client.post("/api/v1/ingest", json=payload_no_title, headers=headers)
    assert response.status_code == 422

    # Empty whitespace title
    payload_empty_title = [
        {
            "id": "101",
            "source": "Hacker News",
            "domain": "dev-tools",
            "title": "   ",
        }
    ]
    response = client.post("/api/v1/ingest", json=payload_empty_title, headers=headers)
    assert response.status_code == 422

    # Malformed non-list / non-dict payload
    response = client.post("/api/v1/ingest", content="invalid json", headers=headers)
    assert response.status_code == 422


def test_unknown_source_rejected_with_422(client: TestClient):
    """Verifies that source names outside the allowed taxonomy are rejected with HTTP 422."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    payload = [
        {
            "id": "123",
            "source": "UnauthorizedBlog",  # Not in AllowedSource
            "domain": "AI research",
            "title": "Unsupported Source Submission",
        }
    ]

    response = client.post("/api/v1/ingest", json=payload, headers=headers)
    assert response.status_code == 422


def test_unknown_domain_rejected_with_422(client: TestClient):
    """Verifies that domain names outside the allowed taxonomy are rejected with HTTP 422."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    payload = [
        {
            "id": "123",
            "source": "arXiv",
            "domain": "finance",  # Not in AllowedDomain
            "title": "Algorithmic Trading Update",
        }
    ]

    response = client.post("/api/v1/ingest", json=payload, headers=headers)
    assert response.status_code == 422


def test_duplicate_records_do_not_create_duplicate_rows(client: TestClient, temp_db: Path):
    """Verifies that duplicate (source, id) submissions update metadata rather than creating duplicate rows."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    initial_payload = [
        {
            "id": "repo/v1.0.0",
            "source": "GitHub Releases",
            "domain": "dev-tools",
            "title": "Version 1.0.0 Released",
        }
    ]

    # First ingestion
    res1 = client.post("/api/v1/ingest", json=initial_payload, headers=headers)
    assert res1.status_code == 200
    assert res1.json() == {"received": 1, "inserted": 1, "updated": 0, "skipped": 0, "message": None}

    # Second ingestion with duplicate + new record
    mixed_payload = [
        {
            "id": "repo/v1.0.0",  # Duplicate with corrected title
            "source": "GitHub Releases",
            "domain": "dev-tools",
            "title": "Version 1.0.0 (Corrected Title)",
        },
        {
            "id": "repo/v1.1.0",  # New item
            "source": "GitHub Releases",
            "domain": "dev-tools",
            "title": "Version 1.1.0 Released",
        },
    ]

    res2 = client.post("/api/v1/ingest", json=mixed_payload, headers=headers)
    assert res2.status_code == 200
    assert res2.json() == {"received": 2, "inserted": 1, "updated": 1, "skipped": 0, "message": None}

    # Verify total count in DB is 2 and existing record title was updated
    assert count_items(db_path=temp_db) == 2
    items = get_items(db_path=temp_db)
    v1_item = next(it for it in items if it["source_id"] == "repo/v1.0.0")
    assert v1_item["title"] == "Version 1.0.0 (Corrected Title)"


def test_ingest_existing_record_metadata_update(client: TestClient, temp_db: Path):
    """Verifies updating all content fields (domain, title, url, text, published_at) for an existing record."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    initial_payload = [
        {
            "id": "release-410",
            "source": "GitHub Releases",
            "domain": "dev-tools",
            "title": "{{ $json.name || $json.tag_name }}",  # Placeholder title to be corrected
            "url": "https://github.com/ollama/ollama/releases/tag/v0.40.4",
            "text": "Initial unparsed release text.",
            "published_at": "2026-10-12T19:00:12Z",
        }
    ]

    res1 = client.post("/api/v1/ingest", json=initial_payload, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["inserted"] == 1
    assert res1.json()["updated"] == 0

    # Ingest corrected metadata
    corrected_payload = [
        {
            "id": "release-410",
            "source": "GitHub Releases",
            "domain": "dev-tools",
            "title": "Ollama v0.40.4: Decision Models in the CLI",
            "url": "https://github.com/ollama/ollama/releases/tag/v0.40.4",
            "text": "Corrected description with detailed changelog.",
            "published_at": "2026-10-12T19:30:00Z",
        }
    ]

    res2 = client.post("/api/v1/ingest", json=corrected_payload, headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["received"] == 1
    assert data2["inserted"] == 0
    assert data2["updated"] == 1
    assert data2["skipped"] == 0

    # Verify updated values in SQLite
    assert count_items(db_path=temp_db) == 1
    items = get_items(db_path=temp_db)
    item = items[0]
    assert item["source_id"] == "release-410"
    assert item["title"] == "Ollama v0.40.4: Decision Models in the CLI"
    assert item["text"] == "Corrected description with detailed changelog."
    assert item["published_at"] == "2026-10-12T19:30:00Z"


def test_ingest_preserves_bookmark_and_read_status(client: TestClient, temp_db: Path):
    """Verifies that updating existing record metadata preserves user-managed is_bookmarked and is_read flags."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    initial_payload = [
        {
            "id": "story-999",
            "source": "Hacker News",
            "domain": "dev-tools",
            "title": "Show HN: Fast Search Tool",
            "url": "https://example.com/fast-search",
        }
    ]

    res1 = client.post("/api/v1/ingest", json=initial_payload, headers=headers)
    assert res1.status_code == 200

    items = get_items(db_path=temp_db)
    item_id = items[0]["id"]

    # User interacts with the dashboard: marks item as read and bookmarked
    update_bookmark_status(item_id, 1, db_path=temp_db)
    update_read_status(item_id, 1, db_path=temp_db)

    stored_before = get_item_by_id(item_id, db_path=temp_db)
    assert stored_before["is_bookmarked"] == 1
    assert stored_before["is_read"] == 1

    # Ingestion pipeline re-sends story with updated title and added discussion text
    update_payload = [
        {
            "id": "story-999",
            "source": "Hacker News",
            "domain": "dev-tools",
            "title": "Show HN: Fast Search Tool v2.0",
            "url": "https://example.com/fast-search-v2",
            "text": "Added full text indexing and benchmarks.",
        }
    ]

    res2 = client.post("/api/v1/ingest", json=update_payload, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["updated"] == 1

    # Verify that content fields updated but user flags remain preserved
    stored_after = get_item_by_id(item_id, db_path=temp_db)
    assert stored_after["title"] == "Show HN: Fast Search Tool v2.0"
    assert stored_after["url"] == "https://example.com/fast-search-v2"
    assert stored_after["text"] == "Added full text indexing and benchmarks."
    assert stored_after["is_bookmarked"] == 1  # Preserved!
    assert stored_after["is_read"] == 1        # Preserved!


def test_ingest_duplicate_records_within_same_batch(client: TestClient, temp_db: Path):
    """Verifies that multiple records with the same (source, id) in a single incoming batch are handled safely."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    batch_payload = [
        {
            "id": "paper-1234",
            "source": "arXiv",
            "domain": "AI research",
            "title": "Initial Preprint Title",
            "url": "https://arxiv.org/abs/2411.1234v1",
            "text": "First version abstract.",
        },
        {
            "id": "paper-5678",
            "source": "arXiv",
            "domain": "AI research",
            "title": "Different Preprint",
            "url": "https://arxiv.org/abs/2411.5678v1",
        },
        {
            "id": "paper-1234",  # Same id in same batch with revised title and v2 text
            "source": "arXiv",
            "domain": "AI research",
            "title": "Revised Preprint Title (v2)",
            "url": "https://arxiv.org/abs/2411.1234v2",
            "text": "Revised and expanded abstract.",
        },
    ]

    response = client.post("/api/v1/ingest", json=batch_payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["received"] == 3
    assert data["inserted"] == 2
    assert data["updated"] == 1
    assert data["skipped"] == 0

    # Ensure database contains exactly 2 records, with paper-1234 holding the updated metadata
    assert count_items(db_path=temp_db) == 2
    items = get_items(db_path=temp_db)
    paper = next(it for it in items if it["source_id"] == "paper-1234")
    assert paper["title"] == "Revised Preprint Title (v2)"
    assert paper["url"] == "https://arxiv.org/abs/2411.1234v2"
    assert paper["text"] == "Revised and expanded abstract."


def test_empty_batch_handling_policy(client: TestClient):
    """Verifies that empty batches return HTTP 200 with 0 counts per documented policy."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}

    # Empty list
    res_list = client.post("/api/v1/ingest", json=[], headers=headers)
    assert res_list.status_code == 200
    assert res_list.json()["received"] == 0
    assert res_list.json()["inserted"] == 0
    assert res_list.json()["skipped"] == 0
    assert "Empty batch" in res_list.json()["message"]

    # Empty items object
    res_obj = client.post("/api/v1/ingest", json={"items": []}, headers=headers)
    assert res_obj.status_code == 200
    assert res_obj.json()["received"] == 0


def test_existing_database_contents_remain_intact(client: TestClient, temp_db: Path):
    """Verifies that pre-existing database records remain undisturbed after ingestion calls."""
    # Pre-populate database with an existing item
    pre_id = insert_item(
        {
            "source": "CISA KEV",
            "source_id": "PRE-EXISTING-01",
            "domain": "cybersecurity",
            "title": "Pre-existing Vulnerability",
        },
        db_path=temp_db,
    )
    assert pre_id is not None

    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    payload = [
        {
            "id": "NEW-01",
            "source": "arXiv",
            "domain": "AI research",
            "title": "New Research Finding",
        }
    ]

    res = client.post("/api/v1/ingest", json=payload, headers=headers)
    assert res.status_code == 200

    # Ensure pre-existing item is still intact
    stored_pre = get_item_by_id(pre_id, db_path=temp_db)
    assert stored_pre is not None
    assert stored_pre["title"] == "Pre-existing Vulnerability"
    assert count_items(db_path=temp_db) == 2
