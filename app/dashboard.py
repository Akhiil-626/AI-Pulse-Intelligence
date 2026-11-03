"""AI Pulse - Intelligence Dashboard.

Phase 4.1.1: Database Integration and Live Overview Metrics.
"""

import html
import importlib
import os
from pathlib import Path
import re
import sys
from typing import Any

# Ensure project root is on sys.path so services can be imported regardless of execution context
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

import services.database
importlib.reload(services.database)

from services.database import (
    DEFAULT_DB_PATH,
    count_items,
    get_items,
    init_db,
    update_bookmark_status,
    update_read_status,
)

# Configure page settings
st.set_page_config(
    page_title="AI Pulse | Intelligence Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom styling for high-contrast dark intelligence UI
st.markdown(
    """
    <style>
    /* Global style tweaks */
    .block-container {
        padding-top: 1.8rem;
        padding-bottom: 2.5rem;
    }
    
    /* Header typography */
    .pulse-title {
        font-size: 2.3rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin-bottom: 0.1rem;
        color: #F8FAFC;
    }
    .pulse-subtitle {
        font-size: 1.05rem;
        font-weight: 400;
        color: #94A3B8;
        margin-bottom: 1.5rem;
    }

    /* Metric and card styling */
    .metric-card {
        background: #131823;
        border: 1px solid #1E293B;
        border-radius: 8px;
        padding: 1.1rem 1.25rem;
        margin-bottom: 1rem;
    }
    .metric-label {
        font-size: 0.82rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #64748B;
        margin-bottom: 0.4rem;
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #38BDF8;
        font-feature-settings: "tnum";
    }
    .metric-note {
        font-size: 0.78rem;
        color: #64748B;
        margin-top: 0.3rem;
    }

    /* Empty state notice */
    .empty-state-box {
        background: #0B132B;
        border: 1px dashed #1D4ED8;
        border-radius: 10px;
        padding: 2.2rem 1.5rem;
        text-align: center;
        margin: 1.5rem 0;
    }
    .empty-state-title {
        font-size: 1.15rem;
        font-weight: 600;
        color: #E2E8F0;
        margin-bottom: 0.5rem;
    }
    .empty-state-text {
        font-size: 0.92rem;
        color: #94A3B8;
        max-width: 620px;
        margin: 0 auto;
        line-height: 1.55;
    }

    /* Pillar cards */
    .pillar-card {
        background: #111827;
        border: 1px solid #1F2937;
        border-radius: 8px;
        padding: 1.25rem;
        height: 100%;
    }
    .pillar-title {
        font-size: 1.0rem;
        font-weight: 600;
        color: #F3F4F6;
        margin-bottom: 0.45rem;
    }
    .pillar-desc {
        font-size: 0.85rem;
        color: #9CA3AF;
        line-height: 1.5;
    }

    /* Sidebar metadata badges */
    .sidebar-meta {
        background: #111827;
        border: 1px solid #1F2937;
        border-radius: 6px;
        padding: 0.75rem 0.9rem;
        font-size: 0.8rem;
        color: #9CA3AF;
        margin-top: 1.5rem;
    }
    .sidebar-meta strong {
        color: #E5E7EB;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_dashboard_db_path() -> Path:
    """Resolves the database path for the dashboard, respecting environment overrides."""
    env_path = os.environ.get("AI_PULSE_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def fetch_overview_metrics(db_path: Path | str | None = None) -> dict[str, Any]:
    """Fetches real-time counts from the SQLite database using services.database.
    
    Returns total items, unread items, bookmarked items, and cybersecurity threats.
    Catches database exceptions gracefully to prevent dashboard crashes.
    """
    target_path = db_path if db_path is not None else get_dashboard_db_path()
    try:
        init_db(target_path)
        total_items = count_items(db_path=target_path)
        unread_items = count_items(is_read=0, db_path=target_path)
        bookmarked_items = count_items(is_bookmarked=1, db_path=target_path)
        threat_alerts = count_items(domain="cybersecurity", db_path=target_path)
        return {
            "total": total_items,
            "unread": unread_items,
            "bookmarked": bookmarked_items,
            "threats": threat_alerts,
            "error": None,
        }
    except Exception as exc:
        return {
            "total": 0,
            "unread": 0,
            "bookmarked": 0,
            "threats": 0,
            "error": str(exc),
        }


def render_sidebar(db_error: str | None = None) -> str:
    """Renders the dashboard sidebar navigation and system information."""
    with st.sidebar:
        st.markdown("## ⚡ AI Pulse")
        st.caption("Intelligence & Research Monitoring")

        st.markdown("---")

        # Visual placeholder navigation options
        nav_options = [
            "Overview",
            "Intelligence Feed",
            "Threat Center",
            "Analytics",
            "Reading List",
        ]

        selected_page = st.radio(
            "Navigation",
            options=nav_options,
            index=0,
            label_visibility="collapsed",
        )

        st.markdown("---")

        db_status = "SQLite (Connected)" if db_error is None else "SQLite (Unavailable)"

        # System and environment indicators
        st.markdown(
            f"""
            <div class="sidebar-meta">
                <div><strong>Current Phase:</strong> Phase 4.1.1 (Live Overview)</div>
                <div style="margin-top: 6px;"><strong>Data Pipeline:</strong> Standby (n8n)</div>
                <div style="margin-top: 6px;"><strong>Database:</strong> {db_status}</div>
                <div style="margin-top: 6px;"><strong>Processing:</strong> Ollama (Pending)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption("AI Pulse v0.1.0 • Phase 4.1.1")

    return selected_page


def render_metrics_row(metrics: dict[str, Any] | None = None) -> None:
    """Renders status cards displaying live metrics from the SQLite database."""
    if metrics is None:
        metrics = fetch_overview_metrics()

    if metrics.get("error"):
        st.error(
            f"⚠️ Database connection unavailable: {metrics['error']}. Displaying fallback metrics.",
            icon="🚨",
        )

    col1, col2, col3, col4 = st.columns(4)

    total_val = metrics.get("total", 0)
    unread_val = metrics.get("unread", 0)
    bookmarked_val = metrics.get("bookmarked", 0)
    threats_val = metrics.get("threats", 0)

    with col1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Total Intelligence Items</div>
                <div class="metric-value">{total_val}</div>
                <div class="metric-note">{"Awaiting ingestion" if total_val == 0 else "All stored records"}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Unread Items</div>
                <div class="metric-value">{unread_val}</div>
                <div class="metric-note">is_read = 0 (Awaiting review)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Bookmarked Items</div>
                <div class="metric-value">{bookmarked_val}</div>
                <div class="metric-note">is_bookmarked = 1 (Saved items)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Threat Alerts</div>
                <div class="metric-value">{threats_val}</div>
                <div class="metric-note">domain = 'cybersecurity'</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_overview(db_path: Path | str | None = None) -> None:
    """Renders the main overview section with introduction and empty-state messaging."""
    target_path = db_path if db_path is not None else get_dashboard_db_path()
    st.markdown('<div class="pulse-title">AI Pulse</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pulse-subtitle">AI Research, Developer Tools & Cybersecurity Intelligence</div>',
        unsafe_allow_html=True,
    )

    # Fetch live database metrics
    metrics = fetch_overview_metrics(db_path=target_path)

    # Status indicators row with live metrics
    render_metrics_row(metrics)

    # Empty-state message explaining that intelligence items will appear after n8n integration
    if metrics.get("total", 0) == 0:
        st.markdown(
            """
            <div class="empty-state-box">
                <div style="font-size: 2.2rem; margin-bottom: 0.5rem;">📡</div>
                <div class="empty-state-title">Intelligence Feeds Awaiting Data Ingestion</div>
                <div class="empty-state-text">
                    No intelligence items are loaded yet. Ingested feeds, research papers, tool release logs, 
                    and threat advisories will populate automatically once the <strong>n8n automation pipeline</strong> 
                    and database persistence are integrated in the upcoming phases.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.success(
            f"⚡ **{metrics['total']} intelligence records loaded in SQLite database.** "
            f"({metrics['unread']} unread, {metrics['bookmarked']} bookmarked, {metrics['threats']} threat alerts)",
            icon="✅",
        )

    # Core pillars / intelligence focus areas
    st.markdown("### Intelligence Pillars")
    p1, p2, p3 = st.columns(3)

    with p1:
        st.markdown(
            """
            <div class="pillar-card">
                <div class="pillar-title">🔬 AI Research & Models</div>
                <div class="pillar-desc">
                    Tracking breakthroughs in foundational models, arXiv preprints, reasoning benchmarks, 
                    and multimodal research across leading AI labs.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with p2:
        st.markdown(
            """
            <div class="pillar-card">
                <div class="pillar-title">🛠️ Developer Tools & Frameworks</div>
                <div class="pillar-desc">
                    Monitoring rapid evolutions in agentic frameworks, software engineering tooling, 
                    SDKs, inference engines, and developer infrastructure.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with p3:
        st.markdown(
            """
            <div class="pillar-card">
                <div class="pillar-title">🛡️ Cybersecurity Intelligence</div>
                <div class="pillar-desc">
                    Aggregating actionable threat intelligence, vulnerability advisories (CVEs), 
                    model security risks, prompt injection vectors, and exploit analyses.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


SUPPORTED_SOURCES = ("arXiv", "Hacker News", "GitHub Releases", "NVD CVE", "CISA KEV")


def format_item_text(raw_text: str | None) -> str:
    """Decodes HTML entities and strips or converts HTML markup into clean readable text.

    Does not modify database records.
    """
    if not raw_text:
        return "No content available."
    # Decode HTML entities (e.g. &#x2F;, &amp;, &lt;, &gt;, &quot;, &#39;)
    text = html.unescape(raw_text)
    # Convert paragraph tags and line break tags into newlines
    text = re.sub(r"(?i)<\s*p\s*/?>", "\n\n", text)
    text = re.sub(r"(?i)<\s*br\s*/?>", "\n", text)
    # Strip any remaining HTML tags (like <a href="...">, </a>, <span>, etc.)
    text = re.sub(r"<[^>]+>", "", text)
    # Normalize excess whitespace/newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or "No content available."


def fetch_feed_data(
    selected_source: str = "All Sources",
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Fetches intelligence items and summary counts directly from the SQLite database.

    Supports filtering by 'All Sources', 'arXiv', 'Hacker News', 'GitHub Releases', 'NVD CVE', or 'CISA KEV'.
    """
    target_path = db_path if db_path is not None else get_dashboard_db_path()
    try:
        init_db(target_path)
        total_arxiv = count_items(source="arXiv", db_path=target_path)
        total_hn = count_items(source="Hacker News", db_path=target_path)
        total_gh = count_items(source="GitHub Releases", db_path=target_path)
        total_nvd = count_items(source="NVD CVE", db_path=target_path)
        total_cisa = count_items(source="CISA KEV", db_path=target_path)
        total_items = total_arxiv + total_hn + total_gh + total_nvd + total_cisa

        unread_arxiv = count_items(source="arXiv", is_read=0, db_path=target_path)
        unread_hn = count_items(source="Hacker News", is_read=0, db_path=target_path)
        unread_gh = count_items(source="GitHub Releases", is_read=0, db_path=target_path)
        unread_nvd = count_items(source="NVD CVE", is_read=0, db_path=target_path)
        unread_cisa = count_items(source="CISA KEV", is_read=0, db_path=target_path)
        unread_items = unread_arxiv + unread_hn + unread_gh + unread_nvd + unread_cisa

        bookmarked_arxiv = count_items(source="arXiv", is_bookmarked=1, db_path=target_path)
        bookmarked_hn = count_items(source="Hacker News", is_bookmarked=1, db_path=target_path)
        bookmarked_gh = count_items(source="GitHub Releases", is_bookmarked=1, db_path=target_path)
        bookmarked_nvd = count_items(source="NVD CVE", is_bookmarked=1, db_path=target_path)
        bookmarked_cisa = count_items(source="CISA KEV", is_bookmarked=1, db_path=target_path)
        bookmarked_items = bookmarked_arxiv + bookmarked_hn + bookmarked_gh + bookmarked_nvd + bookmarked_cisa

        if selected_source == "arXiv":
            items = get_items(source="arXiv", limit=100, db_path=target_path)
        elif selected_source == "Hacker News":
            items = get_items(source="Hacker News", limit=100, db_path=target_path)
        elif selected_source == "GitHub Releases":
            items = get_items(source="GitHub Releases", limit=100, db_path=target_path)
        elif selected_source == "NVD CVE":
            items = get_items(source="NVD CVE", limit=100, db_path=target_path)
        elif selected_source == "CISA KEV":
            items = get_items(source="CISA KEV", limit=100, db_path=target_path)
        else:
            raw_items = get_items(source=list(SUPPORTED_SOURCES), limit=100, db_path=target_path)
            items = [it for it in raw_items if it.get("source") in SUPPORTED_SOURCES]

        return {
            "items": items,
            "total_items": total_items,
            "total_arxiv": total_arxiv,
            "total_hn": total_hn,
            "total_gh": total_gh,
            "total_github": total_gh,
            "total_nvd": total_nvd,
            "total_cve": total_nvd,
            "total_cisa": total_cisa,
            "total_cisa_kev": total_cisa,
            "unread": unread_items,
            "bookmarked": bookmarked_items,
            # Backward compatibility fields
            "total": total_arxiv,
            "error": None,
        }
    except Exception as exc:
        return {
            "items": [],
            "total_items": 0,
            "total_arxiv": 0,
            "total_hn": 0,
            "total_gh": 0,
            "total_github": 0,
            "total_nvd": 0,
            "total_cve": 0,
            "total_cisa": 0,
            "total_cisa_kev": 0,
            "unread": 0,
            "bookmarked": 0,
            "total": 0,
            "error": str(exc),
        }


def fetch_arxiv_feed_data(db_path: Path | str | None = None) -> dict[str, Any]:
    """Fetches arXiv items and summary counts directly from the SQLite database.

    Maintained for backward compatibility.
    """
    target_path = db_path if db_path is not None else get_dashboard_db_path()
    try:
        init_db(target_path)
        items = get_items(source="arXiv", limit=100, db_path=target_path)
        total_arxiv = count_items(source="arXiv", db_path=target_path)
        unread_arxiv = count_items(source="arXiv", is_read=0, db_path=target_path)
        bookmarked_arxiv = count_items(source="arXiv", is_bookmarked=1, db_path=target_path)
        return {
            "items": items,
            "total": total_arxiv,
            "unread": unread_arxiv,
            "bookmarked": bookmarked_arxiv,
            "error": None,
        }
    except Exception as exc:
        return {
            "items": [],
            "total": 0,
            "unread": 0,
            "bookmarked": 0,
            "error": str(exc),
        }


def handle_bookmark_toggle(item_id: int, key: str, db_path: Path | str | None = None) -> None:
    """Updates bookmark status in the SQLite database when toggle is changed."""
    new_status = st.session_state.get(key, False)
    update_bookmark_status(item_id, 1 if new_status else 0, db_path=db_path)


def handle_read_toggle(item_id: int, key: str, db_path: Path | str | None = None) -> None:
    """Updates read status in the SQLite database when toggle is changed."""
    new_status = st.session_state.get(key, False)
    update_read_status(item_id, 1 if new_status else 0, db_path=db_path)


def render_feed_metrics_row(feed_data: dict[str, Any]) -> None:
    """Renders status cards displaying live multi-source intelligence feed metrics."""
    total_val = feed_data.get("total_items", 0)
    arxiv_val = feed_data.get("total_arxiv", 0)
    hn_val = feed_data.get("total_hn", 0)
    gh_val = feed_data.get("total_gh", feed_data.get("total_github", 0))
    nvd_val = feed_data.get("total_nvd", feed_data.get("total_cve", 0))
    cisa_val = feed_data.get("total_cisa", feed_data.get("total_cisa_kev", 0))
    unread_val = feed_data.get("unread", 0)
    bookmarked_val = feed_data.get("bookmarked", 0)

    col1, col2, col3, col4, col5, col6, col7, col8 = st.columns(8)

    with col1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Total Items</div>
                <div class="metric-value">{total_val}</div>
                <div class="metric-note">Total intelligence items</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">arXiv Papers Stored</div>
                <div class="metric-value">{arxiv_val}</div>
                <div class="metric-note">Total arXiv papers</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Hacker News Stories</div>
                <div class="metric-value">{hn_val}</div>
                <div class="metric-note">Total Hacker News stories</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">GitHub Releases</div>
                <div class="metric-value">{gh_val}</div>
                <div class="metric-note">Total GitHub releases</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col5:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">NVD CVEs</div>
                <div class="metric-value">{nvd_val}</div>
                <div class="metric-note">Total CVE advisories</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col6:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">CISA KEV</div>
                <div class="metric-value">{cisa_val}</div>
                <div class="metric-note">Total CISA KEV records</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col7:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Unread Items</div>
                <div class="metric-value">{unread_val}</div>
                <div class="metric-note">is_read = 0 (Awaiting review)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col8:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Bookmarked Items</div>
                <div class="metric-value">{bookmarked_val}</div>
                <div class="metric-note">is_bookmarked = 1 (Saved items)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_arxiv_metrics_row(feed_data: dict[str, Any]) -> None:
    """Backward compatible alias for render_feed_metrics_row."""
    render_feed_metrics_row(feed_data)


def render_intelligence_feed(db_path: Path | str | None = None) -> None:
    """Renders the functional multi-source Intelligence Feed (arXiv, Hacker News, GitHub Releases, NVD CVE & CISA KEV)."""
    target_path = db_path if db_path is not None else get_dashboard_db_path()

    st.markdown('<div class="pulse-title">Intelligence Feed</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pulse-subtitle">Curated AI Research (arXiv), Developer Discussions (Hacker News), Releases (GitHub Releases), Vulnerabilities (NVD CVE) & Exploited Vulnerabilities (CISA KEV)</div>',
        unsafe_allow_html=True,
    )

    # 1. Source filter control (All Sources, arXiv, Hacker News, GitHub Releases, NVD CVE, CISA KEV)
    # Default is "All Sources"
    filter_col1, _ = st.columns([3, 2])
    with filter_col1:
        selected_source = st.radio(
            "Filter by Source",
            options=["All Sources", "arXiv", "Hacker News", "GitHub Releases", "NVD CVE", "CISA KEV"],
            index=0,
            horizontal=True,
            key="intelligence_feed_source_filter",
        )

    feed_data = fetch_feed_data(selected_source=selected_source, db_path=target_path)

    if feed_data.get("error"):
        st.error(
            f"⚠️ Database connection unavailable: {feed_data['error']}. Unable to load intelligence feed.",
            icon="🚨",
        )
        return

    # 2. Metrics row showing total, arXiv, Hacker News, GitHub Releases, NVD CVEs, CISA KEV, unread, and bookmarked
    render_feed_metrics_row(feed_data)

    items = feed_data.get("items", [])

    if not items:
        # Useful empty state if no records exist for the selected filter
        if selected_source == "arXiv":
            empty_title = "No arXiv Research Papers Found"
            empty_desc = (
                "No research papers from arXiv are currently stored in the database. "
                "Trigger the <strong>n8n arXiv pipeline</strong> to fetch and ingest papers."
            )
        elif selected_source == "Hacker News":
            empty_title = "No Hacker News Stories Found"
            empty_desc = (
                "No stories from Hacker News are currently stored in the database. "
                "Trigger the <strong>n8n Hacker News pipeline</strong> to fetch and ingest stories."
            )
        elif selected_source == "GitHub Releases":
            empty_title = "No GitHub Releases Found"
            empty_desc = (
                "No releases from GitHub are currently stored in the database. "
                "Trigger the <strong>n8n GitHub Releases pipeline</strong> to fetch and ingest releases."
            )
        elif selected_source == "NVD CVE":
            empty_title = "No NVD CVE Advisories Found"
            empty_desc = (
                "No CVE advisories from NVD are currently stored in the database. "
                "Trigger the <strong>n8n NVD CVE pipeline</strong> to fetch and ingest vulnerabilities."
            )
        elif selected_source == "CISA KEV":
            empty_title = "No CISA KEV Records Found"
            empty_desc = (
                "No known exploited vulnerabilities from CISA KEV are currently stored in the database. "
                "Trigger the <strong>n8n CISA KEV pipeline</strong> to fetch and ingest records."
            )
        else:
            empty_title = "No Intelligence Items Found"
            empty_desc = (
                "No intelligence items are currently stored in the database "
                "(No arXiv Research Papers Found, Hacker News stories, GitHub releases, NVD CVEs, or CISA KEV records). "
                "Trigger the <strong>n8n automation pipeline</strong> to fetch and ingest records."
            )

        st.markdown(
            f"""
            <div class="empty-state-box">
                <div style="font-size: 2.2rem; margin-bottom: 0.5rem;">📄</div>
                <div class="empty-state-title">{empty_title}</div>
                <div class="empty-state-text">{empty_desc}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # 3. Render feed cards (arXiv papers, Hacker News stories, GitHub releases, NVD CVEs & CISA KEV)
    for item in items:
        with st.container(border=True):
            item_id = item["id"]
            source_label = item.get("source") or "Unknown"
            domain_label = item.get("domain") or "General"
            pub_date = item.get("published_at") or "Unknown"
            title = item.get("title", "Untitled")
            source_id = item.get("source_id", "")
            url = item.get("url")

            # Title handling: For NVD CVE and CISA KEV, display CVE ID prominently
            if source_label == "NVD CVE":
                cve_id = source_id if source_id else "CVE"
                raw_desc = title if title and title != "Untitled" else (item.get("text") or "Vulnerability advisory")
                clean_raw = raw_desc.replace("[", "\\[").replace("]", "\\]")
                truncated = clean_raw if len(clean_raw) <= 140 else clean_raw[:137].rstrip() + "..."
                if clean_raw.startswith(cve_id):
                    clean_title = truncated
                else:
                    clean_title = f"{cve_id}: {truncated}"
            elif source_label == "CISA KEV":
                cve_id = source_id if source_id else "CVE"
                vuln_name = title if title and title != "Untitled" else "Known Exploited Vulnerability"
                clean_vuln = vuln_name.replace("[", "\\[").replace("]", "\\]")
                if clean_vuln.startswith(cve_id):
                    clean_title = clean_vuln
                else:
                    clean_title = f"{cve_id}: {clean_vuln}"
            else:
                clean_title = title.replace("[", "\\[").replace("]", "\\]")

            # Title: clickable link if URL exists and is non-empty; ordinary text if null or empty
            if url and str(url).strip():
                st.markdown(f"#### [{clean_title}]({str(url).strip()})")
            else:
                st.markdown(f"#### {clean_title}")

            # Badges: Source label, Domain label, Publication date / Date Added
            if source_label == "CISA KEV":
                source_bg = "#991B1B"
                source_fg = "#FEE2E2"
            elif source_label == "NVD CVE":
                source_bg = "#831843"
                source_fg = "#FBCFE8"
            elif source_label == "GitHub Releases":
                source_bg = "#581C87"
                source_fg = "#E9D5FF"
            elif source_label == "Hacker News":
                source_bg = "#9A3412"
                source_fg = "#FDBA74"
            else:
                source_bg = "#1E3A8A"
                source_fg = "#93C5FD"

            if domain_label == "cybersecurity":
                domain_bg = "#7F1D1D"
                domain_fg = "#FCA5A5"
            elif domain_label == "dev-tools":
                domain_bg = "#4338CA"
                domain_fg = "#C7D2FE"
            else:
                domain_bg = "#064E3B"
                domain_fg = "#6EE7B7"

            if source_label == "CISA KEV":
                date_display = f"📅 Date Added: {pub_date}"
            else:
                date_display = f"📅 Publication Date: {pub_date}"

            st.markdown(
                f"""
                <div style="display: flex; gap: 0.5rem; align-items: center; margin-top: 0.15rem; margin-bottom: 0.65rem; flex-wrap: wrap;">
                    <span style="background: {source_bg}; color: {source_fg}; font-size: 0.78rem; font-weight: 600; padding: 0.2rem 0.55rem; border-radius: 4px;">
                        Source: {source_label}
                    </span>
                    <span style="background: {domain_bg}; color: {domain_fg}; font-size: 0.78rem; font-weight: 600; padding: 0.2rem 0.55rem; border-radius: 4px;">
                        Domain: {domain_label}
                    </span>
                    <span style="color: #94A3B8; font-size: 0.82rem;">
                        {date_display}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Description and Expandable section
            if source_label == "CISA KEV":
                cleaned_text = format_item_text(item.get("text") or item.get("summary") or item.get("title"))
                if len(cleaned_text) > 200:
                    preview_text = cleaned_text[:200].rstrip() + "..."
                    st.markdown(preview_text)
                    with st.expander("Full Vulnerability Description", expanded=False):
                        st.markdown(cleaned_text)
                else:
                    st.markdown(cleaned_text)
            else:
                # Expandable section: Abstract (for arXiv), Story Text (for HN), Release Notes (for GitHub Releases), or Full Vulnerability Description (for NVD CVE)
                if source_label == "arXiv":
                    expander_title = "Abstract"
                elif source_label == "GitHub Releases":
                    expander_title = "Release Notes"
                elif source_label == "NVD CVE":
                    expander_title = "Full Vulnerability Description"
                else:
                    expander_title = "Story Text"
                cleaned_text = format_item_text(item.get("text") or item.get("summary") or item.get("title"))
                with st.expander(expander_title, expanded=False):
                    st.markdown(cleaned_text)

            # Action toggles: Bookmark and Read/Unread
            if source_label == "arXiv":
                source_slug = "arxiv"
            elif source_label == "GitHub Releases":
                source_slug = "gh"
            elif source_label == "NVD CVE":
                source_slug = "nvd"
            elif source_label == "CISA KEV":
                source_slug = "cisa"
            else:
                source_slug = "hn"
            bm_key = f"{source_slug}_bm_{item_id}"
            read_key = f"{source_slug}_read_{item_id}"

            is_bm = bool(item.get("is_bookmarked", 0))
            is_rd = bool(item.get("is_read", 0))

            tcol1, tcol2, tcol3 = st.columns([1, 1, 2])
            with tcol1:
                st.toggle(
                    "Bookmark",
                    value=is_bm,
                    key=bm_key,
                    on_change=handle_bookmark_toggle,
                    args=(item_id, bm_key, target_path),
                )
            with tcol2:
                st.toggle(
                    "Read",
                    value=is_rd,
                    key=read_key,
                    on_change=handle_read_toggle,
                    args=(item_id, read_key, target_path),
                )
            with tcol3:
                status_parts = []
                if is_bm:
                    status_parts.append("⭐ Bookmarked")
                if is_rd:
                    status_parts.append("✓ Read")
                else:
                    status_parts.append("○ Unread")
                st.markdown(
                    f'<div style="color: #94A3B8; font-size: 0.82rem; margin-top: 0.35rem;">{" • ".join(status_parts)}</div>',
                    unsafe_allow_html=True,
                )


def render_placeholder(page_name: str) -> None:
    """Renders clean visual placeholder view for secondary navigation options."""
    st.markdown(f'<div class="pulse-title">{page_name}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pulse-subtitle">AI Pulse Intelligence Section</div>',
        unsafe_allow_html=True,
    )

    st.info(
        f"**{page_name}** is currently a visual placeholder for Phase 1. "
        "Real-time feeds, filtering, and analysis will be connected following database "
        "and n8n automation integration in subsequent phases.",
        icon="ℹ️",
    )


def main() -> None:
    """Application entry point."""
    target_path = get_dashboard_db_path()
    metrics = fetch_overview_metrics(db_path=target_path)
    selected_page = render_sidebar(db_error=metrics.get("error"))

    if selected_page == "Overview":
        render_overview(db_path=target_path)
    elif selected_page == "Intelligence Feed":
        render_intelligence_feed(db_path=target_path)
    else:
        render_placeholder(selected_page)


if __name__ == "__main__":
    main()
