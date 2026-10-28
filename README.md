# AI Pulse

AI Pulse is an AI research, developer tools, and cybersecurity intelligence dashboard designed to monitor and aggregate high-value technical signals without relying on paid APIs or third-party cloud services.

---

## Technology Stack

- **Python**: 3.12+ (tested and verified on Python 3.13)
- **Dashboard Framework**: [Streamlit](https://streamlit.io/) (v1.40+)
- **Data Manipulation**: [pandas](https://pandas.pydata.org/)
- **Visualizations**: [Plotly](https://plotly.com/)
- **Data Persistence**: SQLite (scheduled for Phase 2)
- **Workflow Automation**: Self-hosted n8n (v2.44.6, scheduled for Phase 2)
- **Local Inference**: Ollama (scheduled for Phase 3)
- **Version Control**: Git

---

## Project Structure

```text
AI-Pulse/
├── .streamlit/
│   └── config.toml           # Streamlit dark theme & server configuration
├── app/
│   ├── __init__.py           # Application package marker
│   └── dashboard.py          # Main Streamlit dashboard application
├── assets/                   # Static media, icons, and diagrams (future)
├── data/
│   ├── processed/            # Normalized and enriched data (git-ignored)
│   └── raw/                  # Ingested feed payloads (git-ignored)
├── services/
│   └── __init__.py           # Future business logic and service modules
├── tests/
│   └── test_phase1.py        # Automated test suite for Phase 1 verification
├── .env.example              # Minimal environment variable template
├── .gitignore                # Comprehensive exclusions (venv, caches, data, sqlite)
├── README.md                 # Project documentation and setup guide
└── requirements.txt          # Python project dependencies
```

---

## Setup & Installation

### 1. Prerequisites
- Python 3.12 or compatible (Python 3.13 supported).
- Git installed on your system.

### 2. Create and Activate Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Dashboard
```bash
streamlit run app/dashboard.py
```
Open your browser at `http://localhost:8501`.

### 5. Run Automated Tests
```bash
python -m unittest discover tests
```

---

## Implementation Status & Limitations (Phase 1)

### Current Status
- **Scaffold**: Full directory hierarchy and package structure initialized.
- **Environment**: Virtual environment configured with verified `streamlit`, `pandas`, and `plotly` dependencies.
- **UI & Layout**: Professional dark-themed dashboard active with sidebar navigation placeholders and overview intelligence pillars.
- **Empty-State Indicators**: Status cards and informational alerts clearly indicating data will appear once the automation pipeline is connected.
- **Verification**: Complete automated test suite (`tests/test_phase1.py`) validating directory structure, dependencies, configuration files, and runtime rendering.

### Limitations in Phase 1
- **No Live Data / Database**: SQLite database schema and database connectors are not implemented yet (scheduled for Phase 2).
- **No n8n Ingestion**: The existing n8n automation workflow (2.44.6) is unmodified and awaiting webhook/database connectivity in Phase 2.
- **Navigation Placeholders**: Secondary tabs (`Intelligence Feed`, `Threat Center`, `Analytics`, `Reading List`) display informative placeholders; functional subpages will arrive in subsequent phases.
- **No LLM Processing**: Ollama local inference and automated summarization will be integrated in later phases.
