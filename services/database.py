"""AI Pulse Database Service.

Manages SQLite storage for intelligence items with validation,
transactions, and conflict handling.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import sys
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
    """Initializes the database schema and creates the intelligence_items and pipeline_checkpoints tables."""
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

    CREATE TABLE IF NOT EXISTS pipeline_checkpoints (
        pipeline_id TEXT PRIMARY KEY,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        current_offset INTEGER NOT NULL DEFAULT 0 CHECK (current_offset >= 0),
        last_page INTEGER NOT NULL DEFAULT 0 CHECK (last_page >= 0),
        total_records_ingested INTEGER NOT NULL DEFAULT 0 CHECK (total_records_ingested >= 0),
        status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'in_progress', 'completed', 'failed')),
        last_error TEXT,
        last_sync_at TEXT,
        updated_at TEXT NOT NULL
    );
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


def upsert_item(item: dict[str, Any], db_path: Path | str | None = None) -> tuple[int, str]:
    """Inserts a single intelligence item, or updates content fields if it already exists.

    When (source, source_id) already exists, updates content fields:
    (domain, title, url, text, published_at, fetched_at) while preserving user-managed
    fields (is_read, is_bookmarked).

    Returns:
        tuple (item_id, action) where action is 'inserted' or 'updated'.
    """
    validated = validate_item_payload(item)
    select_sql = "SELECT id FROM intelligence_items WHERE source = :source AND source_id = :source_id;"
    insert_sql = """
    INSERT INTO intelligence_items (
        source, source_id, domain, title, url, text,
        published_at, fetched_at, summary, relevance_score,
        relevance_reason, is_read, is_bookmarked
    ) VALUES (
        :source, :source_id, :domain, :title, :url, :text,
        :published_at, :fetched_at, :summary, :relevance_score,
        :relevance_reason, :is_read, :is_bookmarked
    );
    """
    update_sql = """
    UPDATE intelligence_items SET
        domain = :domain,
        title = :title,
        url = :url,
        text = :text,
        published_at = :published_at,
        fetched_at = :fetched_at
    WHERE id = :id;
    """
    with get_db_connection(db_path) as conn:
        with conn:
            cursor = conn.execute(
                select_sql,
                {"source": validated["source"], "source_id": validated["source_id"]},
            )
            row = cursor.fetchone()
            if row is None:
                cur = conn.execute(insert_sql, validated)
                return cur.lastrowid, "inserted"
            else:
                item_id = row["id"]
                conn.execute(update_sql, {**validated, "id": item_id})
                return item_id, "updated"


def upsert_items(items: list[dict[str, Any]], db_path: Path | str | None = None) -> dict[str, int]:
    """Safely inserts new items or updates existing items within a single database transaction.

    When (source, source_id) already exists, updates content fields:
    (domain, title, url, text, published_at, fetched_at) while preserving user-managed
    fields (is_read, is_bookmarked).

    Returns:
        dict with counts: {'inserted': count, 'updated': count}
    """
    if not items:
        return {"inserted": 0, "updated": 0}

    validated_items = [validate_item_payload(it) for it in items]
    inserted_count = 0
    updated_count = 0

    select_sql = "SELECT id FROM intelligence_items WHERE source = :source AND source_id = :source_id;"
    insert_sql = """
    INSERT INTO intelligence_items (
        source, source_id, domain, title, url, text,
        published_at, fetched_at, summary, relevance_score,
        relevance_reason, is_read, is_bookmarked
    ) VALUES (
        :source, :source_id, :domain, :title, :url, :text,
        :published_at, :fetched_at, :summary, :relevance_score,
        :relevance_reason, :is_read, :is_bookmarked
    );
    """
    update_sql = """
    UPDATE intelligence_items SET
        domain = :domain,
        title = :title,
        url = :url,
        text = :text,
        published_at = :published_at,
        fetched_at = :fetched_at
    WHERE id = :id;
    """

    with get_db_connection(db_path) as conn:
        with conn:
            for item in validated_items:
                cursor = conn.execute(
                    select_sql,
                    {"source": item["source"], "source_id": item["source_id"]},
                )
                row = cursor.fetchone()
                if row is None:
                    conn.execute(insert_sql, item)
                    inserted_count += 1
                else:
                    item_id = row["id"]
                    conn.execute(update_sql, {**item, "id": item_id})
                    updated_count += 1

    return {"inserted": inserted_count, "updated": updated_count}


def get_items(
    limit: int = 50,
    offset: int = 0,
    domain: str | None = None,
    is_read: int | None = None,
    is_bookmarked: int | None = None,
    source: str | list[str] | tuple[str, ...] | None = None,
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
    if source is not None:
        if isinstance(source, (list, tuple, set)):
            placeholders = ", ".join(f":source_{i}" for i in range(len(source)))
            conditions.append(f"source IN ({placeholders})")
            for i, s in enumerate(source):
                params[f"source_{i}"] = s
        else:
            conditions.append("source = :source")
            params["source"] = source
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
    source: str | list[str] | tuple[str, ...] | None = None,
    db_path: Path | str | None = None,
) -> int:
    """Returns total count of stored items matching optional filters."""
    conditions = []
    params: dict[str, Any] = {}

    if domain is not None:
        conditions.append("domain = :domain")
        params["domain"] = domain
    if source is not None:
        if isinstance(source, (list, tuple, set)):
            placeholders = ", ".join(f":source_{i}" for i in range(len(source)))
            conditions.append(f"source IN ({placeholders})")
            for i, s in enumerate(source):
                params[f"source_{i}"] = s
        else:
            conditions.append("source = :source")
            params["source"] = source
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


VALID_CORRELATION_STATUSES = ("all", "both", "nvd_only", "cisa_only")


def count_correlated_cves(
    filter_status: str = "all",
    db_path: Path | str | None = None,
) -> int:
    """Returns total count of correlated CVE records matching the given filter status.

    Supported filter_status values: 'all', 'both', 'nvd_only', 'cisa_only'.
    """
    if filter_status not in VALID_CORRELATION_STATUSES:
        raise ValueError(
            f"Invalid filter_status '{filter_status}'. Must be one of: {', '.join(repr(s) for s in VALID_CORRELATION_STATUSES)}."
        )

    where_clause = ""
    params: dict[str, Any] = {}
    if filter_status != "all":
        where_clause = "WHERE correlation_status = :status"
        params["status"] = filter_status

    query = f"""
    WITH nvd AS (
        SELECT id, source_id
        FROM intelligence_items
        WHERE source = 'NVD CVE'
    ),
    cisa AS (
        SELECT id, source_id
        FROM intelligence_items
        WHERE source = 'CISA KEV'
    ),
    correlated AS (
        SELECT
            CASE
                WHEN nvd.id IS NOT NULL AND cisa.id IS NOT NULL THEN 'both'
                WHEN nvd.id IS NOT NULL THEN 'nvd_only'
                ELSE 'cisa_only'
            END AS correlation_status
        FROM nvd
        FULL OUTER JOIN cisa ON nvd.source_id = cisa.source_id
    )
    SELECT COUNT(*) AS total FROM correlated {where_clause};
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        return int(row["total"]) if row else 0


