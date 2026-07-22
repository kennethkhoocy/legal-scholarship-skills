"""Tests for docling_extract.py footnote reconstruction.

The Docling conversion itself is not exercised here (it needs the docling
package and is slow); the pure reconstruction logic — footnote parsing, marker
linking, and definition rendering — is tested with a lightweight fake document.
"""

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import docling_extract as dx


# --- fake Docling document ----------------------------------------------------

class FakeItem:
    def __init__(self, label, text=""):
        self.label = label  # str(...).lower() in the code yields this
        self.text = text


class FakeDoc:
    def __init__(self, items):
        # items: list of (FakeItem, level)
        self._items = items

    def iterate_items(self):
        return iter(self._items)


def doc_from(*pairs):
    return FakeDoc([(FakeItem(lbl, txt), lvl) for lbl, txt, lvl in pairs])


# --- marker linking -----------------------------------------------------------

def test_link_markers_sequential_inlines_text():
    body = "The IPO documents. 1 After the case settled in 2018. 2 As shown."
    out, linked = dx.link_markers(body, [("1", "first note"), ("2", "second note")])
    assert linked == [1, 2]
    assert "documents.^[first note]" in out
    assert "2018.^[second note]" in out


def test_link_markers_excludes_section_reference():
    body = "See Section 2 for details. The result holds. 1 Thus we conclude."
    out, linked = dx.link_markers(body, [("1", "x")])
    assert linked == [1]
    assert "Section 2 for" in out          # section reference untouched
    assert "holds.^[x]" in out


def test_link_markers_excludes_year_and_quantity():
    body = "Raised $ 38 million in 2018. The firm grew. 1 It then expanded."
    out, linked = dx.link_markers(body, [("1", "x")])
    assert "in 2018." in out and "$ 38 million" in out  # untouched
    assert "grew.^[x]" in out


def test_link_markers_after_quote():
    body = 'the rulers." 5 The court then ruled.'
    out, linked = dx.link_markers(body, [("5", "x")])
    assert linked == [5]
    assert 'rulers."^[x]' in out


def test_link_markers_escapes_brackets_in_inline_note():
    body = "the law. 1 Then the rule."
    out, _ = dx.link_markers(body, [("1", "See [Civil Code] art. 9")])
    assert "law.^[See \\[Civil Code\\] art. 9]" in out


def test_link_markers_reports_unlinked():
    body = "Only one marker here. 1 And nothing for two."
    out, linked = dx.link_markers(body, [("1", "a"), ("2", "b")])
    assert linked == [1]


def test_marker_context_not_rejected_by_month_substring():
    """Cause-2 regression: 'decade'/'doctrine' contain month substrings (dec/oct)
    but must NOT cause a following marker to be rejected as a date."""
    for body in ["the following decade. 30 With regard", "Party doctrine. 65 But you"]:
        s = body
        n = "30" if "30" in s else "65"
        i = s.index(n)
        assert dx._is_marker_context(s, i, i + 2) is True


def test_marker_context_still_rejects_real_dates():
    s = "filed on October 7, 2021 in the court"
    i = s.index("7")
    assert dx._is_marker_context(s, i, i + 1) is False


def test_link_markers_recovers_out_of_order_marker():
    """Cause-3: a valid marker appearing out of reading order (12 after 13) is
    recovered by the second pass instead of being skipped."""
    body = "First the analysis. 13 Then it follows. 12 Finally the end."
    out, linked = dx.link_markers(body, [("12", "twelve"), ("13", "thirteen")])
    assert set(linked) == {12, 13}
    assert "analysis.^[thirteen]" in out
    assert "follows.^[twelve]" in out


# --- footnote parsing (collect) ----------------------------------------------

def test_collect_parses_number_space_footnotes():
    doc = doc_from(
        ("text", "Body paragraph one.", 1),
        ("footnote", "1 See Atkins (2018).", 1),
    )
    body, fns = dx.collect(doc)
    assert ("1", "See Atkins (2018).") in fns
    assert body == ["Body paragraph one."]


def test_collect_parses_number_dot_footnotes_law_style():
    doc = doc_from(("footnote", "3. translation available at the university.", 1))
    _, fns = dx.collect(doc)
    assert fns == [("3", "translation available at the university.")]


def test_collect_parses_star_acknowledgment():
    doc = doc_from(("footnote", "∗ We thank the editor.", 1))
    _, fns = dx.collect(doc)
    assert fns[0][0] in ("∗", "*")


