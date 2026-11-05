"""Tests for the Checkpoint API endpoints in services/ingestion_api.py.

All tests utilize temporary SQLite databases and mock credentials, ensuring
the production database is never modified.
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from services.database import get_pipeline_checkpoint, init_db
from services.ingestion_api import app, get_active_db_path

TEST_TOKEN = "test_secure_ingest_token_xyz987"


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Creates a temporary, isolated SQLite database file."""
    db_file = tmp_path / "test_checkpoint_pulse.db"
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


def test_checkpoint_endpoints_require_authentication(client: TestClient):
    """Verifies that missing or invalid Authorization headers return HTTP 401."""
    # GET without token
    res_get = client.get("/api/v1/checkpoint/nvd_backfill")
    assert res_get.status_code == 401

    # POST without token
    res_post = client.post(
        "/api/v1/checkpoint/nvd_backfill",
        json={
            "start_date": "2002-01-01T00:00:00Z",
            "end_date": "2002-04-01T00:00:00Z",
        },
    )
    assert res_post.status_code == 401

    # GET with invalid token
    bad_headers = {"Authorization": "Bearer completely_wrong_token"}
    res_bad = client.get("/api/v1/checkpoint/nvd_backfill", headers=bad_headers)
    assert res_bad.status_code == 401


def test_invalid_pipeline_id_format_returns_400(client: TestClient):
    """Verifies that invalid pipeline identifiers return HTTP 400 Bad Request."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}

    # Contains invalid symbols or spaces
    res = client.get("/api/v1/checkpoint/invalid..id", headers=headers)
    assert res.status_code == 400
    assert "Invalid pipeline identifier" in res.json()["detail"]

    res_post = client.post(
        "/api/v1/checkpoint/invalid$id",
        json={
            "start_date": "2002-01-01T00:00:00Z",
            "end_date": "2002-04-01T00:00:00Z",
        },
        headers=headers,
    )
    assert res_post.status_code == 400


def test_get_uninitialized_checkpoint_returns_clear_response(client: TestClient, temp_db: Path):
    """Verifies that querying an uninitialized checkpoint returns initialized=False without error."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}

    response = client.get("/api/v1/checkpoint/nvd_backfill", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["pipeline_id"] == "nvd_backfill"
    assert data["initialized"] is False
    assert data["checkpoint"] is None
    assert "not been initialized" in data["message"]

    # Verify database was not silently populated
    assert get_pipeline_checkpoint("nvd_backfill", db_path=temp_db) is None


def test_post_initial_checkpoint_success(client: TestClient, temp_db: Path):
    """Verifies creating an initial checkpoint via POST /api/v1/checkpoint/{pipeline_id}."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    payload = {
        "start_date": "2002-01-01T00:00:00Z",
        "end_date": "2002-04-01T00:00:00Z",
        "current_offset": 0,
        "last_page": 0,
        "total_records_ingested": 0,
        "status": "idle",
        "last_sync_at": None,
    }

    response = client.post("/api/v1/checkpoint/nvd_backfill", json=payload, headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["pipeline_id"] == "nvd_backfill"
    assert data["saved"] is True
    assert data["status"] == "idle"
    assert data["checkpoint"]["current_offset"] == 0
    assert data["checkpoint"]["last_page"] == 0
    assert data["checkpoint"]["total_records_ingested"] == 0
    assert data["checkpoint"]["last_sync_at"] is None

    # Verify persisted in database
    db_rec = get_pipeline_checkpoint("nvd_backfill", db_path=temp_db)
    assert db_rec is not None
    assert db_rec["status"] == "idle"


def test_get_existing_checkpoint_returns_full_data(client: TestClient):
    """Verifies GET returns complete checkpoint structure once initialized."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}

    # Initialize checkpoint
    client.post(
        "/api/v1/checkpoint/nvd_backfill",
        json={
            "start_date": "2002-01-01T00:00:00Z",
            "end_date": "2002-04-01T00:00:00Z",
            "current_offset": 2000,
            "last_page": 1,
            "total_records_ingested": 2000,
            "status": "in_progress",
            "last_sync_at": "2026-11-05T12:00:00Z",
        },
        headers=headers,
    )

    # Query GET
    response = client.get("/api/v1/checkpoint/nvd_backfill", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["pipeline_id"] == "nvd_backfill"
    assert data["initialized"] is True
    assert data["status"] == "in_progress"
    assert data["start_date"] == "2002-01-01T00:00:00Z"
    assert data["end_date"] == "2002-04-01T00:00:00Z"
    assert data["current_offset"] == 2000
    assert data["last_page"] == 1
    assert data["total_records_ingested"] == 2000
    assert data["last_sync_at"] == "2026-11-05T12:00:00Z"
    assert data["checkpoint"]["current_offset"] == 2000


def test_post_checkpoint_validation_rejects_negative_and_invalid_data(client: TestClient):
    """Verifies that negative values, bad dates, and invalid statuses return HTTP 422."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    base = {
        "start_date": "2002-01-01T00:00:00Z",
        "end_date": "2002-04-01T00:00:00Z",
        "status": "in_progress",
    }

    # Negative offset
    res = client.post("/api/v1/checkpoint/nvd_backfill", json={**base, "current_offset": -1}, headers=headers)
    assert res.status_code == 422

    # Negative page
    res = client.post("/api/v1/checkpoint/nvd_backfill", json={**base, "last_page": -1}, headers=headers)
    assert res.status_code == 422

    # Negative total_records_ingested
    res = client.post("/api/v1/checkpoint/nvd_backfill", json={**base, "total_records_ingested": -5}, headers=headers)
    assert res.status_code == 422

    # Invalid status
    res = client.post("/api/v1/checkpoint/nvd_backfill", json={**base, "status": "running"}, headers=headers)
    assert res.status_code == 422

    # Malformed date
    res = client.post("/api/v1/checkpoint/nvd_backfill", json={**base, "start_date": "bad-date"}, headers=headers)
    assert res.status_code == 422

    # Inverted date window
    res = client.post(
        "/api/v1/checkpoint/nvd_backfill",
        json={**base, "start_date": "2002-04-01T00:00:00Z", "end_date": "2002-01-01T00:00:00Z"},
        headers=headers,
    )
    assert res.status_code == 422


def test_post_checkpoint_rejects_concurrency_conflict_and_stale_update(client: TestClient):
    """Verifies that stale updates and OCC conflicts return HTTP 409 Conflict."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}

    # Initialize progress at page 2, offset 4000
    res1 = client.post(
        "/api/v1/checkpoint/nvd_backfill",
        json={
            "start_date": "2002-01-01T00:00:00Z",
            "end_date": "2002-04-01T00:00:00Z",
            "current_offset": 4000,
            "last_page": 2,
            "total_records_ingested": 4000,
            "status": "in_progress",
        },
        headers=headers,
    )
    assert res1.status_code == 200
    updated_at_t1 = res1.json()["checkpoint"]["updated_at"]

    # 1. Stale update regressing offset to 2000 -> HTTP 409
    res_stale = client.post(
        "/api/v1/checkpoint/nvd_backfill",
        json={
            "start_date": "2002-01-01T00:00:00Z",
            "end_date": "2002-04-01T00:00:00Z",
            "current_offset": 2000,
            "last_page": 1,
            "total_records_ingested": 4000,
            "status": "in_progress",
        },
        headers=headers,
    )
    assert res_stale.status_code == 409
    assert "Stale checkpoint update" in res_stale.json()["detail"]

    # 2. OCC mismatch -> HTTP 409
    res_occ = client.post(
        "/api/v1/checkpoint/nvd_backfill",
        json={
            "start_date": "2002-01-01T00:00:00Z",
            "end_date": "2002-04-01T00:00:00Z",
            "current_offset": 6000,
            "last_page": 3,
            "total_records_ingested": 6000,
            "status": "in_progress",
            "expected_updated_at": "2020-01-01T00:00:00Z",  # Mismatched timestamp
        },
        headers=headers,
    )
    assert res_occ.status_code == 409
    assert "Concurrency conflict" in res_occ.json()["detail"]


def test_supported_status_transitions_via_api(client: TestClient):
    """Verifies full lifecycle of state transitions through the API."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}

    # idle
    r1 = client.post(
        "/api/v1/checkpoint/nvd_backfill",
        json={
            "start_date": "2002-01-01T00:00:00Z",
            "end_date": "2002-04-01T00:00:00Z",
            "status": "idle",
        },
        headers=headers,
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "idle"

    # idle -> in_progress
    r2 = client.post(
        "/api/v1/checkpoint/nvd_backfill",
        json={
            "start_date": "2002-01-01T00:00:00Z",
            "end_date": "2002-04-01T00:00:00Z",
            "current_offset": 2000,
            "last_page": 1,
            "total_records_ingested": 2000,
            "status": "in_progress",
        },
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "in_progress"

    # in_progress -> failed
    r3 = client.post(
        "/api/v1/checkpoint/nvd_backfill",
        json={
            "start_date": "2002-01-01T00:00:00Z",
            "end_date": "2002-04-01T00:00:00Z",
            "current_offset": 2000,
            "last_page": 1,
            "total_records_ingested": 2000,
            "status": "failed",
            "last_error": "Connection reset by peer",
        },
        headers=headers,
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "failed"

    # failed -> in_progress (resume)
    r4 = client.post(
        "/api/v1/checkpoint/nvd_backfill",
        json={
            "start_date": "2002-01-01T00:00:00Z",
            "end_date": "2002-04-01T00:00:00Z",
            "current_offset": 4000,
            "last_page": 2,
            "total_records_ingested": 4000,
            "status": "in_progress",
        },
        headers=headers,
    )
    assert r4.status_code == 200
    assert r4.json()["status"] == "in_progress"

    # in_progress -> completed
    r5 = client.post(
        "/api/v1/checkpoint/nvd_backfill",
        json={
            "start_date": "2002-01-01T00:00:00Z",
            "end_date": "2002-04-01T00:00:00Z",
            "current_offset": 4000,
            "last_page": 2,
            "total_records_ingested": 4000,
            "status": "completed",
        },
        headers=headers,
    )
    assert r5.status_code == 200
    assert r5.json()["status"] == "completed"

    # Mutating completed -> 409 Conflict
    r6 = client.post(
        "/api/v1/checkpoint/nvd_backfill",
        json={
            "start_date": "2002-01-01T00:00:00Z",
            "end_date": "2002-04-01T00:00:00Z",
            "status": "in_progress",
        },
        headers=headers,
    )
    assert r6.status_code == 409
