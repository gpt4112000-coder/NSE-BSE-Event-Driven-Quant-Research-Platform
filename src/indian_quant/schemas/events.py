"""Generic research event envelope for event studies and regime tagging."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ResearchEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    instrument_id: str
    event_time: datetime
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "derived"


class RegimeLabel(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    regime: Literal["BULL", "BEAR", "SIDEWAYS", "HIGH_VOL", "LOW_VOL"]
    score: float | None = None
    method: str = "unknown"
