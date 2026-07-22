#!/usr/bin/env python3
"""
Phase 6: Bluebook short-form post-processing.

Converts repeated full citations to Id., supra note N, and inserts
hereinafter for same-author disambiguation.

Usage:
    python scripts/short_form.py --input Manuscript_cited.tex --output Manuscript_cited.tex
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ── Data structures ──────────────────────────────────────────────────


@dataclass
class Citation:
    """A single citation within a footnote."""

    raw: str  # Original text of this citation
    signal: str  # Introductory signal (e.g., "See", "See also", "")
    author_raw: str  # Full author string as written
    author_key: str  # Normalized: last name(s) for identity
    title: str  # Title text (without \textit{} or \textsc{})
    title_cmd: str  # "textit" or "textsc"
    identity_key: str  # author_key + "|" + normalized title
    is_short_form: bool = False  # Already a supra/Id. reference
    year: str = ""  # Publication year (extracted for APA short form)


@dataclass
class Footnote:
    """A single footnote in the document."""

    number: int  # Sequential footnote number (1-based)
    start: int  # Character offset of \footnote{ in the file
    end: int  # Character offset after closing }
    content: str  # Text inside \footnote{...} (marker stripped)
    has_marker: bool = False  # True if %CITE-PLACED marker was present
    citations: list[Citation] = field(default_factory=list)
    skip: bool = False  # True if footnote should not be processed


@dataclass
class WorkInfo:
    """Tracks a unique work across the document."""

    identity_key: str
    author_key: str
    title: str
    title_cmd: str
    first_fn: int  # Footnote number of first full occurrence
    short_title: str = ""  # Set if hereinafter needed
    needs_hereinafter: bool = False
    year: str = ""  # Publication year (for APA short form)


# ── Style configuration ─────────────────────────────────────────────

_DEFAULT_SIGNALS = [
    "See generally", "See also", "But see", "But cf.",
    "Compare", "Cf.", "See", "E.g.,",
]

_DEFAULT_SHORT_FORMS = {
    "ibid_term": "\\textit{Id.}",
    "ibid_require_sole_citation": True,
    "ibid_require_immediately_preceding": True,
    "supra_template": "{signal}{author}, \\textit{{supra}} note {n}",
    "supra_with_short_title_template": (
        "{signal}{author}, \\textit{{{short_title}}}, "
        "\\textit{{supra}} note {n}"
    ),
    "hereinafter_template": "[hereinafter \\textit{{{short_title}}}]",
    "use_hereinafter": True,
    "et_al_threshold": 3,
    "et_al_format": "{first_author} et al.",
    "two_author_format": "{first_author} \\& {second_author}",
}

_DEFAULT_MERGE = {
    "separator": "; ",
    "lowercase_signals_after_first": True,
    "end_punctuation": ".",
}


@dataclass
class StyleConfig:
    """Loaded style configuration."""
    style_id: str = "bluebook"
    signals: list[str] = field(default_factory=lambda: list(_DEFAULT_SIGNALS))
    short_forms: dict = field(default_factory=lambda: dict(_DEFAULT_SHORT_FORMS))
    merge: dict = field(default_factory=lambda: dict(_DEFAULT_MERGE))
    signal_pattern: re.Pattern = field(default=None)
    signal_literals: list[str] = field(default_factory=list)
    signal_lowercase_re: re.Pattern = field(default=None)

    def __post_init__(self):
        self._rebuild_patterns()

    def _rebuild_patterns(self):
        self.signal_literals = list(self.signals)
        if self.signals:
            escaped = [re.escape(s) for s in self.signals]
            self.signal_pattern = re.compile(
                r"^(" + "|".join(escaped) + r")\s+", re.IGNORECASE
            )
            self.signal_lowercase_re = re.compile(
                r"^(" + "|".join(re.escape(s) for s in self.signals) + r")(\s)",
                re.IGNORECASE,
            )
        else:
            self.signal_pattern = re.compile(r"(?!)")
            self.signal_lowercase_re = re.compile(r"(?!)")


def load_style(style_id: str, skill_dir: str | None = None) -> StyleConfig:
    """Load a style JSON config and return a StyleConfig."""
    if skill_dir is None:
        skill_dir = str(Path(__file__).parent.parent)

    style_path = Path(skill_dir) / "references" / "styles" / f"{style_id}.json"
    if not style_path.is_file():
        print(f"  Warning: style config not found: {style_path}, using Bluebook defaults")
        return StyleConfig()

    raw = json.loads(style_path.read_text(encoding="utf-8"))
    cfg = StyleConfig(
        style_id=raw.get("style_id", style_id),
        signals=raw.get("signals", list(_DEFAULT_SIGNALS)),
        short_forms={**_DEFAULT_SHORT_FORMS, **raw.get("short_forms", {})},
        merge={**_DEFAULT_MERGE, **raw.get("merge", {})},
    )
    return cfg


# Module-level default (overridden by process())
_style = StyleConfig()


def lowercase_signal_after_first(parts: list[str], style: StyleConfig) -> list[str]:
    """Lowercase the leading signal in all parts after the first."""
    if not style.merge.get("lowercase_signals_after_first", True):
        return parts
    result = []
    for i, part in enumerate(parts):
        if i == 0:
            result.append(part)
        else:
            m = style.signal_lowercase_re.match(part)
            if m:
                lowered = m.group(1)[0].lower() + m.group(1)[1:]
                result.append(lowered + m.group(2) + part[m.end():])
            else:
                result.append(part)
    return result


MARKER = "%CITE-PLACED"

STOP_WORDS = {
    "a", "an", "the", "of", "in", "on", "for", "and", "or",
    "to", "from", "with", "by", "at", "is", "are", "was", "were",
}


# ── Footnote extraction ─────────────────────────────────────────────


def extract_footnotes(tex: str) -> list[Footnote]:
    """Find all \\footnote{...} in document order, handling nested braces."""
    footnotes = []
    pattern = re.compile(r"\\footnote\{")
    fn_num = 0

    for m in pattern.finditer(tex):
        start = m.start()
        depth = 1
        pos = m.end()
        while pos < len(tex) and depth > 0:
            if tex[pos] == "{":
                depth += 1
            elif tex[pos] == "}":
                depth -= 1
            pos += 1

        if depth != 0:
            continue  # Malformed footnote, skip

        fn_num += 1
        content = tex[m.end() : pos - 1]
        # Strip %CITE-PLACED marker if present, record its presence
        has_marker = False
        if content.startswith(MARKER + "\n"):
            has_marker = True
            content = content[len(MARKER) + 1:]
        elif content.startswith(MARKER):
            has_marker = True
            content = content[len(MARKER):]
        footnotes.append(
            Footnote(number=fn_num, start=start, end=pos, content=content,
                     has_marker=has_marker)
        )

    return footnotes


# ── Citation parsing ─────────────────────────────────────────────────


def split_citations(content: str) -> list[str]:
    """Split footnote content into individual citations at top-level semicolons."""
    parts = []
    depth = 0
    current: list[str] = []

    for ch in content:
        if ch == "{":
            depth += 1
            current.append(ch)
        elif ch == "}":
            depth -= 1
            current.append(ch)
        elif ch == ";" and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)

    remainder = "".join(current).strip()
    if remainder:
        parts.append(remainder)

    return parts


def find_brace_content(text: str, start: int) -> tuple[str, int] | None:
    """From position after opening {, find matching } and return (content, end_pos)."""
    depth = 1
    pos = start
    while pos < len(text) and depth > 0:
        if text[pos] == "{":
            depth += 1
        elif text[pos] == "}":
            depth -= 1
        pos += 1
    if depth == 0:
        return (text[start : pos - 1], pos)
    return None


def extract_title(text: str) -> tuple[str, str, int, int] | None:
    """Extract first \\textit{...} or \\textsc{...} title from text.

    Returns (title_text, command_name, match_start, match_end) or None.
    """
    for cmd in ("textit", "textsc"):
        pat = re.compile(r"\\%s\{" % cmd)
        m = pat.search(text)
        if m:
            result = find_brace_content(text, m.end())
            if result:
                title_text, end_pos = result
                return (title_text, cmd, m.start(), end_pos)
    return None


def normalize_author(author_raw: str, style: StyleConfig | None = None) -> str:
    """Extract last name(s) for short-form references.

    Respects style config for et al. threshold and two-author format.
    """
    cleaned = author_raw.replace("\\&", "&").replace("\\", "").strip()

    parts = re.split(r"\s*[,&]\s*|\s+and\s+", cleaned)
    parts = [p.strip() for p in parts if p.strip()]

    if not parts:
        return cleaned

    sf = (style.short_forms if style else _DEFAULT_SHORT_FORMS)
    et_al_threshold = sf.get("et_al_threshold", 3)
    et_al_fmt = sf.get("et_al_format", "{first_author} et al.")
    two_fmt = sf.get("two_author_format", "{first_author} \\& {second_author}")

    def last_name(full_name: str) -> str:
        words = full_name.split()
        return words[-1].rstrip(".,;:") if words else full_name

    if len(parts) >= et_al_threshold:
        return et_al_fmt.format(first_author=last_name(parts[0]))
    elif len(parts) == 2:
        return two_fmt.format(
            first_author=last_name(parts[0]),
            second_author=last_name(parts[1]),
        )
    else:
        return last_name(parts[0])


def parse_citation(text: str, style: StyleConfig | None = None) -> Citation | None:
    """Parse a single citation string into a Citation object."""
    text = text.strip()
    if not text:
        return None

    if style is None:
        style = _style

    # Check if already short form (covers all styles)
    short_form_markers = [
        r"\textit{Id.}", r"\textit{supra}", "ibid", r"\textit{Ibid}",
        "Ibid.", "(n ",  # OSCOLA cross-ref
    ]
    if any(marker in text for marker in short_form_markers):
        return Citation(
            raw=text, signal="", author_raw="", author_key="",
            title="", title_cmd="", identity_key="", is_short_form=True,
        )

    # Check for infra — skip
    if re.search(r"\\textit\s*\{[Ii]nfra\}", text) or re.search(
        r"\binfra\b", text, re.IGNORECASE
    ):
        return None

    # Extract signal
    signal = ""
    remaining = text
    sm = style.signal_pattern.match(text)
    if sm:
        matched = sm.group(1)
        for lit in style.signal_literals:
            if re.fullmatch(re.escape(lit).replace(r"\.", r"\."), matched, re.IGNORECASE):
                signal = lit
                break
        else:
            signal = matched
        remaining = text[sm.end() :]

    # Extract title
    title_result = extract_title(remaining)
    if title_result is None:
        return None

    title, title_cmd, title_start, _title_end = title_result

    # Extract author: text before the title command, up to trailing comma
    author_region = remaining[:title_start].strip()
    author_raw = author_region.rstrip(", \t\n")

    if not author_raw and title_cmd == "textsc":
        comma_pos = title.find(",")
        if comma_pos > 0:
            author_raw = title[:comma_pos].strip()
            title = title[comma_pos + 1 :].strip()

    if not author_raw:
        return None

    author_key = normalize_author(author_raw, style)

    # Extract year (for APA short form)
    year_match = re.search(r"\((\d{4})\)", text)
    year = year_match.group(1) if year_match else ""

    # Normalize title for identity key
    norm_title = re.sub(r"\s+", " ", title).strip().lower()
    norm_title = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", norm_title)
    norm_title = re.sub(r"[{}\\]", "", norm_title)
    identity_key = f"{author_key.lower()}|{norm_title}"

    return Citation(
        raw=text, signal=signal, author_raw=author_raw,
        author_key=author_key, title=title, title_cmd=title_cmd,
        identity_key=identity_key, year=year,
    )


def parse_footnote_citations(fn: Footnote, style: StyleConfig | None = None) -> None:
    """Parse citations within a footnote and populate fn.citations."""
    content = fn.content.strip()

    if re.search(r"\\textit\s*\{[Ii]nfra\}", content):
        fn.skip = True
        return

    parts = split_citations(content)
    for part in parts:
        cite = parse_citation(part, style)
        if cite is not None:
            fn.citations.append(cite)

    if not fn.citations:
        fn.skip = True


# ── Short title generation ───────────────────────────────────────────


def generate_short_title_deterministic(title: str) -> str:
    """Fallback: generate a short title from a full title via truncation.

    Take first substantive word/phrase, excluding articles and prepositions.
    """
    cleaned = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", title)
    cleaned = re.sub(r"\\[a-zA-Z]+", "", cleaned)
    cleaned = re.sub(r"[{}]", "", cleaned)

    main = re.split(r"\s*[:\u2014\u2013]{1,2}\s*|---+|--+", cleaned)[0].strip()

    words = main.split()
    start = 0
    while start < len(words) and words[start].lower().rstrip(".,;:") in STOP_WORDS:
        start += 1

    if start >= len(words):
        start = 0

    substantive = words[start : start + 3]
    return " ".join(substantive).rstrip(".,;:")


def generate_short_titles_llm(
    conflicts: dict[str, list[str]],
    style: StyleConfig | None = None,
) -> dict[str, str] | None:
    """Use Claude API to generate distinctive short titles for same-author works.

    Args:
        conflicts: {author_key: [full_title_1, full_title_2, ...]}
        style: Style configuration (affects prompt framing).

    Returns:
        {full_title: short_title} mapping, or None on failure.
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        print("    Warning: anthropic package not installed, using deterministic fallback")
        return None

    style_name = (style.style_id if style else "bluebook").replace("_", " ").title()

    prompt_parts: list[str] = []
    for author, titles in conflicts.items():
        prompt_parts.append(f"Author: {author}")
        for i, title in enumerate(titles, 1):
            prompt_parts.append(f"  {i}. {title}")
        prompt_parts.append("")

    try:
        client = Anthropic()
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    f"You are a {style_name} citation expert. For each author below "
                    "who has multiple works, generate a SHORT TITLE for each work that "
                    "will be used for disambiguation in short-form references.\n\n"
                    "Rules for short titles:\n"
                    "- The short title must UNIQUELY IDENTIFY this work among the "
                    "same author's other works.\n"
                    "- Prefer the most SPECIFIC and RECOGNISABLE noun phrase -- "
                    "typically the methodology (e.g., 'Meta-Empirical Study', "
                    "'Regression Discontinuity'), dataset (e.g., 'Shanghai-Shenzhen "
                    "Data'), institutional setting (e.g., 'Mandatory Board Reforms', "
                    "'Anti-Corruption Campaign'), or distinctive concept.\n"
                    "- Do NOT pick generic outcome variables or common "
                    "dependent-variable phrases like 'Firm Value', 'Corporate "
                    "Performance', 'Market Returns', 'Stock Prices', 'Financial "
                    "Performance'. These could describe dozens of papers and are "
                    "useless as identifiers.\n"
                    "- Do NOT just take the first few words of the title. Skip "
                    "shared prefixes.\n"
                    "- If the title has a colon or subtitle, the distinctive part is "
                    "often AFTER the colon (e.g., 'Evidence from Mandatory Board "
                    "Reforms' -> 'Mandatory Board Reforms').\n"
                    "- Keep short titles to 2-4 words maximum.\n"
                    "- The short title must be a substring or close paraphrase of "
                    "the original title -- do not invent new phrases.\n\n"
                    + "\n".join(prompt_parts) + "\n"
                    "Respond in EXACTLY this format, one line per title, no extra text:\n"
                    "FULL TITLE ||| SHORT TITLE"
                ),
            }],
        )

        result: dict[str, str] = {}
        response_text = message.content[0].text.strip()
        for line in response_text.split("\n"):
            line = line.strip()
            if "|||" in line:
                full, short = line.split("|||", 1)
                result[full.strip()] = short.strip()

        # Validate: every conflict title should have a mapping
        all_titles = [t for titles in conflicts.values() for t in titles]
        missing = [t for t in all_titles if t not in result]
        if missing:
            print(f"    Warning: LLM response missing {len(missing)} titles, "
                  "attempting fuzzy match")
            # Try matching by containment for minor whitespace/formatting differences
            for m_title in missing:
                m_norm = re.sub(r"\s+", " ", m_title).strip().lower()
                for resp_title, short in list(result.items()):
                    r_norm = re.sub(r"\s+", " ", resp_title).strip().lower()
                    if m_norm in r_norm or r_norm in m_norm:
                        result[m_title] = short
                        break

        return result if result else None

    except Exception as e:
        print(f"    Warning: LLM short-title generation failed: {e}")
        print("    Falling back to deterministic short titles")
        return None