def test_collect_merges_split_footnote_continuation():
    """A numberless footnote fragment is merged into the note it continues."""
    doc = doc_from(
        ("footnote", "5 See, e.g., Owen Fiss, Against Settlement,", 1),
        ("footnote", "93 YALE L.J. 1073 (1984).", 1),  # continuation, no leading marker word
    )
    _, fns = dx.collect(doc)
    assert len(fns) == 1
    assert fns[0][0] == "5"
    assert "Owen Fiss" in fns[0][1] and "1073 (1984)." in fns[0][1]


def test_collect_skips_headers_and_footers():
    doc = doc_from(
        ("page_header", "Journal of Things", 1),
        ("page_footer", "42", 1),
        ("text", "Real body.", 1),
    )
    body, _ = dx.collect(doc)
    assert body == ["Real body."]


def test_collect_renders_formula_as_display_math():
    doc = doc_from(("formula", r"\alpha = \beta", 1))
    body, _ = dx.collect(doc)
    assert body == ["$$\n\\alpha = \\beta\n$$"]


def test_collect_heading_levels():
    doc = doc_from(("section_header", "Introduction", 1))
    body, _ = dx.collect(doc)
    assert body == ["## Introduction"]


# --- definition rendering & end to end ---------------------------------------

def test_build_markdown_end_to_end_inline_footnotes():
    doc = doc_from(
        ("section_header", "Intro", 1),
        ("text", "The firm disclosed everything. 1 Investors were happy. 2 The end.", 1),
        ("footnote", "1 First note.", 1),
        ("footnote", "2 Second note.", 1),
    )
    md, report = dx.build_markdown(doc, image_mode="none")
    assert report["footnotes"] == 2
    assert report["markers_linked"] == 2
    assert report["unlinked"] == []
    # Footnotes are inlined at their reference point, not collected at the end.
    assert "everything.^[First note.]" in md
    assert "happy.^[Second note.]" in md
    assert "## Notes" not in md
    assert "[^1]:" not in md


class FakePicture:
    label = "picture"
    text = ""

    def __init__(self, img=None, cap=""):
        self._img = img
        self._cap = cap

    def get_image(self, doc):
        return self._img

    def caption_text(self, doc):
        return self._cap


def test_picture_embedded_as_base64_inside_markdown():
    from PIL import Image
    img = Image.new("RGB", (4, 4), (10, 200, 30))
    doc = FakeDoc([(FakePicture(img, "Figure 1: Phase diagram"), 1)])
    body, _ = dx.collect(doc, image_mode="embedded")
    assert body[0].startswith("![figure 1](data:image/png;base64,")
    assert "Figure 1: Phase diagram" in body[0]


def test_picture_none_mode_is_placeholder():
    doc = FakeDoc([(FakePicture(None), 1)])
    body, _ = dx.collect(doc, image_mode="none")
    assert body == ["<!-- figure -->"]


def test_picture_external_mode_writes_file_and_references_it(tmp_path):
    from PIL import Image
    img = Image.new("RGB", (4, 4), (1, 2, 3))
    doc = FakeDoc([(FakePicture(img), 1)])
    images_dir = tmp_path / "doc_images"
    body, _ = dx.collect(doc, image_mode="external", images_dir=images_dir)
    assert (images_dir / "figure_1.png").exists()
    assert "![figure 1](doc_images/figure_1.png)" in body[0]


def test_render_endnotes_preserves_original_number():
    out = dx.render_endnotes([("23", "absorbed note"), ("31", "another one")])
    assert out.startswith("## Endnotes")
    assert "**[23]** absorbed note" in out
    assert "**[31]** another one" in out


def test_build_markdown_routes_unlinked_to_endnotes():
    """A footnote whose marker is absent from the body goes to Endnotes; a linked
    one is inlined at its reference point."""
    doc = doc_from(
        ("text", "Body referencing one. 1 But the other is unmarked here.", 1),
        ("footnote", "1 Linked note.", 1),
        ("footnote", "2 Orphan note with no marker in text.", 1),
    )
    md, report = dx.build_markdown(doc, image_mode="none")
    assert report["markers_linked"] == 1
    assert report["endnotes"] == 1
    # Linked one is inlined at its reference.
    assert "one.^[Linked note.]" in md
    # Orphan one is an endnote, preserved by number (pandoc keeps it).
    assert "## Endnotes" in md
    assert "**[2]** Orphan note with no marker in text." in md
    assert "[^2]:" not in md  # not a droppable footnote def


