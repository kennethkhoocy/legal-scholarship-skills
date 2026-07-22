"""Shared Pydantic models for word-docx pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Output / extraction models ─────────────────────────────────────────────
#
# These describe data extracted from upstream libraries (docx2python,
# docx-revisions, lxml). They intentionally tolerate extra fields so that
# library variance does not break parsing of returned objects.


class Comment(BaseModel):
    comment_id: str
    ooxml_id: str | None = None
    paragraph_index: int | None = None
    author: str
    date: str
    reference_text: str
    comment_text: str
    source: str = "docx2python"


class Revision(BaseModel):
    revision_id: str
    type: str
    author: str
    date: str
    text: str
    paragraph_index: int | None = None
    location: str | None = None
    source: str = "ooxml"


class ParagraphRecord(BaseModel):
    index: int
    style: str
    text: str


class DiagnosticEntry(BaseModel):
    level: str
    source: str
    message: str


class Manifest(BaseModel):
    input_file: str
    output_dir: str
    timestamp: str
    files: list[str]
    diagnostics: list[DiagnosticEntry] = []


class Section(BaseModel):
    heading: str
    paragraphs: list[str]


class ResponseItem(BaseModel):
    comment_id: str
    comment: str
    response: str
    revision_made: str = ""


# ── Input / spec models ────────────────────────────────────────────────────
#
# These describe user-authored JSON specs that drive the pipeline. They
# forbid extra fields so typos surface at parse time, and they restrict
# enum-like attributes to Literal values so misspelled options are caught
# instead of silently matching no branch at runtime.


class PageMargins(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top: float = 1.0
    bottom: float = 1.0
    left: float = 1.0
    right: float = 1.0


class PageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    size: Literal["letter", "a4"] = "letter"
    orientation: Literal["portrait", "landscape"] = "portrait"
    margins: PageMargins = PageMargins()


class TocConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = "Contents"
    heading_range: str = "1-3"
    hyperlinks: bool = True


class PageSectionElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text", "page_number"]
    value: str | None = None   # for type=text


class PageSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: list[PageSectionElement] = []
    footer: list[PageSectionElement] = []


class InternalLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor: str
    label: str
    text: str | None = None    # optional display text; defaults to label


class BuildSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    subtitle: str | None = None
    sections: list[Section] = []
    items: list[ResponseItem] = []
    footnotes: dict[str, str] = {}                   # post-processed in python path

    # Phase 4 additions
    runtime: Literal["auto", "python", "js"] = "auto"
    page: PageConfig = PageConfig()
    toc: TocConfig | None = None
    columns: int = 1
    page_sections: list[PageSection] = []
    internal_links: list[InternalLink] = []
    native_footnotes: dict[str, str] = {}            # routed to js (FootnoteReferenceRun)


class EditOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["replace", "insert", "delete"]
    paragraph_index: int
    old_text: str | None = None
    new_text: str | None = None
    author: str = "LLM"
    date: str | None = None


class AddCommentSpec(BaseModel):
    """One of three sub-modes, validated at parse time."""

    model_config = ConfigDict(extra="forbid")

    mode: str  # "reply" | "new" | "resolve"
    text: str | None = None
    author: str = "Claude"
    reply_to: str | None = None         # mode=reply, e.g. "C001"
    anchor_paragraph: int | None = None  # mode=new
    anchor_text: str | None = None       # mode=new
    resolve: str | None = None           # mode=resolve, e.g. "C001"

    def validate_mode(self) -> None:
        if self.mode == "reply":
            if not self.reply_to or not self.text:
                raise ValueError("reply mode requires --reply-to and --text")
        elif self.mode == "new":
            if self.anchor_paragraph is None or not self.anchor_text or not self.text:
                raise ValueError("new mode requires --anchor-paragraph, --anchor-text, and --text")
        elif self.mode == "resolve":
            if not self.resolve:
                raise ValueError("resolve mode requires --resolve")
        else:
            raise ValueError(f"unknown mode: {self.mode}")
