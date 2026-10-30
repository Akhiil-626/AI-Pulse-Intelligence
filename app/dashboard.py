"""AI Pulse - Intelligence Dashboard.

Phase 4.1.1: Database Integration and Live Overview Metrics.
"""

import os
from pathlib import Path
from typing import Any

import streamlit as st

from services.database import DEFAULT_DB_PATH, count_items, init_db

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


def render_overview() -> None:
    """Renders the main overview section with introduction and empty-state messaging."""
    st.markdown('<div class="pulse-title">AI Pulse</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pulse-subtitle">AI Research, Developer Tools & Cybersecurity Intelligence</div>',
        unsafe_allow_html=True,
    )

    # Fetch live database metrics
    metrics = fetch_overview_metrics()

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
    metrics = fetch_overview_metrics()
    selected_page = render_sidebar(db_error=metrics.get("error"))

    if selected_page == "Overview":
        render_overview()
    else:
        render_placeholder(selected_page)


if __name__ == "__main__":
    main()
