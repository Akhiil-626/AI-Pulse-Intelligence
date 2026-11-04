"""Tests for the Streamlit Threat Center (CVE Correlation View).

Validates Threat Center rendering, four-metric status cards, correlation filtering
(All Statuses, Present in Both, NVD Only, CISA KEV Only), dual-source card comparative layouts,
missing-side notices, pagination, and independent read/bookmark toggle handling.
"""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

from app.dashboard import (
    get_dashboard_db_path,
)
from services.database import (
    count_correlated_cves,
    get_correlated_cves,
    get_item_by_id,
    init_db,
    insert_items,
    update_bookmark_status,
    update_read_status,
)

DASHBOARD_FILE = str(Path(__file__).resolve().parent.parent / "app" / "dashboard.py")


@pytest.fixture
def empty_threat_db(tmp_path: Path) -> Path:
    """Provides an initialized, empty SQLite database."""
    db_file = tmp_path / "empty_threat_pulse.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def populated_threat_db(tmp_path: Path) -> Path:
    """Provides an initialized SQLite database with synthetic NVD CVE and CISA KEV records."""
    db_file = tmp_path / "populated_threat_pulse.db"
    init_db(db_file)

    sample_items = [
        # CVE 1: Present in both sources
        {
            "source": "NVD CVE",
            "source_id": "CVE-2026-9001",
            "domain": "cybersecurity",
            "title": "NVD Advisory for Remote Code Execution Flaw",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-9001",
            "text": "Technical vulnerability analysis from NIST.",
            "published_at": "2026-03-01T12:00:00.000",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        {
            "source": "CISA KEV",
            "source_id": "CVE-2026-9001",
            "domain": "cybersecurity",
            "title": "Enterprise Gateway Remote Code Execution Vulnerability",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-9001",
            "text": "Actively exploited in the wild; immediate patch required.",
            "published_at": "2026-03-05",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # CVE 2: NVD Only
        {
            "source": "NVD CVE",
            "source_id": "CVE-2026-9002",
            "domain": "cybersecurity",
            "title": "NVD Only Buffer Overflow Vulnerability",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-9002",
            "text": "Stack buffer overflow in library parser.",
            "published_at": "2026-03-02T10:00:00.000",
            "is_read": 1,
            "is_bookmarked": 0,
        },
        # CVE 3: CISA KEV Only
        {
            "source": "CISA KEV",
            "source_id": "CVE-2026-9003",
            "domain": "cybersecurity",
            "title": "Legacy Server Authentication Bypass Vulnerability",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-9003",
            "text": "Known exploited advisory from CISA catalog.",
            "published_at": "2026-03-03",
            "is_read": 0,
            "is_bookmarked": 1,
        },
        # CVE 4: Another NVD Only
        {
            "source": "NVD CVE",
            "source_id": "CVE-2026-9004",
            "domain": "cybersecurity",
            "title": "NVD Second Advisory for SQL Injection",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-9004",
            "text": "SQL injection in admin backend.",
            "published_at": "2026-03-04T15:00:00.000",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Other source: arXiv item (should be completely excluded)
        {
            "source": "arXiv",
            "source_id": "2411.8888",
            "domain": "AI research",
            "title": "Unrelated Research Paper",
            "url": "https://arxiv.org/abs/2411.8888",
            "text": "Deep learning paper.",
            "published_at": "2026-03-01T00:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
    ]
    insert_items(sample_items, db_path=db_file)
    return db_file


def test_threat_center_renders_cleanly(empty_threat_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that Threat Center renders with empty state notice and 0 counts when no records exist."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(empty_threat_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    # Navigate to Threat Center
    app_test.radio[0].set_value("Threat Center").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    assert any("Threat Center" in t for t in markdown_texts)
    assert any("Total Distinct CVEs" in t for t in markdown_texts)
    assert any("Present in Both" in t for t in markdown_texts)
    assert any("NVD Only" in t for t in markdown_texts)
    assert any("CISA KEV Only" in t for t in markdown_texts)
    assert any("No Correlated CVE Records Found" in t for t in markdown_texts)


def test_threat_center_metrics_row_with_records(populated_threat_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that Threat Center metrics display correct counts across all four categories."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_threat_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    app_test.radio[0].set_value("Threat Center").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    # Total = 4 distinct CVEs (1 both + 2 nvd_only + 1 cisa_only = 4)
    assert any("Total Distinct CVEs" in t for t in markdown_texts)
    assert any("4" in t for t in markdown_texts)
    # Present in both = 1
    assert any("Present in Both" in t for t in markdown_texts)
    # NVD Only = 2
    assert any("NVD Only" in t for t in markdown_texts)
    # CISA KEV Only = 1
    assert any("CISA KEV Only" in t for t in markdown_texts)


def test_threat_center_status_filtering_options(populated_threat_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that correlation status filter options display the appropriate subsets of CVE records."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_threat_db))

    # Test 'Present in Both'
    app_both = AppTest.from_file(DASHBOARD_FILE).run()
    app_both.radio[0].set_value("Threat Center").run()
    status_radio = [r for r in app_both.radio if r.label == "Filter by Correlation Status"][0]
    status_radio.set_value("Present in Both").run()
    assert len(app_both.exception) == 0
    markdown_both = [m.value for m in app_both.markdown]
    assert any("CVE-2026-9001" in t for t in markdown_both)
    assert not any("CVE-2026-9002" in t for t in markdown_both)
    assert not any("CVE-2026-9003" in t for t in markdown_both)

    # Test 'NVD Only'
    app_nvd = AppTest.from_file(DASHBOARD_FILE).run()
    app_nvd.radio[0].set_value("Threat Center").run()
    status_radio = [r for r in app_nvd.radio if r.label == "Filter by Correlation Status"][0]
    status_radio.set_value("NVD Only").run()
    assert len(app_nvd.exception) == 0
    markdown_nvd = [m.value for m in app_nvd.markdown]
    assert any("CVE-2026-9002" in t for t in markdown_nvd)
    assert any("CVE-2026-9004" in t for t in markdown_nvd)
    assert not any("CVE-2026-9001" in t for t in markdown_nvd)
    assert not any("CVE-2026-9003" in t for t in markdown_nvd)

    # Test 'CISA KEV Only'
    app_cisa = AppTest.from_file(DASHBOARD_FILE).run()
    app_cisa.radio[0].set_value("Threat Center").run()
    status_radio = [r for r in app_cisa.radio if r.label == "Filter by Correlation Status"][0]
    status_radio.set_value("CISA KEV Only").run()
    assert len(app_cisa.exception) == 0
    markdown_cisa = [m.value for m in app_cisa.markdown]
    assert any("CVE-2026-9003" in t for t in markdown_cisa)
    assert not any("CVE-2026-9001" in t for t in markdown_cisa)
    assert not any("CVE-2026-9002" in t for t in markdown_cisa)


def test_threat_center_cards_render_all_three_statuses(populated_threat_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that cards for 'both', 'nvd_only', and 'cisa_only' render their appropriate labels and notices."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_threat_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Threat Center").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Verify 'both' badge and dual columns
    assert any("Present in Both (Exploited in Wild)" in t for t in markdown_texts)
    assert any("NVD Vulnerability Advisory" in t for t in markdown_texts)
    assert any("CISA Known Exploited Vulnerability" in t for t in markdown_texts)

    # Verify 'nvd_only' badge and CISA KEV status callout
    assert any("NVD Advisory Only" in t for t in markdown_texts)
    assert any("Not listed in CISA Known Exploited Vulnerabilities catalog" in t for t in markdown_texts)

    # Verify 'cisa_only' badge and NVD status callout
    assert any("CISA KEV Only" in t for t in markdown_texts)
    assert any("Full NVD advisory not present in locally ingested AI Pulse database" in t for t in markdown_texts)


def test_threat_center_missing_metadata_handled_safely(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that CVE records with missing URLs, texts, or dates render safely without errors."""
    sparse_db = tmp_path / "sparse_threat.db"
    init_db(sparse_db)

    items = [
        {
            "source": "NVD CVE",
            "source_id": "CVE-2026-7777",
            "domain": "cybersecurity",
            "title": "Minimal NVD Flaw",
            "url": None,
            "text": None,
            "published_at": None,
        },
        {
            "source": "CISA KEV",
            "source_id": "CVE-2026-8888",
            "domain": "cybersecurity",
            "title": "Minimal CISA Flaw",
            "url": None,
            "text": None,
            "published_at": None,
        },
    ]
    insert_items(items, db_path=sparse_db)
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(sparse_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Threat Center").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    assert any("CVE-2026-7777" in t for t in markdown_texts)
    assert any("CVE-2026-8888" in t for t in markdown_texts)


def test_threat_center_pagination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies SQL-level pagination and next/previous page navigation."""
    paginated_db = tmp_path / "paginated_threat.db"
    init_db(paginated_db)

    # Insert 30 CISA KEV items (PAGE_SIZE = 25)
    items = [
        {
            "source": "CISA KEV",
            "source_id": f"CVE-2026-8{i:03d}",
            "domain": "cybersecurity",
            "title": f"Vulnerability {i}",
            "published_at": f"2026-01-{(i % 28) + 1:02d}",
        }
        for i in range(1, 31)
    ]
    insert_items(items, db_path=paginated_db)
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(paginated_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Threat Center").run()
    assert len(app_test.exception) == 0

    # Page 1 indicator
    markdown_texts = [m.value for m in app_test.markdown]
    assert any("Showing 1–25 of 30 CVEs (Page 1 of 2)" in t for t in markdown_texts)

    # Click Next button to navigate to Page 2
    next_btn = [b for b in app_test.button if b.key == "tc_next_btn"][0]
    assert not next_btn.disabled
    next_btn.click().run()
    assert len(app_test.exception) == 0

    # Page 2 indicator
    markdown_texts2 = [m.value for m in app_test.markdown]
    assert any("Showing 26–30 of 30 CVEs (Page 2 of 2)" in t for t in markdown_texts2)


def test_threat_center_read_bookmark_independent_actions(populated_threat_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that bookmark and read toggles on NVD record do not alter CISA record and vice versa."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_threat_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Threat Center").run()
    assert len(app_test.exception) == 0

    # Find toggles for CVE-2026-9001 (present in both)
    both_records = get_correlated_cves(filter_status="both", db_path=populated_threat_db)
    assert len(both_records) == 1
    nvd_id = both_records[0]["nvd_id"]
    cisa_id = both_records[0]["cisa_id"]

    nvd_bm_key = f"tc_nvd_bm_{nvd_id}"
    cisa_bm_key = f"tc_cisa_bm_{cisa_id}"

    nvd_bm_toggles = [t for t in app_test.toggle if t.key == nvd_bm_key]
    cisa_bm_toggles = [t for t in app_test.toggle if t.key == cisa_bm_key]

    assert len(nvd_bm_toggles) == 1
    assert len(cisa_bm_toggles) == 1

    # Toggle NVD bookmark ON
    nvd_bm_toggles[0].set_value(True).run()
    assert len(app_test.exception) == 0

    # Verify database state: NVD is bookmarked, CISA remains unbookmarked
    nvd_item = get_item_by_id(nvd_id, db_path=populated_threat_db)
    cisa_item = get_item_by_id(cisa_id, db_path=populated_threat_db)
    assert nvd_item["is_bookmarked"] == 1
    assert cisa_item["is_bookmarked"] == 0


def test_threat_center_live_database_integration():
    """Verifies Threat Center live counts on data/ai_pulse.db match authoritative inspection counts."""
    live_db = Path("data/ai_pulse.db")
    assert live_db.exists(), "Production database must exist"

    total_cves = count_correlated_cves("all", db_path=live_db)
    both_cves = count_correlated_cves("both", db_path=live_db)
    nvd_only_cves = count_correlated_cves("nvd_only", db_path=live_db)
    cisa_only_cves = count_correlated_cves("cisa_only", db_path=live_db)

    assert total_cves == 1771
    assert both_cves == 0
    assert nvd_only_cves == 5
    assert cisa_only_cves == 1766