def load_short_titles_cache(plan_dir: Path) -> dict | None:
    """Load cached short titles from placement/short_titles.json."""
    cache_path = plan_dir / "short_titles.json"
    if not cache_path.is_file():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_short_titles_cache(plan_dir: Path, cache: dict) -> None:
    """Save short titles cache to placement/short_titles.json."""
    cache_path = plan_dir / "short_titles.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    print(f"    Short titles cached to: {cache_path}")


def resolve_short_titles(
    conflicts: dict[str, list[str]], plan_dir: Path | None,
    style: StyleConfig | None = None,
) -> dict[str, str]:
    """Resolve short titles via cache, LLM, or deterministic fallback.

    Args:
        conflicts: {author_key: [full_title_1, full_title_2, ...]}
        plan_dir: Path to placement/ directory for caching, or None.
        style: Style configuration.

    Returns:
        {full_title: short_title} mapping for all conflict titles.
    """
    if not conflicts:
        return {}

    # 1. Check cache
    if plan_dir is not None:
        cache = load_short_titles_cache(plan_dir)
        if cache is not None:
            cache_valid = True
            for author, titles in conflicts.items():
                if author not in cache:
                    cache_valid = False
                    break
                cached_titles = set(cache[author].keys())
                if set(titles) != cached_titles:
                    cache_valid = False
                    break

            if cache_valid:
                print("    Using cached short titles from short_titles.json")
                result: dict[str, str] = {}
                for author, mapping in cache.items():
                    result.update(mapping)
                return result
            else:
                print("    Cache stale (conflicts changed), regenerating")

    # 2. Try LLM
    llm_result = generate_short_titles_llm(conflicts, style)
    if llm_result is not None:
        print(f"    LLM generated {len(llm_result)} short titles")

        # Save to cache
        if plan_dir is not None:
            cache_data: dict[str, dict[str, str]] = {}
            for author, titles in conflicts.items():
                cache_data[author] = {}
                for title in titles:
                    if title in llm_result:
                        cache_data[author][title] = llm_result[title]
            save_short_titles_cache(plan_dir, cache_data)

        return llm_result

    # 3. Deterministic fallback
    print("    Using deterministic short-title generation (fallback)")
    result = {}
    for author, titles in conflicts.items():
        for title in titles:
            result[title] = generate_short_title_deterministic(title)

    # Disambiguate collisions within each author
    for author, titles in conflicts.items():
        short_titles = [result[t] for t in titles]
        if len(short_titles) != len(set(short_titles)):
            # Collision -- extend to 5 words
            for title in titles:
                cleaned = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", title)
                cleaned = re.sub(r"[{}]", "", cleaned)
                main = re.split(
                    r"\s*[:\u2014\u2013]{1,2}\s*|---+|--+", cleaned
                )[0].strip()
                words = main.split()
                start = 0
                while start < len(words) and words[start].lower() in STOP_WORDS:
                    start += 1
                result[title] = " ".join(words[start : start + 5]).rstrip(".,;:")

    return result


