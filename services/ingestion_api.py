"""AI Pulse Data Ingestion API.

Provides an authenticated FastAPI endpoint to ingest and normalize intelligence
records into the SQLite database.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import secrets
from typing import Any, AsyncGenerator, Literal, Union

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator, model_validator

from services.database import (
    DEFAULT_DB_PATH,
    CheckpointConflictError,
    get_pipeline_checkpoint,
    init_db,
    insert_items,
    save_pipeline_checkpoint,
    upsert_items,
)

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
    updated: int = Field(default=0, description="Count of existing items updated with new metadata")
    skipped: int = Field(default=0, description="Count of duplicate items skipped")
    message: str | None = Field(default=None, description="Optional status message")


PIPELINE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def validate_pipeline_id(pipeline_id: str) -> str:
    """Validates that pipeline_id adheres to safe alphanumeric/hyphen/underscore naming."""
    clean_id = pipeline_id.strip() if isinstance(pipeline_id, str) else ""
    if not clean_id or not PIPELINE_ID_PATTERN.match(clean_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid pipeline identifier '{pipeline_id}'. "
                "Must be alphanumeric with hyphens or underscores (1-64 characters)."
            ),
        )
    return clean_id


class CheckpointPayload(BaseModel):
    """Pydantic model for setting or updating a pipeline checkpoint."""

    start_date: str = Field(..., description="Start date of the current window (ISO-8601)")
    end_date: str = Field(..., description="End date of the current window (ISO-8601)")
    current_offset: int = Field(0, ge=0, description="Next pagination offset (NVD startIndex)")
    last_page: int = Field(0, ge=0, description="Last successfully committed page index")
    total_records_ingested: int = Field(0, ge=0, description="Cumulative records ingested")
    status: Literal["idle", "in_progress", "completed", "failed"] = Field(
        "idle", description="Current pipeline execution status"
    )
    last_error: str | None = Field(default=None, description="Error message if status is failed")
    last_sync_at: str | None = Field(default=None, description="Timestamp of last successful commit")
    updated_at: str | None = Field(default=None, description="ISO-8601 timestamp of this update")
    expected_updated_at: str | None = Field(
        default=None,
        description="Optional concurrency token for optimistic concurrency control",
    )

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_iso_dates(cls, value: Any, info) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Field '{info.field_name}' must be a non-empty ISO-8601 date string.")
        cleaned = value.strip()
        try:
            datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except Exception as e:
            raise ValueError(f"Field '{info.field_name}' must be a valid ISO-8601 date string: {e}")
        return cleaned

    @field_validator("last_sync_at", "updated_at", "expected_updated_at", mode="before")
    @classmethod
    def validate_optional_iso_dates(cls, value: Any, info) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            return None
        cleaned = value.strip()
        try:
            datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except Exception as e:
            raise ValueError(f"Field '{info.field_name}' must be a valid ISO-8601 date string: {e}")
        return cleaned

    @model_validator(mode="after")
    def validate_date_window(self) -> "CheckpointPayload":
        start = datetime.fromisoformat(self.start_date.replace("Z", "+00:00"))
        end = datetime.fromisoformat(self.end_date.replace("Z", "+00:00"))
        if start > end:
            raise ValueError("Field 'start_date' must be less than or equal to 'end_date'.")
        return self


class CheckpointData(BaseModel):
    """Schema representing structured checkpoint data."""

    pipeline_id: str
    start_date: str
    end_date: str
    current_offset: int
    last_page: int
    total_records_ingested: int
    status: Literal["idle", "in_progress", "completed", "failed"]
    last_error: str | None = None
    last_sync_at: str | None = None
    updated_at: str


class CheckpointResponse(BaseModel):
    """Response returned when querying a pipeline checkpoint."""

    pipeline_id: str
    initialized: bool
    status: Literal["idle", "in_progress", "completed", "failed"] | None = None
    start_date: str | None = None
    end_date: str | None = None
    current_offset: int | None = None
    last_page: int | None = None
    total_records_ingested: int | None = None
    last_error: str | None = None
    last_sync_at: str | None = None
    updated_at: str | None = None
    checkpoint: CheckpointData | None = None
    message: str


class CheckpointSaveResponse(BaseModel):
    """Response returned upon saving a pipeline checkpoint."""

    pipeline_id: str
    saved: bool
    status: Literal["idle", "in_progress", "completed", "failed"]
    checkpoint: CheckpointData
    message: str


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
            updated=0,
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

    # Persist via database layer using duplicate-updating transaction
    received_count = len(db_items)
    counts = upsert_items(db_items, db_path=db_path)
    inserted_count = counts["inserted"]
    updated_count = counts["updated"]
    skipped_count = received_count - (inserted_count + updated_count)

    return IngestResponse(
        received=received_count,
        inserted=inserted_count,
        updated=updated_count,
        skipped=skipped_count,
    )


@app.get(
    "/api/v1/checkpoint/{pipeline_id}",
    response_model=CheckpointResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve pipeline checkpoint",
    description="Retrieves the current execution checkpoint for a pipeline. Returns uninitialized response if not found.",
)
def get_checkpoint_endpoint(
    pipeline_id: str,
    db_path: Path = Depends(get_active_db_path),
    authenticated: bool = Depends(verify_bearer_token),
) -> CheckpointResponse:
    """Retrieves stored checkpoint for pipeline_id or returns a clear uninitialized response."""
    clean_id = validate_pipeline_id(pipeline_id)
    init_db(db_path)

    record = get_pipeline_checkpoint(clean_id, db_path=db_path)
    if record is None:
        return CheckpointResponse(
            pipeline_id=clean_id,
            initialized=False,
            message=f"Pipeline checkpoint '{clean_id}' has not been initialized.",
        )

    data = CheckpointData(**record)
    return CheckpointResponse(
        pipeline_id=clean_id,
        initialized=True,
        status=data.status,
        start_date=data.start_date,
        end_date=data.end_date,
        current_offset=data.current_offset,
        last_page=data.last_page,
        total_records_ingested=data.total_records_ingested,
        last_error=data.last_error,
        last_sync_at=data.last_sync_at,
        updated_at=data.updated_at,
        checkpoint=data,
        message="Checkpoint retrieved successfully.",
    )


@app.post(
    "/api/v1/checkpoint/{pipeline_id}",
    response_model=CheckpointSaveResponse,
    status_code=status.HTTP_200_OK,
    summary="Save or advance pipeline checkpoint",
    description="Atomically upserts a pipeline checkpoint with optimistic concurrency and monotonicity validation.",
)
def set_pipeline_checkpoint(
    pipeline_id: str,
    payload: CheckpointPayload = Body(...),
    db_path: Path = Depends(get_active_db_path),
    authenticated: bool = Depends(verify_bearer_token),
) -> CheckpointSaveResponse:
    """Saves or advances a pipeline checkpoint atomically."""
    clean_id = validate_pipeline_id(pipeline_id)
    init_db(db_path)

    checkpoint_dict = payload.model_dump()
    checkpoint_dict["pipeline_id"] = clean_id

    try:
        save_pipeline_checkpoint(checkpoint_dict, db_path=db_path)
    except Exception as err:
        if type(err).__name__ == "CheckpointConflictError" or isinstance(err, CheckpointConflictError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(err),
            )
        if isinstance(err, ValueError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(err),
            )
        raise

    updated_record = get_pipeline_checkpoint(clean_id, db_path=db_path)
    if not updated_record:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Checkpoint saved but could not be re-read from database.",
        )

    return CheckpointSaveResponse(
        pipeline_id=clean_id,
        saved=True,
        status=updated_record["status"],
        checkpoint=CheckpointData(**updated_record),
        message="Checkpoint saved successfully.",
    )
