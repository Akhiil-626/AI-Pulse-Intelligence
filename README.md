# AI Pulse

AI Pulse is an AI research, developer tools, and cybersecurity intelligence dashboard designed to monitor and aggregate high-value technical signals without relying on paid APIs or third-party cloud services.

---

## Technology Stack

- **Python**: 3.12+ (tested and verified on Python 3.13)
- **Dashboard Framework**: [Streamlit](https://streamlit.io/) (v1.40+)
- **Data Manipulation**: [pandas](https://pandas.pydata.org/)
- **Visualizations**: [Plotly](https://plotly.com/)
- **Data Persistence**: [SQLite](https://www.sqlite.org/) via Python's standard library `sqlite3`
- **Testing**: [pytest](https://pytest.org/) (v8.0+) & standard `unittest`
- **Workflow Automation**: Self-hosted n8n (v2.44.6, scheduled for Phase 3)
- **Local Inference**: Ollama (scheduled for a later phase)
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
│   ├── ai_pulse.db           # SQLite database (generated at runtime, git-ignored)
│   ├── processed/            # Normalized and enriched data (git-ignored)
│   └── raw/                  # Ingested feed payloads (git-ignored)
├── services/
│   ├── __init__.py           # Service layer package marker
│   └── database.py           # SQLite database connection, schema, and queries
├── tests/
│   ├── test_phase1.py        # Automated test suite for Phase 1 verification
│   └── test_database.py      # Automated pytest suite for Phase 2 database
├── .env.example              # Minimal environment variable template
├── .gitignore                # Comprehensive exclusions (venv, caches, data, sqlite)
├── README.md                 # Project documentation and setup guide
└── requirements.txt          # Python project dependencies
```

---

## Database Architecture (Phase 2)

### Location & Persistence
- **Default Database Path**: `data/ai_pulse.db` (configurable via `db_path` parameter).
- Parent directories are automatically resolved and created when absent.
- The database is excluded from Git tracking via `.gitignore`.

### Schema: `intelligence_items`
```sql
CREATE TABLE IF NOT EXISTS intelligence_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    domain TEXT,
    title TEXT NOT NULL,
    url TEXT,
    text TEXT,
    published_at TEXT,
    fetched_at TEXT,
    summary TEXT,
    relevance_score INTEGER CHECK (
        relevance_score IS NULL OR (relevance_score >= 1 AND relevance_score <= 5)
    ),
    relevance_reason TEXT,
    is_read INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    is_bookmarked INTEGER NOT NULL DEFAULT 0 CHECK (is_bookmarked IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_source_source_id UNIQUE (source, source_id)
);
```

### Conflict Handling & Deduplication Strategy
Duplicate ingestion is prevented via a `UNIQUE(source, source_id)` constraint paired with `INSERT OR IGNORE`.
When an intelligence item with a previously ingested `(source, source_id)` pair is submitted, SQLite silently bypasses insertion without raising an error or overwriting existing attributes. `insert_item` returns the primary key ID if newly created, or `None` if ignored as a duplicate.

### Database Initialization
The database and tables are initialized programmatically via `services/database.py`:
```python
from services.database import init_db

# Initializes default database at data/ai_pulse.db
init_db()

# Or specify a custom path
init_db("custom/path/ai_pulse.db")
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

Run the full pytest suite (including all database tests):
```bash
pytest -v
```

Run only the database tests:
```bash
pytest tests/test_database.py -v
```

Run Phase 1 scaffold tests:
```bash
python -m unittest discover tests
```

---

## Implementation Status & Roadmap

### Phase 1: Scaffold & Base UI (Complete)
- Project directory hierarchy, `.gitignore`, and virtual environment setup.
- Professional dark-themed Streamlit UI with sidebar navigation and intelligence pillars.
- Empty-state notifications indicating future automated pipeline data.

### Phase 2: SQLite Storage & Data Model (Complete)
- `services/database.py` implemented with parameterized queries, transactions, and foreign-key pragma.
- `intelligence_items` data model with `(source, source_id)` uniqueness and validation.
- Clean CRUD functions: `init_db`, `insert_item`, `insert_items`, `get_items` (pagination), `get_item_by_id`, `count_items`, `update_read_status`, `update_bookmark_status`.
- 10 automated pytest tests using isolated temporary databases (`tmp_path`).

### Upcoming Phases
> [!NOTE]
> - **n8n Integration (v2.44.6)**: Ingestion webhooks and automated collectors are planned for a subsequent phase; the existing n8n workflow was not altered.
> - **AI Processing & Summarization**: Local inference with Ollama and relevance scoring will be integrated after the data collection pipeline is established.