# ── Footnote registry ────────────────────────────────────────────────


def _save_footnote_registry(
    plan_dir: Path,
    works: dict[str, "WorkInfo"],
    full_citation_texts: dict[str, str],
) -> None:
    """Save footnote_registry.json for standalone cross-reference reordering.

    The registry stores each unique work's full citation text and metadata so
    that reorder_crossrefs.py can reverse supra/Id. substitutions, re-parse
    footnotes with updated numbering, and re-apply short forms correctly.
    """
    registry: dict[str, object] = {"works": {}}
    for key, w in works.items():
        registry["works"][key] = {
            "author_key": w.author_key,
            "title": w.title,
            "title_cmd": w.title_cmd,
            "short_title": w.short_title or None,
            "needs_hereinafter": w.needs_hereinafter,
            "full_citation_text": full_citation_texts.get(key, ""),
        }

    plan_dir.mkdir(parents=True, exist_ok=True)
    reg_path = plan_dir / "footnote_registry.json"
    reg_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Footnote registry saved to: {reg_path}")


# ── Main processing ──────────────────────────────────────────────────


def process(input_path: str, output_path: str, plan_dir: str | None = None,
            style_id: str = "bluebook", skill_dir: str | None = None) -> None:
    global _style
    _style = load_style(style_id, skill_dir)

    tex = Path(input_path).read_text(encoding="utf-8")

    # Resolve plan directory for caching
    plan_dir_path: Path | None = None
    if plan_dir:
        plan_dir_path = Path(plan_dir)
    else:
        candidate = Path(output_path).parent / "placement"
        if candidate.is_dir():
            plan_dir_path = candidate

    sf = _style.short_forms
    ibid_term = sf.get("ibid_term")
    use_hereinafter = sf.get("use_hereinafter", True)

    print(f"Phase 6: Short-form substitution (style: {_style.style_id})")

    # ── Pass 1: Parse and index ──
    footnotes = extract_footnotes(tex)
    print(f"  Total footnotes: {len(footnotes)}")

    for fn in footnotes:
        parse_footnote_citations(fn, _style)

    # Build work registry
    works: dict[str, WorkInfo] = {}
    full_citation_texts: dict[str, str] = {}
    total_citations = 0

    for fn in footnotes:
        if fn.skip:
            continue
        for cite in fn.citations:
            if cite.is_short_form:
                continue
            total_citations += 1
            key = cite.identity_key
            if key not in works:
                works[key] = WorkInfo(
                    identity_key=key,
                    author_key=cite.author_key,
                    title=cite.title,
                    title_cmd=cite.title_cmd,
                    first_fn=fn.number,
                    year=cite.year,
                )
                full_citation_texts[key] = cite.raw

    print(f"  Citations processed: {total_citations}")

    # ── Pass 2: Detect same-author conflicts ──
    by_author: dict[str, list[str]] = {}
    for key, w in works.items():
        by_author.setdefault(w.author_key, []).append(key)

    hereinafter_count = 0
    authors_with_multiple = 0

    conflicts: dict[str, list[str]] = {}
    conflict_works: list[WorkInfo] = []

    # For Chicago/APA: always generate short titles (used in lieu of supra)
    # For Bluebook/McGill: only when same author has multiple works
    always_short_title = not use_hereinafter and ibid_term != "\\textit{Id.}"

    for author, keys in by_author.items():
        if len(keys) > 1 or always_short_title:
            if len(keys) > 1:
                authors_with_multiple += 1
            author_titles: list[str] = []
            for key in keys:
                w = works[key]
                if use_hereinafter and len(keys) > 1:
                    w.needs_hereinafter = True
                    hereinafter_count += 1
                elif always_short_title:
                    w.short_title = generate_short_title_deterministic(w.title)
                conflict_works.append(w)
                author_titles.append(w.title)
            if len(keys) > 1:
                conflicts[author] = author_titles

    short_title_map = resolve_short_titles(conflicts, plan_dir_path, _style)

    # Apply resolved short titles to WorkInfo objects
    flagged: list[str] = []
    for w in conflict_works:
        if w.title in short_title_map:
            w.short_title = short_title_map[w.title]
        else:
            w.short_title = generate_short_title_deterministic(w.title)
            flagged.append(
                f"  Warning: no LLM short title for '{w.title[:60]}...', "
                f"using fallback: '{w.short_title}'"
            )

    # Check for collisions within each author
    for author, keys in by_author.items():
        if len(keys) <= 1:
            continue
        author_works = [works[k] for k in keys]
        titles = [w.short_title for w in author_works]
        if len(titles) != len(set(titles)):
            flagged.append(
                f"  {author}: SHORT TITLE COLLISION: "
                + " vs ".join(f'"{t}"' for t in titles)
            )

    # ── Pass 2b: Insert hereinafter into first occurrences ──
    modifications: list[tuple[int, int, str]] = []
    hereinafter_tmpl = sf.get("hereinafter_template")

    if use_hereinafter and hereinafter_tmpl:
        for w in works.values():
            if not w.needs_hereinafter:
                continue

            fn = next((f for f in footnotes if f.number == w.first_fn), None)
            if fn is None:
                continue

            fn_content = tex[fn.start : fn.end]

            search_str = w.title[:40]
            escaped = re.escape(search_str)
            escaped = re.sub(r"\\ ", r"\\s+", escaped)
            title_match = re.search(escaped, fn_content)
            if title_match is None:
                continue

            after_title = fn_content[title_match.end() :]

            depth = 0
            cite_end = len(after_title)
            for i, ch in enumerate(after_title):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                elif ch == ";" and depth == 0:
                    cite_end = i
                    break

            cite_region = after_title[:cite_end]

            hereinafter_text = " " + hereinafter_tmpl.format(
                short_title=w.short_title, author=w.author_key,
            )

            last_paren_period = cite_region.rfind(").")
            if last_paren_period >= 0:
                insert_pos = fn.start + title_match.end() + last_paren_period + 1
                modifications.append((insert_pos, insert_pos, hereinafter_text))
            else:
                last_period = cite_region.rfind(".")
                if last_period >= 0:
                    insert_pos = fn.start + title_match.end() + last_period
                    modifications.append((insert_pos, insert_pos, hereinafter_text))

    modifications.sort(key=lambda x: x[0], reverse=True)
    for start, end, replacement in modifications:
        tex = tex[:start] + replacement + tex[end:]

    # ── Re-parse footnotes after hereinafter insertions ──
    footnotes = extract_footnotes(tex)
    for fn in footnotes:
        parse_footnote_citations(fn, _style)

    # ── Pass 3: Substitute short forms ──
    ibid_require_sole = sf.get("ibid_require_sole_citation", True)
    ibid_require_prev = sf.get("ibid_require_immediately_preceding", True)
    supra_tmpl = sf.get("supra_template", "{signal}{author}, \\textit{{supra}} note {n}")
    supra_short_tmpl = sf.get(
        "supra_with_short_title_template",
        "{signal}{author}, \\textit{{{short_title}}}, \\textit{{supra}} note {n}",
    )
    end_punct = _style.merge.get("end_punctuation", ".")
    sep = _style.merge.get("separator", "; ")

    id_count = 0
    supra_count = 0
    already_short = 0
    full_retained = 0

    seen: dict[str, int] = {}
    prev_fn_citations: list[Citation] = []

    subs: list[tuple[int, int, str]] = []

    for fn in footnotes:
        if fn.skip or not fn.citations:
            prev_fn_citations = []
            continue

        new_parts: list[str] = []
        any_change = False

        for cite in fn.citations:
            if cite.is_short_form:
                already_short += 1
                new_parts.append(cite.raw)
                continue

            key = cite.identity_key

            if key not in seen:
                seen[key] = fn.number
                full_retained += 1
                new_parts.append(cite.raw)
                continue

            first_fn = seen[key]
            w = works.get(key)

            # Ibid conditions (style-configurable)
            use_ibid = ibid_term is not None and ibid_require_prev and (
                len(prev_fn_citations) == 1
                and not prev_fn_citations[0].is_short_form
                and prev_fn_citations[0].identity_key == key
                and (not ibid_require_sole or len(fn.citations) == 1)
            )

            if use_ibid:
                new_parts.append(ibid_term)
                id_count += 1
                any_change = True
            else:
                author_for_supra = cite.author_key
                signal_prefix = f"{cite.signal} " if cite.signal else ""

                if w and (w.needs_hereinafter or w.short_title):
                    supra_text = supra_short_tmpl.format(
                        signal=signal_prefix,
                        author=author_for_supra,
                        short_title=w.short_title,
                        n=first_fn,
                        year=w.year,
                    )
                else:
                    supra_text = supra_tmpl.format(
                        signal=signal_prefix,
                        author=author_for_supra,
                        n=first_fn,
                        year=w.year if w else "",
                    )

                new_parts.append(supra_text)
                supra_count += 1
                any_change = True

        if any_change:
            new_content = sep.join(
                lowercase_signal_after_first(new_parts, _style)
            )
            if end_punct:
                stripped_for_check = new_content.rstrip().rstrip("}").rstrip()
                if not stripped_for_check.endswith(end_punct):
                    new_content = new_content.rstrip() + end_punct
                else:
                    new_content = new_content.rstrip()
            else:
                new_content = new_content.rstrip()
            marker_prefix = f"{MARKER}\n" if fn.has_marker else ""
            new_fn = f"\\footnote{{{marker_prefix}{new_content}}}"
            subs.append((fn.start, fn.end, new_fn))
        else:
            full_retained += sum(
                1 for c in fn.citations if not c.is_short_form and c.identity_key in seen
            ) - sum(1 for c in fn.citations if not c.is_short_form and c.identity_key not in seen)

        prev_fn_citations = fn.citations

    # Apply substitutions in reverse order
    subs.sort(key=lambda x: x[0], reverse=True)
    for start, end, replacement in subs:
        tex = tex[:start] + replacement + tex[end:]

    # Write output
    Path(output_path).write_text(tex, encoding="utf-8")

    # Save footnote registry for standalone cross-reference reordering
    _save_footnote_registry(
        plan_dir_path or Path(output_path).parent / "placement",
        works, full_citation_texts,
    )

    # Report
    print(f"  Id. substitutions: {id_count}")
    print(f"  Supra substitutions: {supra_count}")
    print(
        f"  Hereinafter insertions: {hereinafter_count}"
        f" ({authors_with_multiple} authors with multiple works)"
    )
    print(f"  Already short-form: {already_short}")
    print(f"  Full citations retained: {full_retained}")

    if flagged:
        print("  [!] Review suggested:")
        for f in flagged:
            print(f"    - {f}")


def main():
    parser = argparse.ArgumentParser(
        description="Short-form post-processing (Id./ibid/supra/hereinafter)"
    )
    parser.add_argument("--input", required=True, help="Input .tex file")
    parser.add_argument(
        "--output",
        required=True,
        help="Output .tex file (can be same as input for in-place)",
    )
    parser.add_argument(
        "--plan-dir",
        default=None,
        help="Path to placement/ directory for caching short titles "
        "(default: placement/ alongside output .tex)",
    )
    parser.add_argument(
        "--style",
        default="bluebook",
        choices=["bluebook", "oscola", "chicago", "apa", "mcgill"],
        help="Citation style (default: bluebook)",
    )
    parser.add_argument(
        "--skill-dir",
        default=None,
        help="Path to cite-placement skill directory",
    )
    args = parser.parse_args()

    if not Path(args.input).is_file():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    process(args.input, args.output, args.plan_dir, args.style, args.skill_dir)


if __name__ == "__main__":
    main()
