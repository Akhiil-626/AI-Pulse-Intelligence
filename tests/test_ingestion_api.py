"""Tests for the authenticated ingestion API using pytest and FastAPI TestClient.

All tests utilize temporary SQLite databases and mock credentials, ensuring
the development database is never modified.
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from services.database import count_items, get_item_by_id, get_items, init_db, insert_item
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
    """Verifies that duplicate (source, id) submissions are skipped and counted accurately."""
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
    assert res1.json() == {"received": 1, "inserted": 1, "skipped": 0, "message": None}

    # Second ingestion with duplicate + new record
    mixed_payload = [
        {
            "id": "repo/v1.0.0",  # Duplicate
            "source": "GitHub Releases",
            "domain": "dev-tools",
            "title": "Altered title that should be ignored",
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
    assert res2.json() == {"received": 2, "inserted": 1, "skipped": 1, "message": None}

    # Verify total count in DB is 2 and original record title was preserved
    assert count_items(db_path=temp_db) == 2
    items = get_items(db_path=temp_db)
    v1_item = next(it for it in items if it["source_id"] == "repo/v1.0.0")
    assert v1_item["title"] == "Version 1.0.0 Released"


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
