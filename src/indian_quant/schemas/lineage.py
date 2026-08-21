"""Data lineage: every persisted record must answer 'where did this number come from?'."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from indian_quant.schemas.enums import SCHEMA_VERSION


def utc_now() -> datetime:
    return datetime.now(UTC)


class Lineage(BaseModel):
    source: str
    source_tool: str
    source_request_id: str | None = None
    source_timestamp: datetime | None = None
    ingestion_timestamp: datetime = Field(default_factory=utc_now)
    raw_hash: str | None = None
    schema_version: int = SCHEMA_VERSION


class QualityStamp(BaseModel):
    status: str = "RAW"
    validated_at: datetime | None = None
    validator_version: int = 1
    issues: list[str] = Field(default_factory=list)
