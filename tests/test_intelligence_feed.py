"""Tests for the Streamlit Intelligence Feed (arXiv records).

Validates display of arXiv research papers, metadata badges, expandable abstracts,
bookmark/read toggles, empty states, and metrics.
"""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

from app.dashboard import (
    fetch_arxiv_feed_data,
    fetch_feed_data,
    format_item_text,
    get_dashboard_db_path,
)
from services.database import get_item_by_id, init_db, insert_items


DASHBOARD_FILE = str(Path(__file__).resolve().parent.parent / "app" / "dashboard.py")


@pytest.fixture
def empty_test_db(tmp_path: Path) -> Path:
    """Provides an initialized, empty SQLite database."""
    db_file = tmp_path / "empty_ai_pulse.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def populated_test_db(tmp_path: Path) -> Path:
    """Provides an initialized SQLite database with mixed records (arXiv and others)."""
    db_file = tmp_path / "populated_feed_pulse.db"
    init_db(db_file)

    sample_items = [
        # Item 1: arXiv, unread, unbookmarked
        {
            "source": "arXiv",
            "source_id": "2411.0001",
            "domain": "AI research",
            "title": "Frontier Model Reasoning with Tree of Thoughts",
            "url": "http://arxiv.org/abs/2411.0001v1",
            "text": "This paper explores tree-of-thought prompting in frontier models.",
            "published_at": "2024-11-20T10:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 2: arXiv, read, bookmarked
        {
            "source": "arXiv",
            "source_id": "2411.0002",
            "domain": "AI research",
            "title": "Scaling Laws for RAG Systems",
            "url": "http://arxiv.org/abs/2411.0002v1",
            "text": "An empirical analysis of retrieval-augmented generation at scale.",
            "published_at": "2024-11-25T14:30:00Z",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 3: non-arXiv source (cybersecurity)
        {
            "source": "NVD CVE",
            "source_id": "CVE-2026-9999",
            "domain": "cybersecurity",
            "title": "Remote Code Execution in Agent Runtime",
            "url": "https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2026-9999",
            "text": "Buffer overflow vulnerability.",
            "published_at": "2026-01-10T12:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
    ]
    insert_items(sample_items, db_path=db_file)
    return db_file


def test_fetch_arxiv_feed_data_empty_db(empty_test_db: Path):
    """Verifies fetch_arxiv_feed_data returns empty list and zero metrics for an empty database."""
    feed = fetch_arxiv_feed_data(db_path=empty_test_db)
    assert feed["error"] is None
    assert feed["total"] == 0
    assert feed["unread"] == 0
    assert feed["bookmarked"] == 0
    assert len(feed["items"]) == 0


def test_fetch_arxiv_feed_data_filters_only_arxiv(populated_test_db: Path):
    """Verifies that fetch_arxiv_feed_data returns ONLY arXiv items."""
    feed = fetch_arxiv_feed_data(db_path=populated_test_db)
    assert feed["error"] is None
    assert feed["total"] == 2
    assert feed["unread"] == 1
    assert feed["bookmarked"] == 1
    assert len(feed["items"]) == 2
    assert all(it["source"] == "arXiv" for it in feed["items"])


def test_intelligence_feed_empty_state_rendering(empty_test_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies the empty state notice and 0 metric on the Intelligence Feed page."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(empty_test_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    # Navigate to Intelligence Feed
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    assert any("arXiv Papers Stored" in t for t in markdown_texts)
    assert any("No arXiv Research Papers Found" in t for t in markdown_texts)


def test_intelligence_feed_displays_paper_cards(populated_test_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies paper cards display title links, labels, date, and expandable abstract."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_test_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    # Navigate to Intelligence Feed
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Metric showing stored arXiv papers (count: 2)
    assert any("arXiv Papers Stored" in t for t in markdown_texts)

    # Both arXiv titles displayed as links
    assert any("Frontier Model Reasoning with Tree of Thoughts" in t for t in markdown_texts)
    assert any("http://arxiv.org/abs/2411.0001v1" in t for t in markdown_texts)
    assert any("Scaling Laws for RAG Systems" in t for t in markdown_texts)
    assert any("http://arxiv.org/abs/2411.0002v1" in t for t in markdown_texts)

    # Non-arXiv record is NOT displayed
    assert not any("Remote Code Execution in Agent Runtime" in t for t in markdown_texts)

    # Source label: arXiv
    assert any("Source: arXiv" in t for t in markdown_texts)

    # Domain label: AI research
    assert any("Domain: AI research" in t for t in markdown_texts)

    # Publication date displayed
    assert any("Publication Date:" in t for t in markdown_texts)
    assert any("2024-11-20T10:00:00Z" in t for t in markdown_texts)

    # Expandable section for abstract
    expander_labels = [exp.label for exp in app_test.expander]
    assert "Abstract" in expander_labels

    # Abstract text is rendered inside expander
    assert any("tree-of-thought prompting" in t for t in markdown_texts)


def test_intelligence_feed_bookmark_toggle(populated_test_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies bookmark toggle updates is_bookmarked in SQLite via update_bookmark_status."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_test_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()

    # Find the bookmark toggle for item 1 (initially False)
    item_1 = get_item_by_id(1, db_path=populated_test_db)
    assert item_1["is_bookmarked"] == 0

    # Locate toggle by its specific key
    bm_toggle_1 = [t for t in app_test.toggle if t.key == "arxiv_bm_1"][0]
    assert bm_toggle_1.value is False

    # Toggle item 1 bookmark to True
    bm_toggle_1.set_value(True).run()
    assert len(app_test.exception) == 0

    # Verify SQLite database was updated
    updated_1 = get_item_by_id(1, db_path=populated_test_db)
    assert updated_1["is_bookmarked"] == 1


def test_intelligence_feed_read_toggle(populated_test_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies read toggle updates is_read in SQLite via update_read_status."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_test_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()

    # Find the read toggle for item 1 (initially False)
    item_1 = get_item_by_id(1, db_path=populated_test_db)
    assert item_1["is_read"] == 0

    # Locate toggle by its specific key
    read_toggle_1 = [t for t in app_test.toggle if t.key == "arxiv_read_1"][0]
    assert read_toggle_1.value is False

    # Toggle item 1 read to True
    read_toggle_1.set_value(True).run()
    assert len(app_test.exception) == 0

    # Verify SQLite database was updated
    updated_1 = get_item_by_id(1, db_path=populated_test_db)
    assert updated_1["is_read"] == 1


def test_intelligence_feed_retrieves_all_10_live_arxiv_records():
    """Verifies that the dashboard retrieves all 10 real arXiv records stored in data/ai_pulse.db."""
    live_db = Path("data") / "ai_pulse.db"
    assert live_db.exists(), "data/ai_pulse.db must exist with ingested arXiv records"

    feed = fetch_arxiv_feed_data(db_path=live_db)
    assert feed["error"] is None
    assert feed["total"] == 10
    assert len(feed["items"]) == 10

    # Verify all items are from arXiv and AI research
    for it in feed["items"]:
        assert it["source"] == "arXiv"
        assert it["domain"] == "AI research"
        assert it["url"].startswith("http://arxiv.org/abs/")
        assert len(it["title"]) > 0
        assert len(it["text"]) > 0
        assert it["published_at"] is not None

    # Test full UI rendering of all 10 live records via AppTest
    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Metric shows 10 papers
    assert any("arXiv Papers Stored" in t for t in markdown_texts)
    assert any(">10<" in t or "10" in t for t in markdown_texts)

    # Verify all 10 titles are rendered in the UI
    for it in feed["items"]:
        assert any(it["title"] in t for t in markdown_texts)


@pytest.fixture
def populated_multi_source_db(tmp_path: Path) -> Path:
    """Provides a database populated with arXiv, Hacker News, and third-party sources."""
    db_file = tmp_path / "multi_feed_pulse.db"
    init_db(db_file)

    sample_items = [
        # Item 1: arXiv, unread, unbookmarked
        {
            "source": "arXiv",
            "source_id": "2411.0001",
            "domain": "AI research",
            "title": "Frontier Model Reasoning with Tree of Thoughts",
            "url": "http://arxiv.org/abs/2411.0001v1",
            "text": "This paper explores tree-of-thought prompting.",
            "published_at": "2024-11-20T10:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 2: arXiv, read, bookmarked
        {
            "source": "arXiv",
            "source_id": "2411.0002",
            "domain": "AI research",
            "title": "Scaling Laws for RAG Systems",
            "url": "http://arxiv.org/abs/2411.0002v1",
            "text": "An empirical analysis of retrieval-augmented generation.",
            "published_at": "2024-11-25T14:30:00Z",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 3: Hacker News, with URL, unread, unbookmarked, HTML in text
        {
            "source": "Hacker News",
            "source_id": "hn_3001",
            "domain": "dev-tools",
            "title": "Show HN: Fast Vector Search in Rust",
            "url": "https://github.com/example/fast-vector-search",
            "text": "We built a new vector database.<p>Check out our demo: <a href=\"https:&#x2F;&#x2F;example.com\">link</a> &amp; benchmarks.",
            "published_at": "2026-11-01T15:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 4: Hacker News, NO URL (Ask HN), read, bookmarked
        {
            "source": "Hacker News",
            "source_id": "hn_3002",
            "domain": "dev-tools",
            "title": "Ask HN: What is your preferred local LLM setup in 2026?",
            "url": None,
            "text": "I am curious what developers are using.<p>Ollama, vLLM, or LM Studio?<br>Let me know your thoughts.",
            "published_at": "2026-11-01T16:00:00Z",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 5: Unimplemented source (cybersecurity NVD)
        {
            "source": "NVD CVE",
            "source_id": "CVE-2026-8888",
            "domain": "cybersecurity",
            "title": "Critical Buffer Overflow in Network Daemon",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-8888",
            "text": "Advisory details.",
            "published_at": "2026-01-01T00:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
    ]
    insert_items(sample_items, db_path=db_file)
    return db_file


def test_format_item_text_html_entities_and_markup():
    """Verifies that format_item_text decodes HTML entities and strips HTML markup cleanly."""
    raw = "Hi everyone!<p>Check out sweet-search.<br>Here is a <a href=\"https:&#x2F;&#x2F;youtube.com\">video</a> &amp; promo.</p>"
    cleaned = format_item_text(raw)
    assert "<p>" not in cleaned
    assert "<br>" not in cleaned
    assert "<a" not in cleaned
    assert "</a>" not in cleaned
    assert "&#x2F;" not in cleaned
    assert "&amp;" not in cleaned
    assert "&" in cleaned
    assert "Hi everyone!" in cleaned
    assert "Check out sweet-search." in cleaned

    # Test None and empty string
    assert format_item_text(None) == "No content available."
    assert format_item_text("") == "No content available."


def test_fetch_feed_data_multi_source(populated_multi_source_db: Path):
    """Verifies fetch_feed_data filtering and multi-source count metrics."""
    # All Sources: returns only supported sources (arXiv + Hacker News = 4), excluding NVD CVE
    all_data = fetch_feed_data(selected_source="All Sources", db_path=populated_multi_source_db)
    assert all_data["error"] is None
    assert all_data["total_items"] == 4
    assert all_data["total_arxiv"] == 2
    assert all_data["total_hn"] == 2
    assert all_data["unread"] == 2  # Item 1 and Item 3
    assert all_data["bookmarked"] == 2  # Item 2 and Item 4
    assert len(all_data["items"]) == 4
    assert not any(it["source"] == "NVD CVE" for it in all_data["items"])

    # Filter to arXiv only
    arxiv_data = fetch_feed_data(selected_source="arXiv", db_path=populated_multi_source_db)
    assert len(arxiv_data["items"]) == 2
    assert all(it["source"] == "arXiv" for it in arxiv_data["items"])

    # Filter to Hacker News only
    hn_data = fetch_feed_data(selected_source="Hacker News", db_path=populated_multi_source_db)
    assert len(hn_data["items"]) == 2
    assert all(it["source"] == "Hacker News" for it in hn_data["items"])


def test_intelligence_feed_displays_hacker_news_and_arxiv(populated_multi_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that the Intelligence Feed renders both arXiv and Hacker News stories in All Sources."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_multi_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Both arXiv and Hacker News titles present
    assert any("Frontier Model Reasoning with Tree of Thoughts" in t for t in markdown_texts)
    assert any("Show HN: Fast Vector Search in Rust" in t for t in markdown_texts)
    assert any("Ask HN: What is your preferred local LLM setup in 2026?" in t for t in markdown_texts)

    # Badges for Hacker News
    assert any("Source: Hacker News" in t for t in markdown_texts)
    assert any("Domain: dev-tools" in t for t in markdown_texts)

    # Badges for arXiv
    assert any("Source: arXiv" in t for t in markdown_texts)
    assert any("Domain: AI research" in t for t in markdown_texts)

    # Expanders: Abstract for arXiv, Story Text for Hacker News
    expander_labels = [exp.label for exp in app_test.expander]
    assert "Abstract" in expander_labels
    assert "Story Text" in expander_labels

    # Verified clean decoded text inside Story Text expander
    assert any("Check out our demo: link & benchmarks." in t for t in markdown_texts)


def test_intelligence_feed_handles_missing_urls(populated_multi_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies items with url=None are rendered as ordinary text without links or fake URLs."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_multi_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Item with URL (Item 3) should have a markdown link
    assert any("#### [Show HN: Fast Vector Search in Rust](https://github.com/example/fast-vector-search)" in t for t in markdown_texts)

    # Item without URL (Item 4) should NOT have a markdown link or fake URL
    assert any("#### Ask HN: What is your preferred local LLM setup in 2026?" in t for t in markdown_texts)
    assert not any("[Ask HN: What is your preferred local LLM setup in 2026?]" in t for t in markdown_texts)
    assert not any("(#)" in t for t in markdown_texts)


def test_intelligence_feed_source_filtering(populated_multi_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies filtering by 'All Sources', 'arXiv', and 'Hacker News'."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_multi_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    # Locate source filter radio
    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    assert source_radio.value == "All Sources"

    # Filter to arXiv
    source_radio.set_value("arXiv").run()
    assert len(app_test.exception) == 0
    arxiv_markdown = [m.value for m in app_test.markdown]
    assert any("Frontier Model Reasoning" in t for t in arxiv_markdown)
    assert not any("Show HN: Fast Vector Search" in t for t in arxiv_markdown)

    # Re-fetch source radio from current app_test tree and filter to Hacker News
    hn_source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    hn_source_radio.set_value("Hacker News").run()
    assert len(app_test.exception) == 0
    hn_markdown = [m.value for m in app_test.markdown]
    assert any("Show HN: Fast Vector Search" in t for t in hn_markdown)
    assert not any("Frontier Model Reasoning" in t for t in hn_markdown)


def test_intelligence_feed_hn_bookmark_and_read_toggles(populated_multi_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies bookmark and read toggles for Hacker News items update SQLite database."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_multi_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    # Locate Hacker News Item 3 (id=3, initially unbookmarked and unread)
    item_3 = get_item_by_id(3, db_path=populated_multi_source_db)
    assert item_3["is_bookmarked"] == 0
    assert item_3["is_read"] == 0

    # Toggle bookmark for Item 3
    hn_bm_toggle = [t for t in app_test.toggle if t.key == "hn_bm_3"][0]
    assert hn_bm_toggle.value is False
    hn_bm_toggle.set_value(True).run()
    assert len(app_test.exception) == 0

    updated_3 = get_item_by_id(3, db_path=populated_multi_source_db)
    assert updated_3["is_bookmarked"] == 1

    # Toggle read for Item 3
    hn_read_toggle = [t for t in app_test.toggle if t.key == "hn_read_3"][0]
    assert hn_read_toggle.value is False
    hn_read_toggle.set_value(True).run()
    assert len(app_test.exception) == 0

    updated_3 = get_item_by_id(3, db_path=populated_multi_source_db)
    assert updated_3["is_read"] == 1


def test_intelligence_feed_empty_state_per_source(populated_test_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that selecting Hacker News on an arXiv-only database renders the specific empty state."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_test_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    # Filter to Hacker News (no HN records exist in populated_test_db)
    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("Hacker News").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    assert any("No Hacker News Stories Found" in t for t in markdown_texts)


def test_intelligence_feed_empty_state_github_releases(populated_test_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that selecting GitHub Releases on an arXiv-only database renders the specific empty state."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_test_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    # Filter to GitHub Releases (no GitHub Releases records exist in populated_test_db)
    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("GitHub Releases").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    assert any("No GitHub Releases Found" in t for t in markdown_texts)


@pytest.fixture
def populated_three_source_db(tmp_path: Path) -> Path:
    """Provides a database populated with arXiv, Hacker News, GitHub Releases, and third-party sources."""
    db_file = tmp_path / "three_source_feed_pulse.db"
    init_db(db_file)

    sample_items = [
        # Item 1: arXiv, unread, unbookmarked
        {
            "source": "arXiv",
            "source_id": "2411.0001",
            "domain": "AI research",
            "title": "Frontier Model Reasoning with Tree of Thoughts",
            "url": "http://arxiv.org/abs/2411.0001v1",
            "text": "This paper explores tree-of-thought prompting.",
            "published_at": "2024-11-20T10:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 2: arXiv, read, bookmarked
        {
            "source": "arXiv",
            "source_id": "2411.0002",
            "domain": "AI research",
            "title": "Scaling Laws for RAG Systems",
            "url": "http://arxiv.org/abs/2411.0002v1",
            "text": "An empirical analysis of retrieval-augmented generation.",
            "published_at": "2024-11-25T14:30:00Z",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 3: Hacker News, with URL, unread, unbookmarked, HTML in text
        {
            "source": "Hacker News",
            "source_id": "hn_3001",
            "domain": "dev-tools",
            "title": "Show HN: Fast Vector Search in Rust",
            "url": "https://github.com/example/fast-vector-search",
            "text": "We built a new vector database.<p>Check out our demo: <a href=\"https:&#x2F;&#x2F;example.com\">link</a> &amp; benchmarks.",
            "published_at": "2026-11-01T15:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 4: Hacker News, NO URL (Ask HN), read, bookmarked
        {
            "source": "Hacker News",
            "source_id": "hn_3002",
            "domain": "dev-tools",
            "title": "Ask HN: What is your preferred local LLM setup in 2026?",
            "url": None,
            "text": "I am curious what developers are using.<p>Ollama, vLLM, or LM Studio?<br>Let me know your thoughts.",
            "published_at": "2026-11-01T16:00:00Z",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 5: GitHub Releases, with URL, unread, unbookmarked, HTML in description
        {
            "source": "GitHub Releases",
            "source_id": "gh_5001",
            "domain": "dev-tools",
            "title": "Ollama v0.4.0: Local LLM Runner",
            "url": "https://github.com/ollama/ollama/releases/tag/v0.4.0",
            "text": "Major release with structured outputs.<p>Added support for <a href=\"https:&#x2F;&#x2F;ollama.com\">Llama 3.2</a> &amp; tool calling.</p>",
            "published_at": "2026-10-30T12:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 6: GitHub Releases, NO URL, read, bookmarked
        {
            "source": "GitHub Releases",
            "source_id": "gh_5002",
            "domain": "dev-tools",
            "title": "vLLM v0.6.2 Internal Release",
            "url": None,
            "text": "Performance improvements for chunked prefill.<br>No external link available.",
            "published_at": "2026-10-31T09:00:00Z",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 7: Unimplemented source (cybersecurity NVD)
        {
            "source": "NVD CVE",
            "source_id": "CVE-2026-8888",
            "domain": "cybersecurity",
            "title": "Critical Buffer Overflow in Network Daemon",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-8888",
            "text": "Advisory details.",
            "published_at": "2026-01-01T00:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
    ]
    insert_items(sample_items, db_path=db_file)
    return db_file


def test_fetch_feed_data_three_sources(populated_three_source_db: Path):
    """Verifies fetch_feed_data filtering and three-source count metrics."""
    # All Sources: returns only supported sources (arXiv=2 + HN=2 + GitHub=2 -> 6), excluding NVD CVE
    all_data = fetch_feed_data(selected_source="All Sources", db_path=populated_three_source_db)
    assert all_data["error"] is None
    assert all_data["total_items"] == 6
    assert all_data["total_arxiv"] == 2
    assert all_data["total_hn"] == 2
    assert all_data["total_gh"] == 2
    assert all_data["unread"] == 3  # Item 1 (arXiv), Item 3 (HN), Item 5 (GitHub)
    assert all_data["bookmarked"] == 3  # Item 2 (arXiv), Item 4 (HN), Item 6 (GitHub)
    assert len(all_data["items"]) == 6
    assert not any(it["source"] == "NVD CVE" for it in all_data["items"])

    # Filter to arXiv only
    arxiv_data = fetch_feed_data(selected_source="arXiv", db_path=populated_three_source_db)
    assert len(arxiv_data["items"]) == 2
    assert all(it["source"] == "arXiv" for it in arxiv_data["items"])

    # Filter to Hacker News only
    hn_data = fetch_feed_data(selected_source="Hacker News", db_path=populated_three_source_db)
    assert len(hn_data["items"]) == 2
    assert all(it["source"] == "Hacker News" for it in hn_data["items"])

    # Filter to GitHub Releases only
    gh_data = fetch_feed_data(selected_source="GitHub Releases", db_path=populated_three_source_db)
    assert len(gh_data["items"]) == 2
    assert all(it["source"] == "GitHub Releases" for it in gh_data["items"])


def test_intelligence_feed_displays_all_three_sources(populated_three_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that the Intelligence Feed renders arXiv, Hacker News, and GitHub Releases in All Sources."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_three_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Titles from all three sources present
    assert any("Frontier Model Reasoning with Tree of Thoughts" in t for t in markdown_texts)
    assert any("Show HN: Fast Vector Search in Rust" in t for t in markdown_texts)
    assert any("Ollama v0.4.0: Local LLM Runner" in t for t in markdown_texts)
    assert any("vLLM v0.6.2 Internal Release" in t for t in markdown_texts)

    # Badges for GitHub Releases
    assert any("Source: GitHub Releases" in t for t in markdown_texts)
    assert any("Domain: dev-tools" in t for t in markdown_texts)

    # Badges for Hacker News and arXiv
    assert any("Source: Hacker News" in t for t in markdown_texts)
    assert any("Source: arXiv" in t for t in markdown_texts)

    # Metrics row showing 6 Total Items and GitHub Releases
    assert any("GitHub Releases" in t for t in markdown_texts)

    # Expanders: Abstract for arXiv, Story Text for HN, Release Notes for GitHub Releases
    expander_labels = [exp.label for exp in app_test.expander]
    assert "Abstract" in expander_labels
    assert "Story Text" in expander_labels
    assert "Release Notes" in expander_labels


def test_intelligence_feed_github_releases_source_filtering(populated_three_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies filtering by 'GitHub Releases' displays only releases and hides arXiv and HN."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_three_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    # Locate source filter radio
    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    assert source_radio.value == "All Sources"

    # Filter to GitHub Releases
    source_radio.set_value("GitHub Releases").run()
    assert len(app_test.exception) == 0
    gh_markdown = [m.value for m in app_test.markdown]
    assert any("Ollama v0.4.0: Local LLM Runner" in t for t in gh_markdown)
    assert any("vLLM v0.6.2 Internal Release" in t for t in gh_markdown)
    assert not any("Frontier Model Reasoning" in t for t in gh_markdown)
    assert not any("Show HN: Fast Vector Search" in t for t in gh_markdown)


def test_intelligence_feed_github_releases_missing_url_handling(populated_three_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies GitHub Releases items with url=None render plain text without links or dummy URLs."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_three_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Item with URL (Item 5) should have a markdown link
    assert any("#### [Ollama v0.4.0: Local LLM Runner](https://github.com/ollama/ollama/releases/tag/v0.4.0)" in t for t in markdown_texts)

    # Item without URL (Item 6) should NOT have a markdown link or fake URL
    assert any("#### vLLM v0.6.2 Internal Release" in t for t in markdown_texts)
    assert not any("[vLLM v0.6.2 Internal Release]" in t for t in markdown_texts)
    assert not any("(#)" in t for t in markdown_texts)


def test_intelligence_feed_github_releases_html_entity_handling(populated_three_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that release notes with HTML markup and entities are decoded and stripped safely."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_three_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    # Check that '<p>', '<a', and '&amp;' were cleaned and '&' is present
    assert any("Added support for Llama 3.2 & tool calling." in t for t in markdown_texts)


def test_intelligence_feed_github_releases_toggles(populated_three_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies bookmark and read toggles for GitHub Releases items update the SQLite database."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_three_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    # Locate GitHub Releases Item 5 (id=5, initially unbookmarked and unread)
    item_5 = get_item_by_id(5, db_path=populated_three_source_db)
    assert item_5["is_bookmarked"] == 0
    assert item_5["is_read"] == 0

    # Toggle bookmark for Item 5
    gh_bm_toggle = [t for t in app_test.toggle if t.key == "gh_bm_5"][0]
    assert gh_bm_toggle.value is False
    gh_bm_toggle.set_value(True).run()
    assert len(app_test.exception) == 0

    updated_5 = get_item_by_id(5, db_path=populated_three_source_db)
    assert updated_5["is_bookmarked"] == 1

    # Toggle read for Item 5
    gh_read_toggle = [t for t in app_test.toggle if t.key == "gh_read_5"][0]
    assert gh_read_toggle.value is False
    gh_read_toggle.set_value(True).run()
    assert len(app_test.exception) == 0

    updated_5 = get_item_by_id(5, db_path=populated_three_source_db)
    assert updated_5["is_read"] == 1


def test_intelligence_feed_retrieves_live_github_releases_records():
    """Verifies retrieval and rendering of all 10 live GitHub Releases records from data/ai_pulse.db."""
    live_db = Path("data") / "ai_pulse.db"
    assert live_db.exists(), "data/ai_pulse.db must exist with ingested records"

    gh_feed = fetch_feed_data(selected_source="GitHub Releases", db_path=live_db)
    assert gh_feed["error"] is None
    assert gh_feed["total_gh"] == 10
    assert len(gh_feed["items"]) == 10

    for it in gh_feed["items"]:
        assert it["source"] == "GitHub Releases"
        assert it["domain"] == "dev-tools"
        assert len(it["title"]) > 0
        assert it["published_at"] is not None

    # Verify rendering via Streamlit AppTest
    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("GitHub Releases").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    assert any("GitHub Releases" in t for t in markdown_texts)
    for it in gh_feed["items"]:
        clean_title = it["title"].replace("[", "\\[").replace("]", "\\]")
        assert any(clean_title in t or it["title"] in t for t in markdown_texts)


def test_intelligence_feed_retrieves_all_20_live_records():
    """Verifies retrieval and rendering of all live records (arXiv, Hacker News & GitHub Releases) from data/ai_pulse.db."""
    live_db = Path("data") / "ai_pulse.db"
    assert live_db.exists(), "data/ai_pulse.db must exist with ingested records"

    feed = fetch_feed_data(selected_source="All Sources", db_path=live_db)
    assert feed["error"] is None
    assert feed["total_items"] >= 20
    assert feed["total_arxiv"] >= 10
    assert feed["total_hn"] >= 10
    assert feed["total_gh"] >= 10
    assert feed["total_items"] == feed["total_arxiv"] + feed["total_hn"] + feed["total_gh"]
    assert len(feed["items"]) == feed["total_items"]

    # Verify counts per source
    arxiv_items = [it for it in feed["items"] if it["source"] == "arXiv"]
    hn_items = [it for it in feed["items"] if it["source"] == "Hacker News"]
    gh_items = [it for it in feed["items"] if it["source"] == "GitHub Releases"]
    assert len(arxiv_items) == feed["total_arxiv"]
    assert len(hn_items) == feed["total_hn"]
    assert len(gh_items) == feed["total_gh"]

    # Verify Hacker News records properties
    hn_null_urls = [it for it in hn_items if it["url"] is None]
    assert len(hn_null_urls) >= 3  # Ask HN / discussions with null URLs

    # Verify GitHub Releases records properties
    for it in gh_items:
        assert it["domain"] == "dev-tools"
        assert it["published_at"] is not None

    # Run Streamlit AppTest to verify full dashboard execution
    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Verify metrics row displays total items, arXiv, Hacker News, GitHub Releases
    assert any("Total Items" in t for t in markdown_texts)
    assert any("arXiv Papers Stored" in t for t in markdown_texts)
    assert any("Hacker News Stories" in t for t in markdown_texts)
    assert any("GitHub Releases" in t for t in markdown_texts)
    assert any(str(feed["total_items"]) in t for t in markdown_texts)

    # Verify all titles are rendered in the dashboard UI
    for it in feed["items"]:
        clean_title = it["title"].replace("[", "\\[").replace("]", "\\]")
        assert any(clean_title in t or it["title"] in t for t in markdown_texts)
