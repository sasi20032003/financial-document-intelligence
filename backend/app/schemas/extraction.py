"""Schemas for complete, grounded document extraction."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Evidence(BaseModel):
    source_text: str | None = None
    page_number: int | None = Field(default=None, ge=1)


class ExtractedField(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    label: str
    value: Any = None
    raw_value: str | None = None
    data_type: Literal[
        "string",
        "number",
        "date",
        "currency",
        "percentage",
        "identifier",
        "boolean",
        "unknown",
    ] = "string"
    period: str | None = None
    section: str | None = None
    evidence: Evidence = Field(default_factory=Evidence)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        cleaned = "_".join(value.strip().lower().replace("/", " ").split())
        return "".join(ch for ch in cleaned if ch.isalnum() or ch == "_").strip("_")


class ExtractedTable(BaseModel):
    name: str
    title: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str | None]] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    document_title: str | None = None
    currency: str | None = None
    periods: list[str] = Field(default_factory=list)
    fields: list[ExtractedField] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
