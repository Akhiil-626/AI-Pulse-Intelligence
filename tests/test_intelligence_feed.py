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
        # Item 3: non-arXiv source (cybersecurity Unsupported Source)
        {
            "source": "Unsupported Source",
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

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("arXiv").run()
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
        # Item 5: Unimplemented source (cybersecurity Unsupported Source)
        {
            "source": "Unsupported Source",
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
    # All Sources: returns only supported sources (arXiv + Hacker News = 4), excluding Unsupported Source
    all_data = fetch_feed_data(selected_source="All Sources", db_path=populated_multi_source_db)
    assert all_data["error"] is None
    assert all_data["total_items"] == 4
    assert all_data["total_arxiv"] == 2
    assert all_data["total_hn"] == 2
    assert all_data["unread"] == 2  # Item 1 and Item 3
    assert all_data["bookmarked"] == 2  # Item 2 and Item 4
    assert len(all_data["items"]) == 4
    assert not any(it["source"] == "Unsupported Source" for it in all_data["items"])

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
        # Item 7: Unimplemented source (cybersecurity Unsupported Source)
        {
            "source": "Unsupported Source",
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
    # All Sources: returns only supported sources (arXiv=2 + HN=2 + GitHub=2 -> 6), excluding Unsupported Source
    all_data = fetch_feed_data(selected_source="All Sources", db_path=populated_three_source_db)
    assert all_data["error"] is None
    assert all_data["total_items"] == 6
    assert all_data["total_arxiv"] == 2
    assert all_data["total_hn"] == 2
    assert all_data["total_gh"] == 2
    assert all_data["unread"] == 3  # Item 1 (arXiv), Item 3 (HN), Item 5 (GitHub)
    assert all_data["bookmarked"] == 3  # Item 2 (arXiv), Item 4 (HN), Item 6 (GitHub)
    assert len(all_data["items"]) == 6
    assert not any(it["source"] == "Unsupported Source" for it in all_data["items"])

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
    """Verifies retrieval and rendering of all live GitHub Releases records from data/ai_pulse.db."""
    live_db = Path("data") / "ai_pulse.db"
    assert live_db.exists(), "data/ai_pulse.db must exist with ingested records"

    gh_feed = fetch_feed_data(selected_source="GitHub Releases", db_path=live_db)
    assert gh_feed["error"] is None
    assert gh_feed["total_gh"] >= 10
    assert len(gh_feed["items"]) == gh_feed["total_gh"]

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
    """Verifies retrieval and rendering of all live records (arXiv, Hacker News, GitHub Releases, NVD CVE & CISA KEV) from data/ai_pulse.db."""
    live_db = Path("data") / "ai_pulse.db"
    assert live_db.exists(), "data/ai_pulse.db must exist with ingested records"

    feed = fetch_feed_data(selected_source="All Sources", db_path=live_db)
    assert feed["error"] is None
    assert feed["total_items"] >= 20
    assert feed["total_arxiv"] >= 10
    assert feed["total_hn"] >= 10
    assert feed["total_gh"] >= 10
    assert feed["total_nvd"] >= 5
    assert feed["total_cisa"] >= 1700
    assert feed["total_items"] == feed["total_arxiv"] + feed["total_hn"] + feed["total_gh"] + feed["total_nvd"] + feed["total_cisa"]
    assert len(feed["items"]) == 100

    # Verify per-source individual retrieval of live records
    arxiv_feed = fetch_feed_data(selected_source="arXiv", db_path=live_db)
    hn_feed = fetch_feed_data(selected_source="Hacker News", db_path=live_db)
    gh_feed = fetch_feed_data(selected_source="GitHub Releases", db_path=live_db)
    nvd_feed = fetch_feed_data(selected_source="NVD CVE", db_path=live_db)
    cisa_feed = fetch_feed_data(selected_source="CISA KEV", db_path=live_db)

    assert len(arxiv_feed["items"]) == feed["total_arxiv"]
    assert len(hn_feed["items"]) == feed["total_hn"]
    assert len(gh_feed["items"]) == feed["total_gh"]
    assert len(nvd_feed["items"]) == feed["total_nvd"]
    assert len(cisa_feed["items"]) == 100  # paginated at 100

    # Verify Hacker News records properties
    hn_null_urls = [it for it in hn_feed["items"] if it["url"] is None]
    assert len(hn_null_urls) >= 3  # Ask HN / discussions with null URLs

    # Verify GitHub Releases records properties
    for it in gh_feed["items"]:
        assert it["domain"] == "dev-tools"
        assert it["published_at"] is not None

    # Verify NVD CVE records properties
    for it in nvd_feed["items"]:
        assert it["domain"] == "cybersecurity"
        assert it["published_at"] is not None
        assert it["source_id"].startswith("CVE-")

    # Verify CISA KEV records properties
    for it in cisa_feed["items"]:
        assert it["source"] == "CISA KEV"
        assert it["domain"] == "cybersecurity"
        assert it["published_at"] is not None
        assert it["source_id"].startswith("CVE-")

    # Run Streamlit AppTest to verify full dashboard execution
    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Verify metrics row displays total items, arXiv, Hacker News, GitHub Releases, NVD CVEs, CISA KEV
    assert any("Total Items" in t for t in markdown_texts)
    assert any("arXiv Papers Stored" in t for t in markdown_texts)
    assert any("Hacker News Stories" in t for t in markdown_texts)
    assert any("GitHub Releases" in t for t in markdown_texts)
    assert any("NVD CVEs" in t for t in markdown_texts)
    assert any("CISA KEV" in t for t in markdown_texts)
    assert any(str(feed["total_items"]) in t for t in markdown_texts)

    # Verify all titles are rendered in the dashboard UI
    for it in feed["items"]:
        if it["source"] in ("NVD CVE", "CISA KEV"):
            assert any(it["source_id"] in t for t in markdown_texts)
        else:
            clean_title = it["title"].replace("[", "\\[").replace("]", "\\]")
            assert any(clean_title in t or it["title"] in t for t in markdown_texts)


@pytest.fixture
def populated_four_source_db(tmp_path: Path) -> Path:
    """Provides an initialized SQLite database with four supported sources plus an unsupported source."""
    db_file = tmp_path / "four_source_feed_pulse.db"
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
        # Item 3: Hacker News, unread, unbookmarked
        {
            "source": "Hacker News",
            "source_id": "hn_3001",
            "domain": "dev-tools",
            "title": "Show HN: Fast local SQLite vector search in Python",
            "url": "https://github.com/example/fast-sqlite-vector",
            "text": "A minimal, dependency-free vector index built directly on top of SQLite.",
            "published_at": "2026-11-01T12:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 4: Hacker News, read, bookmarked
        {
            "source": "Hacker News",
            "source_id": "hn_3002",
            "domain": "dev-tools",
            "title": "Ask HN: What is your preferred local LLM setup in 2026?",
            "url": None,
            "text": "I am curious what developers are using.<p>Ollama, vLLM, or LM Studio?</p>",
            "published_at": "2026-11-01T16:00:00Z",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 5: GitHub Releases, unread, unbookmarked
        {
            "source": "GitHub Releases",
            "source_id": "gh_5001",
            "domain": "dev-tools",
            "title": "Ollama v0.4.0: Local Tool Calling & Structured Outputs",
            "url": "https://github.com/ollama/ollama/releases/tag/v0.4.0",
            "text": "Added support for Llama 3.2 & tool calling.",
            "published_at": "2026-11-01T08:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 6: GitHub Releases, read, bookmarked
        {
            "source": "GitHub Releases",
            "source_id": "gh_5002",
            "domain": "dev-tools",
            "title": "vLLM v0.6.2 Internal Release",
            "url": None,
            "text": "Performance improvements for chunked prefill.",
            "published_at": "2026-10-31T09:00:00Z",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 7: NVD CVE, unread, unbookmarked, with URL
        {
            "source": "NVD CVE",
            "source_id": "CVE-2025-62819",
            "domain": "cybersecurity",
            "title": "Heap buffer overflow in OpenSSL ASN.1 parser leading to remote denial of service or arbitrary code execution",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2025-62819",
            "text": "A heap-based buffer overflow flaw was found in OpenSSL. A remote attacker could send a specially crafted ASN.1 structure to cause memory corruption and arbitrary code execution.",
            "published_at": "2026-11-02T15:17:11.403",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 8: NVD CVE, read, bookmarked, NO URL
        {
            "source": "NVD CVE",
            "source_id": "CVE-2025-62820",
            "domain": "cybersecurity",
            "title": "SQL injection vulnerability in legacy authentication plugin",
            "url": None,
            "text": "An issue was discovered in legacy authentication plugin allowing SQL injection via username parameter in login forms.",
            "published_at": "2026-11-01T10:00:00Z",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 9: Unimplemented source (cybersecurity Unsupported Source)
        {
            "source": "Unsupported Source",
            "source_id": "CVE-2024-1234",
            "domain": "cybersecurity",
            "title": "Active exploitation of vulnerability in enterprise gateway",
            "url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
            "text": "Advisory details for catalog entry.",
            "published_at": "2024-05-01T00:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
    ]
    insert_items(sample_items, db_path=db_file)
    return db_file


def test_fetch_feed_data_four_sources(populated_four_source_db: Path):
    """Verifies fetch_feed_data filtering and four-source count metrics."""
    # All Sources: returns only supported sources (arXiv=2 + HN=2 + GitHub=2 + NVD=2 -> 8), excluding Unsupported Source
    all_data = fetch_feed_data(selected_source="All Sources", db_path=populated_four_source_db)
    assert all_data["error"] is None
    assert all_data["total_items"] == 8
    assert all_data["total_arxiv"] == 2
    assert all_data["total_hn"] == 2
    assert all_data["total_gh"] == 2
    assert all_data["total_nvd"] == 2
    assert all_data["unread"] == 4  # Items 1, 3, 5, 7
    assert all_data["bookmarked"] == 4  # Items 2, 4, 6, 8
    assert len(all_data["items"]) == 8
    assert not any(it["source"] == "Unsupported Source" for it in all_data["items"])

    # Filter to NVD CVE only
    nvd_data = fetch_feed_data(selected_source="NVD CVE", db_path=populated_four_source_db)
    assert len(nvd_data["items"]) == 2
    assert all(it["source"] == "NVD CVE" for it in nvd_data["items"])
    assert all(it["domain"] == "cybersecurity" for it in nvd_data["items"])


def test_intelligence_feed_displays_all_four_sources(populated_four_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that the Intelligence Feed renders arXiv, Hacker News, GitHub Releases, and NVD CVE in All Sources."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_four_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Verify metrics row cards
    assert any("Total Items" in t for t in markdown_texts)
    assert any("arXiv Papers Stored" in t for t in markdown_texts)
    assert any("Hacker News Stories" in t for t in markdown_texts)
    assert any("GitHub Releases" in t for t in markdown_texts)
    assert any("NVD CVEs" in t for t in markdown_texts)
    assert any("Unread Items" in t for t in markdown_texts)
    assert any("Bookmarked Items" in t for t in markdown_texts)

    # Verify source radio options
    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    assert "All Sources" in source_radio.options
    assert "arXiv" in source_radio.options
    assert "Hacker News" in source_radio.options
    assert "GitHub Releases" in source_radio.options
    assert "NVD CVE" in source_radio.options
    assert "CISA KEV" in source_radio.options

    # Verify presence of records from all 4 sources
    assert any("Frontier Model Reasoning with Tree of Thoughts" in t for t in markdown_texts)
    assert any("Show HN: Fast local SQLite vector search in Python" in t for t in markdown_texts)
    assert any("Ollama v0.4.0: Local Tool Calling & Structured Outputs" in t for t in markdown_texts)
    assert any("CVE-2025-62819" in t for t in markdown_texts)

    # Verify source badges
    assert any("Source: arXiv" in t for t in markdown_texts)
    assert any("Source: Hacker News" in t for t in markdown_texts)
    assert any("Source: GitHub Releases" in t for t in markdown_texts)
    assert any("Source: NVD CVE" in t for t in markdown_texts)

    # Verify domain badges
    assert any("Domain: AI research" in t for t in markdown_texts)
    assert any("Domain: dev-tools" in t for t in markdown_texts)
    assert any("Domain: cybersecurity" in t for t in markdown_texts)

    # Unimplemented source (Unsupported Source) must NOT be displayed
    assert not any("Active exploitation of vulnerability in enterprise gateway" in t for t in markdown_texts)


def test_intelligence_feed_nvd_source_filtering(populated_four_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that selecting the NVD CVE filter displays only NVD records and hides other sources."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_four_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("NVD CVE").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Displays NVD CVE records prominently
    assert any("CVE-2025-62819" in t for t in markdown_texts)
    assert any("CVE-2025-62820" in t for t in markdown_texts)

    # Hides arXiv, Hacker News, and GitHub Releases records
    assert not any("Frontier Model Reasoning with Tree of Thoughts" in t for t in markdown_texts)
    assert not any("Scaling Laws for RAG Systems" in t for t in markdown_texts)
    assert not any("Show HN: Fast local SQLite vector search in Python" in t for t in markdown_texts)
    assert not any("Ask HN: What is your preferred local LLM setup in 2026?" in t for t in markdown_texts)
    assert not any("Ollama v0.4.0: Local Tool Calling & Structured Outputs" in t for t in markdown_texts)
    assert not any("vLLM v0.6.2 Internal Release" in t for t in markdown_texts)


def test_intelligence_feed_nvd_card_content_and_prominent_cve(populated_four_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies NVD CVE card layout: prominent CVE ID, official link, badges, date, and expandable full description."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_four_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("NVD CVE").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # CVE ID in title and link
    assert any("CVE-2025-62819" in t for t in markdown_texts)
    assert any("https://nvd.nist.gov/vuln/detail/CVE-2025-62819" in t for t in markdown_texts)

    # Badges
    assert any("Source: NVD CVE" in t for t in markdown_texts)
    assert any("Domain: cybersecurity" in t for t in markdown_texts)

    # Publication date
    assert any("2026-11-02T15:17:11.403" in t for t in markdown_texts)

    # Full description in expander
    assert any("A heap-based buffer overflow flaw was found in OpenSSL." in t for t in markdown_texts)


def test_intelligence_feed_nvd_missing_url_handling(populated_four_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that NVD CVE items with missing/null URLs render safely as plain text without broken links."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_four_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("NVD CVE").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # CVE-2025-62820 has url=None; verify it renders as plain header
    assert any("#### CVE-2025-62820: SQL injection vulnerability" in t for t in markdown_texts)
    # Ensure no empty or fake link target is rendered for CVE-2025-62820
    assert not any("[CVE-2025-62820" in t and "](None)" in t for t in markdown_texts)
    assert not any("[CVE-2025-62820" in t and "]()" in t for t in markdown_texts)


def test_intelligence_feed_nvd_toggles(populated_four_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies bookmark and read toggles for NVD CVE items update the SQLite database."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_four_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("NVD CVE").run()
    assert len(app_test.exception) == 0

    # Locate NVD CVE Item 7 (id=7, initially unbookmarked and unread)
    item_7 = get_item_by_id(7, db_path=populated_four_source_db)
    assert item_7["is_bookmarked"] == 0
    assert item_7["is_read"] == 0

    # Toggle bookmark for Item 7
    nvd_bm_toggle = [t for t in app_test.toggle if t.key == "nvd_bm_7"][0]
    assert nvd_bm_toggle.value is False
    nvd_bm_toggle.set_value(True).run()
    assert len(app_test.exception) == 0

    updated_7 = get_item_by_id(7, db_path=populated_four_source_db)
    assert updated_7["is_bookmarked"] == 1

    # Toggle read for Item 7
    nvd_read_toggle = [t for t in app_test.toggle if t.key == "nvd_read_7"][0]
    assert nvd_read_toggle.value is False
    nvd_read_toggle.set_value(True).run()
    assert len(app_test.exception) == 0

    updated_7 = get_item_by_id(7, db_path=populated_four_source_db)
    assert updated_7["is_read"] == 1


def test_intelligence_feed_empty_state_nvd_cve(empty_test_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies the empty state notice when NVD CVE filter is selected with no CVE records."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(empty_test_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("NVD CVE").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    assert any("No NVD CVE Advisories Found" in t for t in markdown_texts)


def test_intelligence_feed_retrieves_live_nvd_cve_records():
    """Verifies retrieval and rendering of all live NVD CVE records from data/ai_pulse.db."""
    live_db = Path("data") / "ai_pulse.db"
    assert live_db.exists(), "data/ai_pulse.db must exist with ingested records"

    nvd_feed = fetch_feed_data(selected_source="NVD CVE", db_path=live_db)
    assert nvd_feed["error"] is None
    assert nvd_feed["total_nvd"] >= 5
    assert len(nvd_feed["items"]) == nvd_feed["total_nvd"]

    for it in nvd_feed["items"]:
        assert it["source"] == "NVD CVE"
        assert it["domain"] == "cybersecurity"
        assert it["source_id"].startswith("CVE-")
        assert it["published_at"] is not None
        assert it["url"] is not None and "nvd.nist.gov" in it["url"]

    # Verify rendering via Streamlit AppTest
    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("NVD CVE").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    assert any("NVD CVE" in t for t in markdown_texts)
    assert any("Domain: cybersecurity" in t for t in markdown_texts)
    for it in nvd_feed["items"]:
        assert any(it["source_id"] in t for t in markdown_texts)


@pytest.fixture
def populated_five_source_db(tmp_path: Path) -> Path:
    """Provides an initialized SQLite database with all five supported sources plus an unsupported source."""
    db_file = tmp_path / "five_source_feed_pulse.db"
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
        # Item 3: Hacker News, unread, unbookmarked
        {
            "source": "Hacker News",
            "source_id": "hn_3001",
            "domain": "dev-tools",
            "title": "Show HN: Fast local SQLite vector search in Python",
            "url": "https://github.com/example/fast-sqlite-vector",
            "text": "A minimal, dependency-free vector index built directly on top of SQLite.",
            "published_at": "2026-11-01T12:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 4: Hacker News, read, bookmarked
        {
            "source": "Hacker News",
            "source_id": "hn_3002",
            "domain": "dev-tools",
            "title": "Ask HN: What is your preferred local LLM setup in 2026?",
            "url": None,
            "text": "I am curious what developers are using.<p>Ollama, vLLM, or LM Studio?</p>",
            "published_at": "2026-11-01T16:00:00Z",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 5: GitHub Releases, unread, unbookmarked
        {
            "source": "GitHub Releases",
            "source_id": "gh_5001",
            "domain": "dev-tools",
            "title": "Ollama v0.4.0: Local Tool Calling & Structured Outputs",
            "url": "https://github.com/ollama/ollama/releases/tag/v0.4.0",
            "text": "Added support for Llama 3.2 & tool calling.",
            "published_at": "2026-11-01T08:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 6: GitHub Releases, read, bookmarked
        {
            "source": "GitHub Releases",
            "source_id": "gh_5002",
            "domain": "dev-tools",
            "title": "vLLM v0.6.2 Internal Release",
            "url": None,
            "text": "Performance improvements for chunked prefill.",
            "published_at": "2026-10-31T09:00:00Z",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 7: NVD CVE, unread, unbookmarked, with URL
        {
            "source": "NVD CVE",
            "source_id": "CVE-2025-62819",
            "domain": "cybersecurity",
            "title": "Heap buffer overflow in OpenSSL ASN.1 parser leading to remote denial of service or arbitrary code execution",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2025-62819",
            "text": "A heap-based buffer overflow flaw was found in OpenSSL. A remote attacker could send a specially crafted ASN.1 structure to cause memory corruption and arbitrary code execution.",
            "published_at": "2026-11-02T15:17:11.403",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 8: NVD CVE, read, bookmarked, NO URL
        {
            "source": "NVD CVE",
            "source_id": "CVE-2025-62820",
            "domain": "cybersecurity",
            "title": "SQL injection vulnerability in legacy authentication plugin",
            "url": None,
            "text": "An issue was discovered in legacy authentication plugin allowing SQL injection via username parameter in login forms.",
            "published_at": "2026-11-01T10:00:00Z",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 9: CISA KEV, unread, unbookmarked, with URL, long description (>200 chars)
        {
            "source": "CISA KEV",
            "source_id": "CVE-2026-118527",
            "domain": "cybersecurity",
            "title": "Ivanti Connect Secure Generation of Predictable Numbers or Identifiers Vulnerability",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-118527",
            "text": "Ivanti Connect Secure contains a generation of predictable numbers or identifiers vulnerability that allows remote unauthenticated attackers to bypass authentication and execute arbitrary commands on vulnerable instances when deployed in cluster configurations.",
            "published_at": "2026-10-30",
            "is_read": 0,
            "is_bookmarked": 0,
        },
        # Item 10: CISA KEV, read, bookmarked, NO URL, short description (<=200 chars)
        {
            "source": "CISA KEV",
            "source_id": "CVE-2026-99999",
            "domain": "cybersecurity",
            "title": "Legacy Gateway Command Injection Vulnerability",
            "url": None,
            "text": "Command injection vulnerability in management interface.",
            "published_at": "2026-10-25",
            "is_read": 1,
            "is_bookmarked": 1,
        },
        # Item 11: Unsupported source (cybersecurity Unsupported Source)
        {
            "source": "Unsupported Source",
            "source_id": "EXP-2026-0001",
            "domain": "cybersecurity",
            "title": "Active exploitation prototype advisory",
            "url": "https://example.com/exploit",
            "text": "Unpublished advisory details.",
            "published_at": "2026-05-01T00:00:00Z",
            "is_read": 0,
            "is_bookmarked": 0,
        },
    ]
    insert_items(sample_items, db_path=db_file)
    return db_file


def test_fetch_feed_data_five_sources(populated_five_source_db: Path):
    """Verifies fetch_feed_data filtering and five-source count metrics."""
    # All Sources: returns only supported sources (arXiv=2 + HN=2 + GitHub=2 + NVD=2 + CISA=2 -> 10), excluding Unsupported Source
    all_data = fetch_feed_data(selected_source="All Sources", db_path=populated_five_source_db)
    assert all_data["error"] is None
    assert all_data["total_items"] == 10
    assert all_data["total_arxiv"] == 2
    assert all_data["total_hn"] == 2
    assert all_data["total_gh"] == 2
    assert all_data["total_nvd"] == 2
    assert all_data["total_cisa"] == 2
    assert all_data["total_cisa_kev"] == 2
    assert all_data["unread"] == 5  # Items 1, 3, 5, 7, 9
    assert all_data["bookmarked"] == 5  # Items 2, 4, 6, 8, 10
    assert len(all_data["items"]) == 10
    assert not any(it["source"] == "Unsupported Source" for it in all_data["items"])

    # All five sources are represented in items
    sources_in_feed = {it["source"] for it in all_data["items"]}
    assert sources_in_feed == {"arXiv", "Hacker News", "GitHub Releases", "NVD CVE", "CISA KEV"}

    # Filter to CISA KEV only
    cisa_data = fetch_feed_data(selected_source="CISA KEV", db_path=populated_five_source_db)
    assert len(cisa_data["items"]) == 2
    assert all(it["source"] == "CISA KEV" for it in cisa_data["items"])
    assert all(it["domain"] == "cybersecurity" for it in cisa_data["items"])


def test_intelligence_feed_displays_all_five_sources(populated_five_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that the Intelligence Feed renders arXiv, Hacker News, GitHub Releases, NVD CVE & CISA KEV in All Sources."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_five_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Verify metrics row cards for all sources
    assert any("Total Items" in t for t in markdown_texts)
    assert any("arXiv Papers Stored" in t for t in markdown_texts)
    assert any("Hacker News Stories" in t for t in markdown_texts)
    assert any("GitHub Releases" in t for t in markdown_texts)
    assert any("NVD CVEs" in t for t in markdown_texts)
    assert any("CISA KEV" in t for t in markdown_texts)
    assert any("Unread Items" in t for t in markdown_texts)
    assert any("Bookmarked Items" in t for t in markdown_texts)

    # Verify source radio options includes all 6 options
    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    expected_options = ["All Sources", "arXiv", "Hacker News", "GitHub Releases", "NVD CVE", "CISA KEV"]
    for opt in expected_options:
        assert opt in source_radio.options

    # Verify presence of records from all 5 sources
    assert any("Frontier Model Reasoning with Tree of Thoughts" in t for t in markdown_texts)
    assert any("Show HN: Fast local SQLite vector search in Python" in t for t in markdown_texts)
    assert any("Ollama v0.4.0: Local Tool Calling & Structured Outputs" in t for t in markdown_texts)
    assert any("CVE-2025-62819" in t for t in markdown_texts)
    assert any("CVE-2026-118527" in t for t in markdown_texts)

    # Verify source badges
    assert any("Source: arXiv" in t for t in markdown_texts)
    assert any("Source: Hacker News" in t for t in markdown_texts)
    assert any("Source: GitHub Releases" in t for t in markdown_texts)
    assert any("Source: NVD CVE" in t for t in markdown_texts)
    assert any("Source: CISA KEV" in t for t in markdown_texts)

    # Verify domain badges
    assert any("Domain: AI research" in t for t in markdown_texts)
    assert any("Domain: dev-tools" in t for t in markdown_texts)
    assert any("Domain: cybersecurity" in t for t in markdown_texts)

    # Unsupported source must NOT be displayed
    assert not any("Active exploitation prototype advisory" in t for t in markdown_texts)


def test_intelligence_feed_cisa_kev_source_filtering(populated_five_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that selecting the CISA KEV filter displays only CISA KEV records and hides other sources."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_five_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("CISA KEV").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Displays CISA KEV records prominently
    assert any("CVE-2026-118527" in t for t in markdown_texts)
    assert any("CVE-2026-99999" in t for t in markdown_texts)

    # Hides arXiv, Hacker News, GitHub Releases, and NVD CVE records
    assert not any("Frontier Model Reasoning with Tree of Thoughts" in t for t in markdown_texts)
    assert not any("Scaling Laws for RAG Systems" in t for t in markdown_texts)
    assert not any("Show HN: Fast local SQLite vector search in Python" in t for t in markdown_texts)
    assert not any("Ask HN: What is your preferred local LLM setup in 2026?" in t for t in markdown_texts)
    assert not any("Ollama v0.4.0: Local Tool Calling & Structured Outputs" in t for t in markdown_texts)
    assert not any("vLLM v0.6.2 Internal Release" in t for t in markdown_texts)
    assert not any("CVE-2025-62819" in t for t in markdown_texts)
    assert not any("CVE-2025-62820" in t for t in markdown_texts)


def test_intelligence_feed_cisa_kev_card_content_and_prominent_cve(populated_five_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies CISA KEV card layout: prominent CVE ID, vulnerability name, URL link, badges."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_five_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("CISA KEV").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # CVE ID and vulnerability name displayed prominently in header link
    assert any("CVE-2026-118527: Ivanti Connect Secure Generation of Predictable Numbers or Identifiers Vulnerability" in t for t in markdown_texts)
    assert any("https://nvd.nist.gov/vuln/detail/CVE-2026-118527" in t for t in markdown_texts)

    # Source and domain badges
    assert any("Source: CISA KEV" in t for t in markdown_texts)
    assert any("Domain: cybersecurity" in t for t in markdown_texts)


def test_intelligence_feed_cisa_kev_date_added_label(populated_five_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that CISA KEV cards display 'Date Added' rather than 'Publication Date'."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_five_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("CISA KEV").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # Date Added label must be present
    assert any("Date Added: 2026-10-30" in t for t in markdown_texts)
    assert any("Date Added: 2026-10-25" in t for t in markdown_texts)

    # Publication Date label must NOT be present on CISA KEV cards
    assert not any("Publication Date: 2026-10-30" in t for t in markdown_texts)


def test_intelligence_feed_cisa_kev_description_expansion(populated_five_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that long descriptions show a preview and can be expanded via 'Full Vulnerability Description'."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_five_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("CISA KEV").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # For Item 9 (long description >200 chars), preview is shown with ellipsis
    assert any("..." in t for t in markdown_texts)

    # Expander titled "Full Vulnerability Description" exists
    expander_labels = [exp.label for exp in app_test.expander]
    assert "Full Vulnerability Description" in expander_labels

    # Full description is rendered inside the expander
    full_text = (
        "Ivanti Connect Secure contains a generation of predictable numbers or identifiers vulnerability "
        "that allows remote unauthenticated attackers to bypass authentication and execute arbitrary commands "
        "on vulnerable instances when deployed in cluster configurations."
    )
    assert any(full_text in t for t in markdown_texts)

    # Short description (Item 10 <= 200 chars) is rendered directly
    assert any("Command injection vulnerability in management interface." in t for t in markdown_texts)


def test_intelligence_feed_cisa_kev_missing_url_handling(populated_five_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that CISA KEV items with missing/null URLs render safely as plain text without broken links."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_five_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("CISA KEV").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]

    # CVE-2026-99999 has url=None; verify it renders as plain header
    assert any("#### CVE-2026-99999: Legacy Gateway Command Injection Vulnerability" in t for t in markdown_texts)
    # Ensure no empty or fake link target is rendered
    assert not any("[CVE-2026-99999" in t and "](None)" in t for t in markdown_texts)
    assert not any("[CVE-2026-99999" in t and "]()" in t for t in markdown_texts)


def test_intelligence_feed_cisa_kev_toggles(populated_five_source_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies bookmark and read toggles for CISA KEV items update the SQLite database with unique keys."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(populated_five_source_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("CISA KEV").run()
    assert len(app_test.exception) == 0

    # Locate CISA KEV Item 9 (id=9, initially unbookmarked and unread)
    item_9 = get_item_by_id(9, db_path=populated_five_source_db)
    assert item_9["is_bookmarked"] == 0
    assert item_9["is_read"] == 0

    # Toggle bookmark for Item 9 with unique key cisa_bm_9
    cisa_bm_toggle = [t for t in app_test.toggle if t.key == "cisa_bm_9"][0]
    assert cisa_bm_toggle.value is False
    cisa_bm_toggle.set_value(True).run()
    assert len(app_test.exception) == 0

    updated_9 = get_item_by_id(9, db_path=populated_five_source_db)
    assert updated_9["is_bookmarked"] == 1

    # Toggle read for Item 9 with unique key cisa_read_9
    cisa_read_toggle = [t for t in app_test.toggle if t.key == "cisa_read_9"][0]
    assert cisa_read_toggle.value is False
    cisa_read_toggle.set_value(True).run()
    assert len(app_test.exception) == 0

    updated_9 = get_item_by_id(9, db_path=populated_five_source_db)
    assert updated_9["is_read"] == 1


def test_intelligence_feed_empty_state_cisa_kev(empty_test_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies the empty state notice when CISA KEV filter is selected with no CISA KEV records."""
    monkeypatch.setenv("AI_PULSE_DB_PATH", str(empty_test_db))

    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("CISA KEV").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    assert any("No CISA KEV Records Found" in t for t in markdown_texts)
    assert any("Trigger the <strong>n8n CISA KEV pipeline</strong> to fetch and ingest records." in t for t in markdown_texts)


def test_intelligence_feed_retrieves_live_cisa_kev_records():
    """Verifies retrieval and rendering of live CISA KEV records from data/ai_pulse.db."""
    live_db = Path("data") / "ai_pulse.db"
    assert live_db.exists(), "data/ai_pulse.db must exist with ingested records"

    cisa_feed = fetch_feed_data(selected_source="CISA KEV", db_path=live_db)
    assert cisa_feed["error"] is None
    assert cisa_feed["total_cisa"] >= 1700
    assert len(cisa_feed["items"]) == 100  # paginated at 100

    for it in cisa_feed["items"]:
        assert it["source"] == "CISA KEV"
        assert it["domain"] == "cybersecurity"
        assert it["source_id"].startswith("CVE-")
        assert it["published_at"] is not None

    # Verify rendering via Streamlit AppTest
    app_test = AppTest.from_file(DASHBOARD_FILE).run()
    assert len(app_test.exception) == 0

    app_test.radio[0].set_value("Intelligence Feed").run()
    assert len(app_test.exception) == 0

    source_radio = [r for r in app_test.radio if r.label == "Filter by Source"][0]
    source_radio.set_value("CISA KEV").run()
    assert len(app_test.exception) == 0

    markdown_texts = [m.value for m in app_test.markdown]
    assert any("Source: CISA KEV" in t for t in markdown_texts)
    assert any("Domain: cybersecurity" in t for t in markdown_texts)
    assert any("Date Added:" in t for t in markdown_texts)

    # Check that first few CVE IDs from live query appear in markdown
    for it in cisa_feed["items"][:5]:
        assert any(it["source_id"] in t for t in markdown_texts)
