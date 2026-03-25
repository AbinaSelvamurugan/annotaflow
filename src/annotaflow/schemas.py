"""Pydantic schema for canonical input records after configurable column mapping."""
from pydantic import BaseModel, ConfigDict, Field


class CanonicalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str = Field(min_length=1)
    text: str = Field(strict=True, min_length=1)
    existing_label: str | None = None
    source: str | None = None
    category: str | None = None
