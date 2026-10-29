"""AI Pulse Data Ingestion API.

Provides an authenticated FastAPI endpoint to ingest and normalize intelligence
records into the SQLite database.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
from typing import Any, AsyncGenerator, Literal, Union

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from services.database import DEFAULT_DB_PATH, init_db, insert_items

# Load environment variables from .env file if present
load_dotenv()

# Allowed source and domain taxonomies
AllowedSource = Literal[
    "arXiv",
    "Hacker News",
    "GitHub Releases",
    "NVD CVE",
    "CISA KEV",
]

AllowedDomain = Literal[
    "AI research",
    "dev-tools",
    "cybersecurity",
]


class NormalizedRecord(BaseModel):
    """Pydantic model representing a single normalized intelligence item."""

    id: str = Field(..., min_length=1, description="Stable source-specific identifier")
    source: AllowedSource = Field(..., description="Normalized source name")
    domain: AllowedDomain = Field(..., description="Intelligence category domain")
    title: str = Field(..., min_length=1, description="Non-empty record title")
    url: str | None = Field(default=None, description="Original source URL")
    text: str | None = Field(default=None, description="Description, abstract, or discussion")
    published_at: str | None = Field(default=None, description="Source publication timestamp")
    fetched_at: str | None = Field(
        default=None,
        description="Collection timestamp. Defaults to UTC now if omitted.",
    )

    @field_validator("id", "title", mode="before")
    @classmethod
    def validate_non_empty_strings(cls, value: Any, info) -> str:
        """Ensures identifiers and titles are non-empty after trimming."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Field '{info.field_name}' must be a non-empty string.")
        return value.strip()


class IngestPayload(BaseModel):
    """Container schema for bulk record submission."""

    items: list[NormalizedRecord] = Field(
        default_factory=list,
        description="List of normalized intelligence items",
    )


class IngestResponse(BaseModel):
    """Response returned upon successful processing of an ingestion batch."""

    received: int = Field(..., description="Total items received in the batch")
    inserted: int = Field(..., description="Count of newly persisted items")
    skipped: int = Field(..., description="Count of duplicate items skipped")
    message: str | None = Field(default=None, description="Optional status message")


# Authentication Security Scheme
security_bearer = HTTPBearer(auto_error=False)


def get_expected_token() -> str | None:
    """Retrieves the configured ingestion bearer token from the environment."""
    token = os.environ.get("INGEST_API_TOKEN")
    if token and token.strip():
        return token.strip()
    return None


def verify_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Security(security_bearer),
) -> bool:
    """Verifies the Bearer token using constant-time string comparison.
    
    Raises HTTP 401 if token is missing, invalid, or if the server token is unconfigured.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expected_token = get_expected_token()
    if not expected_token:
        # Reject safely if INGEST_API_TOKEN is unconfigured or empty
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: INGEST_API_TOKEN is not configured on server.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    provided_token = credentials.credentials
    # Constant-time comparison prevents timing attacks
    if not secrets.compare_digest(provided_token.encode("utf-8"), expected_token.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True


def get_active_db_path() -> Path:
    """Resolves target database path, supporting environment overrides for tests."""
    custom_path = os.environ.get("AI_PULSE_DB_PATH")
    if custom_path:
        return Path(custom_path)
    return DEFAULT_DB_PATH


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]:
    """Ensures database schema is initialized during application startup."""
    active_path = get_active_db_path()
    init_db(active_path)
    yield


# Create FastAPI application
app = FastAPI(
    title="AI Pulse Ingestion API",
    version="1.0.0",
    description="Authenticated ingestion API for AI Pulse intelligence dashboard.",
    lifespan=lifespan,
)


@app.post(
    "/api/v1/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest normalized intelligence records",
    description="Accepts a list of records (or {'items': [...]}), persists new items, and skips duplicates.",
)
def ingest_records(
    payload: Union[IngestPayload, list[NormalizedRecord]] = Body(
        ...,
        description="Payload containing records as a list or under an 'items' key",
    ),
    db_path: Path = Depends(get_active_db_path),
    authenticated: bool = Depends(verify_bearer_token),
) -> IngestResponse:
    """Ingests, normalizes, and stores intelligence items into SQLite."""
    # Support both direct list `[...]` and object container `{"items": [...]}`
    records = payload.items if isinstance(payload, IngestPayload) else payload

    # Policy for empty batch submission
    if not records:
        return IngestResponse(
            received=0,
            inserted=0,
            skipped=0,
            message="Empty batch received; no records to ingest.",
        )

    # Ensure target database is initialized
    init_db(db_path)

    # Map normalized API records to database schema
    # Map incoming source-specific `id` to `source_id`
    current_utc = datetime.now(timezone.utc).isoformat()
    db_items: list[dict[str, Any]] = []

    for record in records:
        db_items.append(
            {
                "source": record.source,
                "source_id": record.id,
                "domain": record.domain,
                "title": record.title,
                "url": record.url,
                "text": record.text,
                "published_at": record.published_at,
                # Documented policy: use current UTC timestamp if fetched_at is absent
                "fetched_at": record.fetched_at if record.fetched_at is not None else current_utc,
                "summary": None,
                "relevance_score": None,
                "relevance_reason": None,
                "is_read": 0,
                "is_bookmarked": 0,
            }
        )

    # Persist via database layer using duplicate-ignoring transaction
    received_count = len(db_items)
    inserted_count = insert_items(db_items, db_path=db_path)
    skipped_count = received_count - inserted_count

    return IngestResponse(
        received=received_count,
        inserted=inserted_count,
        skipped=skipped_count,
    )
