"""AI Pulse Database Service.

Manages SQLite storage for intelligence items with validation,
transactions, and conflict handling.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Generator

DEFAULT_DB_PATH = Path("data") / "ai_pulse.db"


def resolve_db_path(db_path: Path | str | None = None) -> Path:
    """Resolves and returns the target database Path, ensuring parent directory exists."""
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Creates and returns a configured SQLite connection.
    
    Enforces foreign keys and row_factory for dictionary-like access.
    The caller is responsible for closing the connection, or use get_db_connection.
    """
    path = resolve_db_path(db_path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_db_connection(db_path: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite database connections, ensuring proper cleanup."""
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None) -> None:
    """Initializes the database schema and creates the intelligence_items table."""
    create_table_sql = """
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
    CREATE INDEX IF NOT EXISTS idx_intelligence_domain ON intelligence_items(domain);
    CREATE INDEX IF NOT EXISTS idx_intelligence_published_at ON intelligence_items(published_at);
    CREATE INDEX IF NOT EXISTS idx_intelligence_created_at ON intelligence_items(created_at);
    CREATE INDEX IF NOT EXISTS idx_intelligence_is_read ON intelligence_items(is_read);
    CREATE INDEX IF NOT EXISTS idx_intelligence_is_bookmarked ON intelligence_items(is_bookmarked);
    """
    with get_db_connection(db_path) as conn:
        with conn:
            conn.executescript(create_table_sql)


def validate_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    """Validates required fields, type bounds, and normalizes optional values."""
    if not isinstance(item, dict):
        raise TypeError("Item payload must be a dictionary.")

    # Validate required fields
    source = item.get("source")
    if not source or not str(source).strip():
        raise ValueError("Field 'source' is required and cannot be empty.")

    source_id = item.get("source_id")
    if source_id is None or not str(source_id).strip():
        raise ValueError("Field 'source_id' is required and cannot be empty.")

    title = item.get("title")
    if not title or not str(title).strip():
        raise ValueError("Field 'title' is required and cannot be empty.")

    # Validate relevance_score if provided
    relevance_score = item.get("relevance_score")
    if relevance_score is not None:
        if not isinstance(relevance_score, int) or isinstance(relevance_score, bool):
            raise ValueError("Field 'relevance_score' must be an integer between 1 and 5.")
        if relevance_score < 1 or relevance_score > 5:
            raise ValueError("Field 'relevance_score' must be between 1 and 5.")

    # Normalize boolean-like integer fields
    def _normalize_bool_int(value: Any, field_name: str) -> int:
        if value is None:
            return 0
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, int) and value in (0, 1):
            return value
        raise ValueError(f"Field '{field_name}' must be a boolean or an integer (0 or 1).")

    is_read = _normalize_bool_int(item.get("is_read", 0), "is_read")
    is_bookmarked = _normalize_bool_int(item.get("is_bookmarked", 0), "is_bookmarked")

    # Safe defaults for optional values
    fetched_at = item.get("fetched_at")
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc).isoformat()

    return {
        "source": str(source).strip(),
        "source_id": str(source_id).strip(),
        "domain": str(item["domain"]).strip() if item.get("domain") is not None else None,
        "title": str(title).strip(),
        "url": str(item["url"]).strip() if item.get("url") is not None else None,
        "text": str(item["text"]) if item.get("text") is not None else None,
        "published_at": str(item["published_at"]) if item.get("published_at") is not None else None,
        "fetched_at": str(fetched_at),
        "summary": str(item["summary"]) if item.get("summary") is not None else None,
        "relevance_score": relevance_score,
        "relevance_reason": str(item["relevance_reason"]) if item.get("relevance_reason") is not None else None,
        "is_read": is_read,
        "is_bookmarked": is_bookmarked,
    }


def insert_item(item: dict[str, Any], db_path: Path | str | None = None) -> int | None:
    """Inserts a single intelligence item.
    
    Conflict Strategy:
    Uses `INSERT OR IGNORE` with UNIQUE(source, source_id). If an item with matching
    source and source_id already exists, the insert is ignored and existing data is preserved.
    
    Returns:
        The integer primary key `id` of the newly created item, or `None` if ignored as a duplicate.
    """
    validated = validate_item_payload(item)
    insert_sql = """
    INSERT OR IGNORE INTO intelligence_items (
        source, source_id, domain, title, url, text,
        published_at, fetched_at, summary, relevance_score,
        relevance_reason, is_read, is_bookmarked
    ) VALUES (
        :source, :source_id, :domain, :title, :url, :text,
        :published_at, :fetched_at, :summary, :relevance_score,
        :relevance_reason, :is_read, :is_bookmarked
    );
    """
    with get_db_connection(db_path) as conn:
        with conn:
            cursor = conn.execute(insert_sql, validated)
            if cursor.rowcount > 0:
                return cursor.lastrowid
            return None


def insert_items(items: list[dict[str, Any]], db_path: Path | str | None = None) -> int:
    """Safely inserts multiple items within a single database transaction.
    
    Validates all items before or during insertion. Uses `INSERT OR IGNORE` to safely
    bypass duplicates.
    
    Returns:
        The total count of newly inserted items.
    """
    if not items:
        return 0

    validated_items = [validate_item_payload(it) for it in items]
    insert_sql = """
    INSERT OR IGNORE INTO intelligence_items (
        source, source_id, domain, title, url, text,
        published_at, fetched_at, summary, relevance_score,
        relevance_reason, is_read, is_bookmarked
    ) VALUES (
        :source, :source_id, :domain, :title, :url, :text,
        :published_at, :fetched_at, :summary, :relevance_score,
        :relevance_reason, :is_read, :is_bookmarked
    );
    """
    inserted_count = 0
    with get_db_connection(db_path) as conn:
        with conn:
            for item in validated_items:
                cursor = conn.execute(insert_sql, item)
                if cursor.rowcount > 0:
                    inserted_count += 1
    return inserted_count


def get_items(
    limit: int = 50,
    offset: int = 0,
    domain: str | None = None,
    is_read: int | None = None,
    is_bookmarked: int | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retrieves intelligence items with pagination and optional filtering."""
    if limit < 1:
        raise ValueError("Parameter 'limit' must be greater than or equal to 1.")
    if offset < 0:
        raise ValueError("Parameter 'offset' must be greater than or equal to 0.")

    conditions = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if domain is not None:
        conditions.append("domain = :domain")
        params["domain"] = domain
    if is_read is not None:
        conditions.append("is_read = :is_read")
        params["is_read"] = 1 if is_read else 0
    if is_bookmarked is not None:
        conditions.append("is_bookmarked = :is_bookmarked")
        params["is_bookmarked"] = 1 if is_bookmarked else 0

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
    SELECT * FROM intelligence_items
    {where_clause}
    ORDER BY created_at DESC, id DESC
    LIMIT :limit OFFSET :offset;
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_item_by_id(item_id: int, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Retrieves a single intelligence item by its primary key ID."""
    query = "SELECT * FROM intelligence_items WHERE id = :id;"
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, {"id": item_id})
        row = cursor.fetchone()
        return dict(row) if row is not None else None


def count_items(
    domain: str | None = None,
    is_read: int | None = None,
    is_bookmarked: int | None = None,
    db_path: Path | str | None = None,
) -> int:
    """Returns total count of stored items matching optional filters."""
    conditions = []
    params: dict[str, Any] = {}

    if domain is not None:
        conditions.append("domain = :domain")
        params["domain"] = domain
    if is_read is not None:
        conditions.append("is_read = :is_read")
        params["is_read"] = 1 if is_read else 0
    if is_bookmarked is not None:
        conditions.append("is_bookmarked = :is_bookmarked")
        params["is_bookmarked"] = 1 if is_bookmarked else 0

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT COUNT(*) AS total FROM intelligence_items {where_clause};"

    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        return int(row["total"]) if row else 0


def update_read_status(item_id: int, is_read: bool | int, db_path: Path | str | None = None) -> bool:
    """Updates the read status for a specific intelligence item."""
    status_int = 1 if is_read else 0
    query = "UPDATE intelligence_items SET is_read = :is_read WHERE id = :id;"
    with get_db_connection(db_path) as conn:
        with conn:
            cursor = conn.execute(query, {"is_read": status_int, "id": item_id})
            return cursor.rowcount > 0


def update_bookmark_status(item_id: int, is_bookmarked: bool | int, db_path: Path | str | None = None) -> bool:
    """Updates the bookmark status for a specific intelligence item."""
    status_int = 1 if is_bookmarked else 0
    query = "UPDATE intelligence_items SET is_bookmarked = :is_bookmarked WHERE id = :id;"
    with get_db_connection(db_path) as conn:
        with conn:
            cursor = conn.execute(query, {"is_bookmarked": status_int, "id": item_id})
            return cursor.rowcount > 0
