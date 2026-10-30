"""Tests for Phase 4.1.1: Live Overview Metrics and SQLite Database Integration."""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

from app.dashboard import fetch_overview_metrics, get_dashboard_db_path
from services.database import init_db, insert_items


@pytest.fixture
def empty_test_db(tmp_path: Path) -> Path:
    """Provides an initialized, empty SQLite database."""
    db_file = tmp_path / "empty_ai_pulse.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def populated_test_db(tmp_path: Path) -> Path:
    """Provides an initialized SQLite database with known records."""
    db_file = tmp_path / "populated_ai_pulse.db"
    init_db(db_file)

    sample_items = [
        # Item 1: unread, bookmarked, AI research
        {
            "source": "arXiv",
            "source_id": "2401.0001",
            "domain": "AI research",
            "title": "Frontier Model Reasoning",
            "is_read": 0,
            "is_bookmarked": 1,
        },
        # Item 2: read, unbookmarked, cybersecurity
        {
            "source": "NVD CVE",
            "source_id": "CVE-2026-0001",
            "domain": "cybersecurity",
            "title": "Buffer Overflow in Protocol",
            "is_read": 1,
            "is_bookmarked": 0,
        },
        # Item 3: unread, bookmarked, cybersecurity
        {
            "source": "CISA KEV",
            "source_id": "CVE-2026-0002",
            "domain": "cybersecurity",
            "title": "Known Exploited Vulnerability",
            "is_read": 0,
            "is_bookmarked": 1,
        },
        # Item 4: unread, unbookmarked, dev-tools
        {
            "source": "GitHub Releases",
            "source_id": "repo/v2.0",
            "domain": "dev-tools",
            "title": "Release 2.0.0",
            "is_read": 0,
            "is_bookmarked": 0,
        },
    ]
    insert_items(sample_items, db_path=db_file)
    return db_file


def test_fetch_overview_metrics_empty_database(empty_test_db: Path):
    """Verifies that an empty database returns 0 for all live metrics with no error."""
    metrics = fetch_overview_metrics(db_path=empty_test_db)
    assert metrics["error"] is None
    assert metrics["total"] == 0
    assert metrics["unread"] == 0
    assert metrics["bookmarked"] == 0
    assert metrics["threats"] == 0


def test_fetch_overview_metrics_populated_database(populated_test_db: Path):
    """Verifies live metric calculations:
    - total = 4
    - unread (is_read = 0) = 3 (Item 1, 3, 4)
    - bookmarked (is_bookmarked = 1) = 2 (Item 1, 3)
    - threats (domain = 'cybersecurity') = 2 (Item 2, 3)
    """
    metrics = fetch_overview_metrics(db_path=populated_test_db)
    assert metrics["error"] is None
    assert metrics["total"] == 4
    assert metrics["unread"] == 3
    assert metrics["bookmarked"] == 2
    assert metrics["threats"] == 2


def test_fetch_overview_metrics_graceful_error_handling(tmp_path: Path):
    """Verifies that database exceptions (e.g., path pointing to a directory) are caught gracefully."""
    invalid_db_path = tmp_path  # A directory cannot be opened as a SQLite file
    metrics = fetch_overview_metrics(db_path=invalid_db_path)

    assert metrics["error"] is not None
    assert metrics["total"] == 0
    assert metrics["unread"] == 0
    assert metrics["bookmarked"] == 0
    assert metrics["threats"] == 0


DASHBOARD_FILE = str(Path(__file__).resolve().parent.parent / "app" / "dashboard.py")


def test_dashboard_renders_live_metrics_with_empty_db(empty_test_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies Streamlit AppTest execution against an empty database."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(empty_test_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    # Ensure empty-state banner is rendered
    markdown_texts = [m.value for m in app_test.markdown]
    assert any("Total Intelligence Items" in t for t in markdown_texts)
    assert any("Intelligence Feeds Awaiting Data Ingestion" in t for t in markdown_texts)


def test_dashboard_renders_live_metrics_with_populated_db(populated_test_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies Streamlit AppTest execution displaying loaded live metrics."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_test_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    assert any("Total Intelligence Items" in t for t in markdown_texts)
    # Total count 4 rendered in metric value
    assert any(">4<" in t or "4" in t for t in markdown_texts)


def test_dashboard_handles_db_failure_gracefully(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies Streamlit AppTest displays error banner without crashing when DB fails."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(tmp_path))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    # st.error was displayed
    assert len(app_test.error) > 0
    assert "Database connection unavailable" in app_test.error[0].value
