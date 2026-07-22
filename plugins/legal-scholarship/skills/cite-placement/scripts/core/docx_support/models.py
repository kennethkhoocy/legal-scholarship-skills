"""Pydantic models for .docx processing (subset imported from word-docx skill)."""

from __future__ import annotations

from pydantic import BaseModel


class ParagraphRecord(BaseModel):
    index: int
    style: str
    text: str


class DiagnosticEntry(BaseModel):
    level: str
    source: str
    message: str