def get_correlated_cves(
    filter_status: str = "all",
    limit: int = 50,
    offset: int = 0,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retrieves correlated CVE records across NVD CVE and CISA KEV sources.

    Correlates records matching on source_id (the CVE identifier) while preserving
    all individual source fields and user states (is_read, is_bookmarked).

    Supported filter_status values: 'all', 'both', 'nvd_only', 'cisa_only'.
    """
    if filter_status not in VALID_CORRELATION_STATUSES:
        raise ValueError(
            f"Invalid filter_status '{filter_status}'. Must be one of: {', '.join(repr(s) for s in VALID_CORRELATION_STATUSES)}."
        )
    if limit < 1:
        raise ValueError("Parameter 'limit' must be greater than or equal to 1.")
    if offset < 0:
        raise ValueError("Parameter 'offset' must be greater than or equal to 0.")

    where_clause = ""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if filter_status != "all":
        where_clause = "WHERE correlation_status = :status"
        params["status"] = filter_status

    query = f"""
    WITH nvd AS (
        SELECT
            id AS nvd_id,
            source_id,
            title AS nvd_title,
            url AS nvd_url,
            text AS nvd_text,
            published_at AS nvd_published_at,
            is_read AS nvd_is_read,
            is_bookmarked AS nvd_is_bookmarked
        FROM intelligence_items
        WHERE source = 'NVD CVE'
    ),
    cisa AS (
        SELECT
            id AS cisa_id,
            source_id,
            title AS cisa_title,
            url AS cisa_url,
            text AS cisa_text,
            published_at AS cisa_date_added,
            is_read AS cisa_is_read,
            is_bookmarked AS cisa_is_bookmarked
        FROM intelligence_items
        WHERE source = 'CISA KEV'
    ),
    correlated AS (
        SELECT
            COALESCE(nvd.source_id, cisa.source_id) AS cve_id,
            CASE
                WHEN nvd.nvd_id IS NOT NULL AND cisa.cisa_id IS NOT NULL THEN 'both'
                WHEN nvd.nvd_id IS NOT NULL THEN 'nvd_only'
                ELSE 'cisa_only'
            END AS correlation_status,
            nvd.nvd_id,
            nvd.nvd_title,
            nvd.nvd_url,
            nvd.nvd_text,
            nvd.nvd_published_at,
            nvd.nvd_is_read,
            nvd.nvd_is_bookmarked,
            cisa.cisa_id,
            cisa.cisa_title,
            cisa.cisa_url,
            cisa.cisa_text,
            cisa.cisa_date_added,
            cisa.cisa_is_read,
            cisa.cisa_is_bookmarked,
            MAX(COALESCE(nvd.nvd_published_at, ''), COALESCE(cisa.cisa_date_added, '')) AS latest_date
        FROM nvd
        FULL OUTER JOIN cisa ON nvd.source_id = cisa.source_id
    )
    SELECT
        cve_id,
        correlation_status,
        nvd_id,
        nvd_title,
        nvd_url,
        nvd_text,
        nvd_published_at,
        nvd_is_read,
        nvd_is_bookmarked,
        cisa_id,
        cisa_title,
        cisa_url,
        cisa_text,
        cisa_date_added,
        cisa_is_read,
        cisa_is_bookmarked
    FROM correlated
    {where_clause}
    ORDER BY latest_date DESC, cve_id DESC
    LIMIT :limit OFFSET :offset;
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


PIPELINE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
ALLOWED_CHECKPOINT_STATUSES = frozenset({"idle", "in_progress", "completed", "failed"})


if "services.database" in sys.modules and hasattr(sys.modules["services.database"], "CheckpointConflictError"):
    CheckpointConflictError = sys.modules["services.database"].CheckpointConflictError
else:
    class CheckpointConflictError(ValueError):
        """Raised when a checkpoint update conflicts with a concurrent or newer checkpoint state."""
        pass


def validate_checkpoint_dict(checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Validates checkpoint dictionary types, values, and constraints."""
    if not isinstance(checkpoint, dict):
        raise TypeError("Checkpoint must be a dictionary.")

    pipeline_id = checkpoint.get("pipeline_id")
    if not pipeline_id or not isinstance(pipeline_id, str) or not pipeline_id.strip():
        raise ValueError("Field 'pipeline_id' is required and cannot be empty.")
    pipeline_id_str = pipeline_id.strip()
    if not PIPELINE_ID_REGEX.match(pipeline_id_str):
        raise ValueError(
            f"Invalid pipeline_id '{pipeline_id_str}'. Must be alphanumeric with hyphens or underscores (1-64 characters)."
        )

    start_date = checkpoint.get("start_date")
    if not start_date or not isinstance(start_date, str) or not start_date.strip():
        raise ValueError("Field 'start_date' is required and cannot be empty.")
    start_date_str = start_date.strip()
    try:
        start_dt = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
    except Exception as e:
        raise ValueError(f"Field 'start_date' must be a valid ISO-8601 date string: {e}")

    end_date = checkpoint.get("end_date")
    if not end_date or not isinstance(end_date, str) or not end_date.strip():
        raise ValueError("Field 'end_date' is required and cannot be empty.")
    end_date_str = end_date.strip()
    try:
        end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
    except Exception as e:
        raise ValueError(f"Field 'end_date' must be a valid ISO-8601 date string: {e}")

    if start_dt > end_dt:
        raise ValueError("Field 'start_date' must be less than or equal to 'end_date'.")

    def _validate_non_negative_int(val: Any, field_name: str, default: int = 0) -> int:
        if val is None:
            return default
        if not isinstance(val, int) or isinstance(val, bool):
            raise ValueError(f"Field '{field_name}' must be an integer, got {type(val).__name__}.")
        if val < 0:
            raise ValueError(f"Field '{field_name}' must be non-negative (>= 0), got {val}.")
        return val

    current_offset = _validate_non_negative_int(checkpoint.get("current_offset", 0), "current_offset")
    last_page = _validate_non_negative_int(checkpoint.get("last_page", 0), "last_page")
    total_records = _validate_non_negative_int(
        checkpoint.get("total_records_ingested", 0), "total_records_ingested"
    )

    status = checkpoint.get("status", "idle")
    if not status or not isinstance(status, str) or not status.strip():
        raise ValueError("Field 'status' is required and cannot be empty.")
    status_str = status.strip()
    if status_str not in ALLOWED_CHECKPOINT_STATUSES:
        raise ValueError(
            f"Field 'status' must be one of {sorted(ALLOWED_CHECKPOINT_STATUSES)}, got '{status_str}'."
        )

    last_error = checkpoint.get("last_error")
    last_error_str = str(last_error) if last_error is not None else None

    last_sync_at = checkpoint.get("last_sync_at")
    last_sync_at_str = None
    if last_sync_at is not None:
        last_sync_at_str = str(last_sync_at).strip()
        if last_sync_at_str:
            try:
                datetime.fromisoformat(last_sync_at_str.replace("Z", "+00:00"))
            except Exception as e:
                raise ValueError(f"Field 'last_sync_at' must be a valid ISO-8601 date string: {e}")
        else:
            last_sync_at_str = None

    updated_at = checkpoint.get("updated_at")
    if updated_at is not None and isinstance(updated_at, str) and updated_at.strip():
        updated_at_str = updated_at.strip()
        try:
            datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        except Exception as e:
            raise ValueError(f"Field 'updated_at' must be a valid ISO-8601 date string: {e}")
    else:
        updated_at_str = datetime.now(timezone.utc).isoformat()

    expected_updated_at = checkpoint.get("expected_updated_at")
    expected_updated_at_str = (
        str(expected_updated_at).strip() if expected_updated_at is not None else None
    )

    return {
        "pipeline_id": pipeline_id_str,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "current_offset": current_offset,
        "last_page": last_page,
        "total_records_ingested": total_records,
        "status": status_str,
        "last_error": last_error_str,
        "last_sync_at": last_sync_at_str,
        "updated_at": updated_at_str,
        "expected_updated_at": expected_updated_at_str,
    }


def get_pipeline_checkpoint(
    pipeline_id: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Retrieves a stored pipeline checkpoint by pipeline_id, or None if uninitialized."""
    if not pipeline_id or not isinstance(pipeline_id, str) or not pipeline_id.strip():
        raise ValueError("Parameter 'pipeline_id' is required and cannot be empty.")

    clean_id = pipeline_id.strip()
    query = """
    SELECT
        pipeline_id,
        start_date,
        end_date,
        current_offset,
        last_page,
        total_records_ingested,
        status,
        last_error,
        last_sync_at,
        updated_at
    FROM pipeline_checkpoints
    WHERE pipeline_id = ?;
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, (clean_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)


def save_pipeline_checkpoint(
    checkpoint: dict[str, Any],
    db_path: Path | str | None = None,
) -> bool:
    """Atomically creates or updates a pipeline checkpoint with concurrency & monotonicity checks.

    Supported status transitions:
      - idle -> in_progress
      - idle -> idle
      - in_progress -> in_progress
      - in_progress -> completed
      - in_progress -> failed
      - failed -> in_progress (explicit resume)
      - failed -> failed

    Concurrency & stale update protections:
      - Optimistic concurrency control: if 'expected_updated_at' is provided, rejects update
        if existing record has been modified by another execution.
      - Monotonic progress guard: prevents rewinding date window or progress within the same window.
      - Blocks modification of completed pipelines without explicit reinitialization.
    """
    validated = validate_checkpoint_dict(checkpoint)
    pipeline_id = validated["pipeline_id"]
    new_status = validated["status"]
    new_start_date = validated["start_date"]
    new_end_date = validated["end_date"]
    new_offset = validated["current_offset"]
    new_last_page = validated["last_page"]
    new_total_records = validated["total_records_ingested"]
    expected_updated_at = validated["expected_updated_at"]

    with get_db_connection(db_path) as conn:
        with conn:  # Transaction ensures atomic check-and-upsert
            cursor = conn.execute(
                """
                SELECT
                    pipeline_id,
                    start_date,
                    end_date,
                    current_offset,
                    last_page,
                    total_records_ingested,
                    status,
                    last_error,
                    last_sync_at,
                    updated_at
                FROM pipeline_checkpoints
                WHERE pipeline_id = ?;
                """,
                (pipeline_id,),
            )
            existing_row = cursor.fetchone()

            if existing_row is None:
                # Initial checkpoint creation
                # Disallow initializing directly as completed or failed
                if new_status not in ("idle", "in_progress"):
                    raise ValueError(
                        f"Initial checkpoint status must be 'idle' or 'in_progress', got '{new_status}'."
                    )
            else:
                existing = dict(existing_row)
                existing_status = existing["status"]

                # 1. Optimistic Concurrency Control (OCC) check
                if expected_updated_at is not None:
                    if existing["updated_at"] != expected_updated_at:
                        raise CheckpointConflictError(
                            f"Concurrency conflict: checkpoint '{pipeline_id}' was modified concurrently "
                            f"(expected updated_at '{expected_updated_at}', but current is '{existing['updated_at']}')."
                        )

                # 2. Status transition validation
                valid_transitions = {
                    "idle": {"idle", "in_progress"},
                    "in_progress": {"in_progress", "completed", "failed"},
                    "failed": {"in_progress", "failed"},
                    "completed": set(),  # Cannot mutate a completed pipeline
                }
                allowed = valid_transitions.get(existing_status, set())
                if new_status not in allowed:
                    raise CheckpointConflictError(
                        f"Invalid status transition from '{existing_status}' to '{new_status}' "
                        f"for pipeline '{pipeline_id}'."
                    )

                # 3. Date window monotonicity guard
                # Ensure start_date does not regress backwards
                if new_start_date < existing["start_date"]:
                    raise CheckpointConflictError(
                        f"Stale checkpoint update: incoming start_date '{new_start_date}' is earlier than "
                        f"existing start_date '{existing['start_date']}'."
                    )

                # 4. Global cumulative ingestion count monotonicity guard
                if new_total_records < existing["total_records_ingested"]:
                    raise CheckpointConflictError(
                        f"Stale checkpoint update: incoming total_records_ingested ({new_total_records}) "
                        f"cannot be less than existing ({existing['total_records_ingested']})."
                    )

                # 5. Same window progress monotonicity guard
                if new_start_date == existing["start_date"]:
                    if new_status in ("in_progress", "completed"):
                        if new_last_page < existing["last_page"]:
                            raise CheckpointConflictError(
                                f"Stale checkpoint update: incoming last_page ({new_last_page}) "
                                f"is less than existing ({existing['last_page']})."
                            )
                        if new_offset < existing["current_offset"]:
                            raise CheckpointConflictError(
                                f"Stale checkpoint update: incoming current_offset ({new_offset}) "
                                f"is less than existing ({existing['current_offset']})."
                            )

            # Atomic Upsert Statement
            upsert_sql = """
            INSERT INTO pipeline_checkpoints (
                pipeline_id,
                start_date,
                end_date,
                current_offset,
                last_page,
                total_records_ingested,
                status,
                last_error,
                last_sync_at,
                updated_at
            ) VALUES (
                :pipeline_id,
                :start_date,
                :end_date,
                :current_offset,
                :last_page,
                :total_records_ingested,
                :status,
                :last_error,
                :last_sync_at,
                :updated_at
            )
            ON CONFLICT(pipeline_id) DO UPDATE SET
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                current_offset = excluded.current_offset,
                last_page = excluded.last_page,
                total_records_ingested = excluded.total_records_ingested,
                status = excluded.status,
                last_error = excluded.last_error,
                last_sync_at = excluded.last_sync_at,
                updated_at = excluded.updated_at;
            """
            conn.execute(
                upsert_sql,
                {
                    "pipeline_id": validated["pipeline_id"],
                    "start_date": validated["start_date"],
                    "end_date": validated["end_date"],
                    "current_offset": validated["current_offset"],
                    "last_page": validated["last_page"],
                    "total_records_ingested": validated["total_records_ingested"],
                    "status": validated["status"],
                    "last_error": validated["last_error"],
                    "last_sync_at": validated["last_sync_at"],
                    "updated_at": validated["updated_at"],
                },
            )
    return True