def test_build_markdown_no_footnotes_no_notes_section():
    doc = doc_from(("text", "Plain body, no footnotes.", 1))
    md, report = dx.build_markdown(doc)
    assert report["footnotes"] == 0
    assert "## Notes" not in md
    assert md.strip() == "Plain body, no footnotes."


# --- Audit fix #1: first numeric footnote bootstraps the sequence -------------

def test_collect_bootstraps_first_numeric_footnote_above_20():
    """A page-range extraction starting mid-document gives a first footnote
    numbered far above 20; its label must still be captured, not emptied. Before
    the fix, last_num==0 rejected n>20, so the whole range degraded to ("", …)."""
    doc = doc_from(
        ("text", "Body that references something. 23 And it continues.", 1),
        ("footnote", "23 First note on this page.", 1),
        ("footnote", "24 Second note here.", 1),
    )
    _, fns = dx.collect(doc)
    assert ("23", "First note on this page.") in fns
    assert ("24", "Second note here.") in fns


# --- Audit fix #2: "§ 12" statute reference is not a marker -------------------

def test_marker_context_rejects_section_symbol_reference():
    s = "as provided in § 12 of the Act"
    i = s.index("12")
    assert dx._is_marker_context(s, i, i + 2) is False


def test_marker_context_still_links_after_sentence_end():
    """Regression guard that the §-branch split didn't break ordinary markers."""
    s = "the firms settled the dispute. 12 The court agreed."
    i = s.index("12")
    assert dx._is_marker_context(s, i, i + 2) is True


# --- Audit fix #3: numbered-list openers are not markers ----------------------

def test_marker_context_rejects_numbered_list_opener():
    s = "Intro paragraph.\n1. First list item here.\nMore text."
    i = s.index("1. First")
    assert dx._is_marker_context(s, i, i + 1) is False


def test_marker_context_keeps_marker_later_on_list_line():
    """A genuine marker further along a list line is still accepted (lead is
    non-empty there, so the list-opener guard does not fire)."""
    s = "Intro.\n1. The firm disclosed. 5 Then more follows."
    i = s.index("5 Then")
    assert dx._is_marker_context(s, i, i + 1) is True


# --- Audit fix #4: all symbol notes inline; labels preserved in endnotes ------

def test_inline_symbol_notes_inlines_dagger():
    body = "Written by Jane Doe† at the institute."
    out, idx = dx._inline_symbol_notes(body, [("†", "Corresponding author.")])
    assert idx == {0}
    assert "Doe^[Corresponding author.] at the institute." in out


def test_inline_symbol_notes_skips_markdown_bullet():
    body = "Heading\n\n* bullet one\n* bullet two"
    out, idx = dx._inline_symbol_notes(body, [("*", "Should not attach to a bullet.")])
    assert idx == set()
    assert "^[" not in out


def test_inline_symbol_notes_skips_bold_delimiters():
    body = "This is **bold** and nothing else."
    out, idx = dx._inline_symbol_notes(body, [("*", "ack")])
    assert idx == set()
    assert "^[" not in out


def test_build_markdown_inlines_dagger_symbol_note():
    doc = doc_from(
        ("text", "Written by Jane Doe† at the institute.", 1),
        ("footnote", "† Corresponding author: jane@x.edu", 1),
    )
    md, report = dx.build_markdown(doc, image_mode="none")
    assert report["has_ack"] is True
    assert "Doe^[Corresponding author: jane@x.edu]" in md
    assert "## Endnotes" not in md  # inlined, not orphaned


def test_build_markdown_routes_starless_symbol_note_to_endnotes_with_label():
    doc = doc_from(
        ("text", "Body with no symbol markers at all.", 1),
        ("footnote", "‡ Data appendix available online.", 1),
    )
    md, _ = dx.build_markdown(doc, image_mode="none")
    assert "## Endnotes" in md
    assert "**[‡]** Data appendix available online." in md  # label preserved, not [note]


def test_render_endnotes_preserves_symbol_label():
    out = dx.render_endnotes([("†", "dagger note"), ("23", "numeric note")])
    assert "**[†]** dagger note" in out
    assert "**[23]** numeric note" in out


