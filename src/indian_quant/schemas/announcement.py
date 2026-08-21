"""Announcement contract. Never mixed with price data; feeds event studies."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Announcement(BaseModel):
    model_config = ConfigDict(frozen=True)

    announcement_id: str
    instrument_id: str
    exchange: str

    published_at: datetime
    event_date: date | None = None

    category: str | None = None
    headline: str
    description: str | None = None

    document_url: str | None = None

    source: str
    source_timestamp: datetime | None = None
    ingestion_timestamp: datetime | None = None
    raw_document_hash: str | None = None

    extra: dict[str, Any] = Field(default_factory=dict)
