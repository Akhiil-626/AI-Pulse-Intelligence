"""AI Pulse - Intelligence Dashboard.

Phase 1: Project scaffold, Python environment, and base Streamlit UI.
"""

import streamlit as st

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


def render_sidebar() -> str:
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

        # System and environment indicators
        st.markdown(
            """
            <div class="sidebar-meta">
                <div><strong>Current Phase:</strong> Phase 1 (Scaffold & UI)</div>
                <div style="margin-top: 6px;"><strong>Data Pipeline:</strong> Standby (n8n)</div>
                <div style="margin-top: 6px;"><strong>Database:</strong> SQLite (Pending)</div>
                <div style="margin-top: 6px;"><strong>Processing:</strong> Ollama (Pending)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption("AI Pulse v0.1.0 • Phase 1")

    return selected_page


def render_metrics_row() -> None:
    """Renders status cards clearly indicating data integration is pending."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            """
            <div class="metric-card">
                <div class="metric-label">Feed Sources</div>
                <div class="metric-value">--</div>
                <div class="metric-note">Integration pending (n8n)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div class="metric-card">
                <div class="metric-label">Intelligence Items</div>
                <div class="metric-value">--</div>
                <div class="metric-note">Awaiting pipeline ingestion</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            """
            <div class="metric-card">
                <div class="metric-label">Threat Alerts</div>
                <div class="metric-value">--</div>
                <div class="metric-note">Advisories disconnected</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            """
            <div class="metric-card">
                <div class="metric-label">Automation Pipeline</div>
                <div class="metric-value">Standby</div>
                <div class="metric-note">Self-hosted n8n 2.44.6</div>
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

    # Status indicators row
    render_metrics_row()

    # Empty-state message explaining that intelligence items will appear after n8n integration
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
    selected_page = render_sidebar()

    if selected_page == "Overview":
        render_overview()
    else:
        render_placeholder(selected_page)


if __name__ == "__main__":
    main()