# --- Re-audit fixes: star emphasis, blank label, citation-continuation --------

def test_inline_symbol_notes_skips_closing_italic_star():
    """The closing '*' of '*italic*' must not be consumed as an ack marker."""
    body = "This sentence has *italic* emphasis and no real marker."
    out, idx = dx._inline_symbol_notes(body, [("*", "ack")])
    assert idx == set()
    assert "^[" not in out


def test_inline_symbol_notes_blank_label_not_inlined():
    """A blank-label note has no symbol to find ('' in '*∗' is a Python trap);
    it must not attach to an italic star — it belongs in the endnotes."""
    body = "A title with an italic *word* in it."
    out, idx = dx._inline_symbol_notes(body, [("", "Unlabeled fragment.")])
    assert idx == set()
    assert "^[" not in out


def test_symbol_variants_blank_label_returns_empty():
    assert dx._symbol_variants("") == []
    assert dx._symbol_variants("   ") == []
    assert dx._symbol_variants("*") == ["∗", "*"]
    assert dx._symbol_variants("∗") == ["∗", "*"]
    assert dx._symbol_variants("†") == ["†"]


def test_inline_symbol_notes_inlines_section_sign_author_marker():
    body = "Written by Jane Doe§ of the faculty."
    out, idx = dx._inline_symbol_notes(body, [("§", "Affiliation note.")])
    assert idx == {0}
    assert "Doe^[Affiliation note.] of the faculty." in out


def test_inline_symbol_notes_section_sign_skips_statute_reference():
    body = "The rule in § 12 governs; see also the surrounding text."
    out, idx = dx._inline_symbol_notes(body, [("§", "A real section note.")])
    assert idx == set()  # the only § is a statute ref → not inlined (→ endnote)
    assert "^[" not in out


def test_collect_first_citation_continuation_not_phantom():
    """A page range starting mid-note: the first FOOTNOTE item is a citation
    continuation. It must NOT be invented as a phantom numeric footnote, and the
    next item (the real first note) is captured normally."""
    doc = doc_from(
        ("text", "Body text on this page.", 1),
        ("footnote", "93 YALE L.J. 1073 (1984).", 1),
        ("footnote", "210 The first real note on this page.", 1),
    )
    _, fns = dx.collect(doc)
    labels = [l for l, _ in fns]
    assert "93" not in labels
    assert ("210", "The first real note on this page.") in fns


def test_collect_bootstrap_keeps_prose_first_note_above_20():
    """A genuine first note numbered above 20 whose text is ordinary prose still
    bootstraps (the citation-continuation guard must not over-reject)."""
    doc = doc_from(("footnote", "37 The court rejected this argument.", 1))
    _, fns = dx.collect(doc)
    assert fns == [("37", "The court rejected this argument.")]


def test_collect_legal_first_note_openers_not_demoted():
    """First notes opening with common legal abbreviations/acronyms (SEC, Id.,
    Cf.) are real footnotes, not citation continuations — the narrowed guard,
    which requires a <volume> <reporter> <page> shape, must let them bootstrap."""
    for text, num in [
        ("1 SEC v. Chenery Corp., 318 U.S. 80 (1943).", "1"),
        ("37 Id. at 200.", "37"),
        ("37 Cf. Smith v. Jones, 5 F.3d 10 (1993).", "37"),
    ]:
        doc = doc_from(("footnote", text, 1))
        _, fns = dx.collect(doc)
        assert fns and fns[0][0] == num, f"{text!r} → {fns}"


def test_collect_demotes_bare_reporter_citation_continuation():
    """A page range opening on a bare reporter citation tail ('318 U.S. 80 …')
    is still recognized as a continuation and not minted as a phantom note."""
    doc = doc_from(("footnote", "318 U.S. 80 (1943). The holding was narrow.", 1))
    _, fns = dx.collect(doc)
    assert "318" not in [l for l, _ in fns]


# --- Coverage gaps flagged by the re-audit ------------------------------------

def test_marker_context_rejects_abbreviation_references():
    for s, d in [("see p. 5 above", "5"), ("in fig. 3 below", "3"), ("table no. 7 shows", "7")]:
        i = s.index(d)
        assert dx._is_marker_context(s, i, i + 1) is False


def test_marker_context_rejects_section_sign_no_space():
    s = "violations of §12 of the statute"
    i = s.index("12")
    assert dx._is_marker_context(s, i, i + 2) is False
