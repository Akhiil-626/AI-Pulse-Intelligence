# AI Pulse

AI Pulse is an AI research, developer tools, and cybersecurity intelligence dashboard designed to monitor and aggregate high-value technical signals without relying on paid APIs or third-party cloud services.

---

## Technology Stack

- **Python**: 3.12+ (tested and verified on Python 3.13)
- **Ingestion API**: [FastAPI](https://fastapi.tiangolo.com/) with [Pydantic v2](https://docs.pydantic.dev/)
- **API Server**: [Uvicorn](https://www.uvicorn.org/)
- **Dashboard Framework**: [Streamlit](https://streamlit.io/) (v1.40+)
- **Data Manipulation**: [pandas](https://pandas.pydata.org/)
- **Visualizations**: [Plotly](https://plotly.com/)
- **Data Persistence**: [SQLite](https://www.sqlite.org/) via standard library `sqlite3`
- **Testing**: [pytest](https://pytest.org/) & [HTTPX](https://www.python-httpx.org/)
- **Workflow Automation**: Self-hosted n8n (v2.44.6, scheduled for Phase 3.2)
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
│   ├── database.py           # SQLite database connection, schema, and queries
│   └── ingestion_api.py      # Authenticated FastAPI data ingestion service
├── tests/
│   ├── test_phase1.py        # Automated test suite for Phase 1 verification
│   ├── test_database.py      # Automated pytest suite for Phase 2 database
│   └── test_ingestion_api.py # Automated pytest suite for Phase 3.1 ingestion API
├── .env.example              # Environment variable template with INGEST_API_TOKEN
├── .gitignore                # Comprehensive exclusions (venv, caches, data, sqlite)
├── README.md                 # Project documentation and setup guide
└── requirements.txt          # Python project dependencies
```

---

## Ingestion API (Phase 3.1)

### Security Notice
> [!WARNING]
> The Ingestion API is designed for **local development and private pipeline ingestion only**. It binds to `127.0.0.1` by default and must **never** be exposed directly to the public internet without an upstream reverse proxy (e.g., Caddy, Nginx), TLS termination, and rate limiting.

### 1. Configuration
Set the ingestion authentication token in your local `.env` file (copied from `.env.example`):

```bash
# Generate a secure token, e.g. using openssl rand -hex 32
INGEST_API_TOKEN=your_secure_random_token_here
```

### 2. Launch the Ingestion API
Run Uvicorn bound to localhost:

```bash
uvicorn services.ingestion_api:app --host 127.0.0.1 --port 8000 --reload
```
Interactive API documentation will be available at `http://127.0.0.1:8000/docs`.

### 3. Ingestion Endpoint: `POST /api/v1/ingest`
- **Authentication**: `Authorization: Bearer <INGEST_API_TOKEN>`
- **Content-Type**: `application/json`
- **Accepted Sources**: `arXiv`, `Hacker News`, `GitHub Releases`, `NVD CVE`, `CISA KEV`
- **Accepted Domains**: `AI research`, `dev-tools`, `cybersecurity`

#### Example JSON Payload
```json
[
  {
    "id": "2401.12345",
    "source": "arXiv",
    "domain": "AI research",
    "title": "Reasoning Breakthroughs in Frontier Models",
    "url": "https://arxiv.org/abs/2401.12345",
    "text": "Abstract exploring chain-of-thought and verification loops.",
    "published_at": "2026-02-01T10:00:00Z",
    "fetched_at": "2026-02-01T10:15:00Z"
  },
  {
    "id": "CVE-2026-1029",
    "source": "NVD CVE",
    "domain": "cybersecurity",
    "title": "Critical RCE Advisory in Network Parser",
    "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-1029",
    "text": "Buffer overflow disclosed in packet parsing library."
  }
]
```
*(Alternatively, an object with an `"items"` list container `{"items": [...]}` is also accepted.)*

#### Example curl Request
```bash
curl -X POST http://127.0.0.1:8000/api/v1/ingest \
  -H "Authorization: Bearer your_secure_random_token_here" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "id": "2401.12345",
      "source": "arXiv",
      "domain": "AI research",
      "title": "Reasoning Breakthroughs in Frontier Models",
      "url": "https://arxiv.org/abs/2401.12345"
    }
  ]'
```

#### Example Response
```json
{
  "received": 1,
  "inserted": 1,
  "skipped": 0,
  "message": null
}
```

---

## Database Architecture (Phase 2)

### Location & Persistence
- **Default Database Path**: `data/ai_pulse.db` (configurable via `AI_PULSE_DB_PATH` or function parameter).
- Parent directories are automatically created when absent.
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

### Deduplication Strategy
Duplicate ingestion is prevented via `UNIQUE(source, source_id)` paired with `INSERT OR IGNORE`. Existing records are never overwritten, and repeated items are reported as `skipped`.

---

## Setup & Testing

### 1. Create and Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Automated Tests

Run the full pytest suite (Scaffold, Database, and API tests):
```bash
pytest -v
```

Run only the Ingestion API tests:
```bash
pytest tests/test_ingestion_api.py -v
```

Run only the database tests:
```bash
pytest tests/test_database.py -v
```

### 4. Run the Dashboard
```bash
streamlit run app/dashboard.py
```
Open `http://localhost:8501` in your browser.

---

## Implementation Roadmap

- **Phase 1 (Complete)**: UI scaffold, virtual environment, and dark-themed Streamlit dashboard.
- **Phase 2 (Complete)**: SQLite storage, schema, and database functions.
- **Phase 3.1 (Complete)**: Authenticated local Ingestion API (`POST /api/v1/ingest`).
- **Phase 3.2 (Upcoming)**: n8n workflow integration (webhook forwarding to API).
- **Phase 4 (Upcoming)**: Ollama local processing, AI summarization, and relevance scoring.
