"""Three-sub-mode comment author: reply, new, resolve.

Each sub-mode unpacks the input .docx (via Anthropic office/unpack.py),
modifies the unpacked tree in Python, then repacks (via Anthropic
office/pack.py). The LLM never sees raw XML.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from models import AddCommentSpec


def _escape_comment_body(text: str | None) -> str:
    """Escape &, <, > for safe interpolation into XML text content.

    Anthropic's comment.py interpolates the comment body verbatim into a
    string that is later parsed by defusedxml.minidom; an unescaped & or
    < raises ``ExpatError``. Other characters (smart quotes, apostrophes,
    arbitrary Unicode) are valid in XML text content and pass through
    unchanged.
    """
    if text is None:
        return ""
    return _xml_escape(text)


def add_comment(input_path: Path, out_path: Path, spec: AddCommentSpec) -> int:
    spec.validate_mode()
    if spec.mode == "reply":
        return _do_reply(input_path, out_path, spec)
    if spec.mode == "new":
        return _do_new(input_path, out_path, spec)
    if spec.mode == "resolve":
        return _do_resolve(input_path, out_path, spec)
    raise AssertionError(f"unreachable mode: {spec.mode}")


def _do_reply(input_path: Path, out_path: Path, spec: AddCommentSpec) -> int:
    """Append a new comment as a child of an existing one.

    1) Unpack the source.
    2) Map C-id -> parent w:id via extract_comments.
    3) Call Anthropic's comment.py with --parent <parent_w_id> against the unpacked tree.
    4) Insert nested range markers + reference run in document.xml.
    5) Repack.
    """
    from anthropic_bridge import run_anthropic
    from commands.pack import run as pack_run
    from commands.unpack import run as unpack_run
    from extract_comments import extract_comments

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        unpacked = tmp_dir / "unpacked"
        code = unpack_run(input_path, unpacked, merge_runs=True)
        if code != 0:
            return code

        # Map C-id -> parent w:id
        comments, _ = extract_comments(input_path)
        parent_w_id = None
        for c in comments:
            if c.comment_id == spec.reply_to:
                parent_w_id = c.ooxml_id
                break
        if parent_w_id is None:
            print(f"Comment {spec.reply_to} not found in {input_path}", file=sys.stderr)
            return 1

        # Allocate the new comment's w:id
        from lxml import etree
        comments_xml = unpacked / "word" / "comments.xml"
        max_id = -1
        if comments_xml.is_file():
            tree = etree.parse(str(comments_xml))
            w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            for c in tree.getroot().findall(f"{{{w_ns}}}comment"):
                wid = c.get(f"{{{w_ns}}}id")
                if wid is not None:
                    try:
                        max_id = max(max_id, int(wid))
                    except ValueError:
                        pass
        new_id = str(max_id + 1)

        # Ensure comments.xml has the namespace declarations that comment.py needs
        # (w14 for paraId, w15 for commentsEx, etc.) so that defusedxml.minidom
        # can parse it without "unbound prefix" errors.  Pass commentsExtended.xml
        # so that existing paraId values are preserved rather than overwritten with
        # random ones (Fix 2: reply threading must preserve existing paraIds).
        _ensure_comment_xml_namespaces(comments_xml, unpacked / "word" / "commentsExtended.xml")

        # Ensure all four comment-related relationships and content-type entries
        # exist in the unpacked tree.  Anthropic's comment.py skips this when
        # comments.xml is already present, so we must handle it ourselves.
        _ensure_all_comment_relationships(unpacked)

        # Call Anthropic's comment.py with --parent.
        # The body text must be XML-escaped because comment.py interpolates
        # it directly into a string later parsed as XML (codex audit issue 2).
        result = run_anthropic(
            "comment.py",
            str(unpacked),
            new_id,
            _escape_comment_body(spec.text),
            "--parent",
            parent_w_id,
            "--author",
            spec.author,
            check=False,
        )
        if result.returncode != 0:
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return result.returncode

        # Insert nested range markers in document.xml.
        _insert_nested_reply_markers(unpacked / "word" / "document.xml", parent_w_id, new_id)

        # Word 2016+ needs durable ids for every comment (parents + reply) for
        # threaded display.  Anthropic's comment.py only adds a row for the
        # new comment; backfill rows for any pre-existing parent comments
        # that are still missing durable ids.
        _backfill_durable_ids(unpacked)

        # Word's modern review pane keys author display on word/people.xml.
        # Create it (or extend it) so every comment author — including the
        # reply's author — is represented.
        _create_people_xml(unpacked)

        return pack_run(unpacked, out_path, original=input_path, validate=True)


def _ensure_all_comment_relationships(unpacked: Path) -> None:
    """Ensure all four comment-related .rels entries and [Content_Types].xml overrides exist.

    Anthropic's comment.py calls _ensure_comment_relationships only when
    comments.xml does NOT yet exist in the unpacked tree.  If comments.xml is
    already present (existing document), that helper returns early, and any
    newly created companion files (commentsIds.xml, commentsExtensible.xml) will
    have no relationship entry, causing the pack validator to reject them.

    This function adds the missing relationships and content-type overrides
    unconditionally, so the tree is always complete before repacking.
    """
    from lxml import etree

    rels_path = unpacked / "word" / "_rels" / "document.xml.rels"
    ct_path = unpacked / "[Content_Types].xml"
    RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

    COMMENT_RELS = [
        (
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
            "comments.xml",
            "/word/comments.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml",
        ),
        (
            "http://schemas.microsoft.com/office/2011/relationships/commentsExtended",
            "commentsExtended.xml",
            "/word/commentsExtended.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml",
        ),
        (
            "http://schemas.microsoft.com/office/2016/09/relationships/commentsIds",
            "commentsIds.xml",
            "/word/commentsIds.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsIds+xml",
        ),
        (
            "http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible",
            "commentsExtensible.xml",
            "/word/commentsExtensible.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtensible+xml",
        ),
        (
            "http://schemas.microsoft.com/office/2011/relationships/people",
            "people.xml",
            "/word/people.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.people+xml",
        ),
    ]

    # --- relationships ---
    if rels_path.is_file():
        rels_tree = etree.parse(str(rels_path))
        rels_root = rels_tree.getroot()
        existing_targets = {
            el.get("Target")
            for el in rels_root.findall(f"{{{RELS_NS}}}Relationship")
        }
        max_rid = 0
        for el in rels_root.findall(f"{{{RELS_NS}}}Relationship"):
            rid = el.get("Id", "")
            if rid.startswith("rId"):
                try:
                    max_rid = max(max_rid, int(rid[3:]))
                except ValueError:
                    pass
        changed = False
        for rel_type, target, _pt, _ct in COMMENT_RELS:
            if target not in existing_targets:
                rel = etree.SubElement(rels_root, f"{{{RELS_NS}}}Relationship")
                max_rid += 1
                rel.set("Id", f"rId{max_rid}")
                rel.set("Type", rel_type)
                rel.set("Target", target)
                changed = True
        if changed:
            rels_tree.write(str(rels_path), xml_declaration=True, encoding="UTF-8", standalone=True)

    # --- [Content_Types].xml ---
    CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
    if ct_path.is_file():
        ct_tree = etree.parse(str(ct_path))
        ct_root = ct_tree.getroot()
        existing_parts = {
            el.get("PartName")
            for el in ct_root.findall(f"{{{CT_NS}}}Override")
        }
        changed = False
        for _rt, _tgt, part_name, content_type in COMMENT_RELS:
            if part_name not in existing_parts:
                override = etree.SubElement(ct_root, f"{{{CT_NS}}}Override")
                override.set("PartName", part_name)
                override.set("ContentType", content_type)
                changed = True
        if changed:
            ct_tree.write(str(ct_path), xml_declaration=True, encoding="UTF-8", standalone=True)


def _ensure_comment_xml_namespaces(comments_xml: Path, ext_xml: Path | None = None) -> None:
    """Add missing namespace declarations and w14:paraId attributes to comments.xml.

    Anthropic's comment.py uses defusedxml.minidom to parse comments.xml and
    relies on w14:paraId attributes being present on the <w:p> element inside
    each <w:comment> in order to establish parent-child thread linkage.  Our
    unpack step produces minimal XML without these attributes.  This function:

    1. Adds the w14/w15/w16cid/w16cex namespace declarations to the root
       element so that minidom does not raise "unbound prefix" errors.
    2. For each <w:p> inside a <w:comment> that lacks w14:paraId, copies the
       corresponding paraId from commentsExtended.xml (if available and mapped)
       so that existing paraIdParent references in commentsExtended.xml remain
       valid; otherwise generates a fresh random paraId.

    The ext_xml parameter is the path to word/commentsExtended.xml.  Pass it
    when commentsExtended.xml is already present so that existing threading
    linkage is preserved (Fix 2).
    """
    if not comments_xml.is_file():
        return
    import random
    from lxml import etree

    EXTRA_NS = {
        "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
        "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
        "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
        "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    }
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
    W15 = "http://schemas.microsoft.com/office/word/2012/wordml"

    # Build w:id -> existing paraId map from commentsExtended.xml if available.
    # The n-th <w15:commentEx> corresponds to the n-th <w:comment> in comments.xml.
    existing_para_ids: dict[str, str] = {}
    if ext_xml is not None and ext_xml.is_file():
        try:
            ext_tree = etree.parse(str(ext_xml))
            ext_entries = ext_tree.getroot().findall(f"{{{W15}}}commentEx")
            c_root_for_map = etree.parse(str(comments_xml)).getroot()
            c_comments_for_map = c_root_for_map.findall(f"{{{W}}}comment")
            for c_el, ex_el in zip(c_comments_for_map, ext_entries):
                wid = c_el.get(f"{{{W}}}id")
                para_id = ex_el.get(f"{{{W15}}}paraId")
                if wid is not None and para_id:
                    existing_para_ids[wid] = para_id
        except Exception:
            pass  # If commentsExtended.xml is malformed, fall back to fresh ids

    tree = etree.parse(str(comments_xml))
    root = tree.getroot()

    # Rebuild the root element with the merged nsmap if any prefixes are missing.
    current_nsmap = dict(root.nsmap)
    missing = {k: v for k, v in EXTRA_NS.items() if k not in current_nsmap}
    if missing:
        merged_nsmap = {**current_nsmap, **missing}
        new_root = etree.Element(root.tag, nsmap=merged_nsmap)
        for k, v in root.attrib.items():
            new_root.set(k, v)
        for child in root:
            new_root.append(child)
        root = new_root

    # Ensure every <w:p> inside a <w:comment> has a w14:paraId attribute.
    for comment_el in root.findall(f"{{{W}}}comment"):
        wid = comment_el.get(f"{{{W}}}id")
        for p_el in comment_el.findall(f"{{{W}}}p"):
            if p_el.get(f"{{{W14}}}paraId") is None:
                if wid is not None and wid in existing_para_ids:
                    p_el.set(f"{{{W14}}}paraId", existing_para_ids[wid])
                else:
                    p_el.set(
                        f"{{{W14}}}paraId",
                        f"{random.randint(0, 0x7FFFFFFE):08X}",
                    )

    etree.ElementTree(root).write(
        str(comments_xml), xml_declaration=True, encoding="UTF-8", standalone=True
    )


def _backfill_durable_ids(unpacked: Path) -> None:
    """Backfill commentsIds.xml and commentsExtensible.xml so every comment has a durable id.

    Anthropic's comment.py appends a w16cid:commentId / w16cex:commentExtensible
    row only for the new (reply) comment.  If commentsIds.xml or
    commentsExtensible.xml was just created from an empty template, the
    pre-existing parent comments end up with no durable-id rows at all.  Word
    2016+ keys threaded display off durable ids, so a parent that lacks one
    is treated as a legacy comment and a reply referencing it cannot be drawn
    as a thread in the modern review pane.

    This helper walks comments.xml, finds every <w:p> w14:paraId that is not
    yet covered by a commentsIds row, and appends a fresh durableId for it,
    plus a parallel commentExtensible row.  Idempotent: comments that already
    have rows are left alone.
    """
    import random
    from datetime import datetime, timezone

    from lxml import etree

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
    W16CID = "http://schemas.microsoft.com/office/word/2016/wordml/cid"
    W16CEX = "http://schemas.microsoft.com/office/word/2018/wordml/cex"

    comments_path = unpacked / "word" / "comments.xml"
    ids_path = unpacked / "word" / "commentsIds.xml"
    cex_path = unpacked / "word" / "commentsExtensible.xml"

    if not comments_path.is_file():
        return

    paraIds: list[str] = []
    comments_root = etree.parse(str(comments_path)).getroot()
    for c in comments_root.findall(f"{{{W}}}comment"):
        p = c.find(f"{{{W}}}p")
        if p is not None:
            pid = p.get(f"{{{W14}}}paraId")
            if pid:
                paraIds.append(pid)

    if not paraIds:
        return

    if ids_path.is_file():
        ids_tree = etree.parse(str(ids_path))
        ids_root = ids_tree.getroot()
    else:
        ids_root = etree.Element(
            f"{{{W16CID}}}commentsIds",
            nsmap={"w16cid": W16CID, "w": W},
        )
        ids_tree = etree.ElementTree(ids_root)

    if cex_path.is_file():
        cex_tree = etree.parse(str(cex_path))
        cex_root = cex_tree.getroot()
    else:
        cex_root = etree.Element(
            f"{{{W16CEX}}}commentsExtensible",
            nsmap={"w16cex": W16CEX, "w": W},
        )
        cex_tree = etree.ElementTree(cex_root)

    existing_ids_paraIds: dict[str, str] = {}
    for el in ids_root.findall(f"{{{W16CID}}}commentId"):
        pid = el.get(f"{{{W16CID}}}paraId")
        did = el.get(f"{{{W16CID}}}durableId")
        if pid and did:
            existing_ids_paraIds[pid] = did

    existing_cex_durables = {
        el.get(f"{{{W16CEX}}}durableId")
        for el in cex_root.findall(f"{{{W16CEX}}}commentExtensible")
    }

    used_durables = set(existing_ids_paraIds.values()) | existing_cex_durables

    def _fresh_durable() -> str:
        while True:
            d = f"{random.randint(0, 0x7FFFFFFE):08X}"
            if d not in used_durables:
                used_durables.add(d)
                return d

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    changed_ids = False
    changed_cex = False
    for pid in paraIds:
        if pid in existing_ids_paraIds:
            durable = existing_ids_paraIds[pid]
        else:
            durable = _fresh_durable()
            cid_el = etree.SubElement(ids_root, f"{{{W16CID}}}commentId")
            cid_el.set(f"{{{W16CID}}}paraId", pid)
            cid_el.set(f"{{{W16CID}}}durableId", durable)
            existing_ids_paraIds[pid] = durable
            changed_ids = True
        if durable not in existing_cex_durables:
            cex_el = etree.SubElement(cex_root, f"{{{W16CEX}}}commentExtensible")
            cex_el.set(f"{{{W16CEX}}}durableId", durable)
            cex_el.set(f"{{{W16CEX}}}dateUtc", ts)
            existing_cex_durables.add(durable)
            changed_cex = True

    if changed_ids:
        ids_tree.write(
            str(ids_path), xml_declaration=True, encoding="UTF-8", standalone=True,
        )
    if changed_cex:
        cex_tree.write(
            str(cex_path), xml_declaration=True, encoding="UTF-8", standalone=True,
        )


def _create_people_xml(unpacked: Path) -> None:
    """Create or update word/people.xml so every comment author has a w15:person row.

    Word's modern review pane keys author display and presence on
    word/people.xml.  Without it, threaded replies render under the
    generic "Author" label, breaking the visual thread.  This helper is
    idempotent: re-running it adds rows for new authors without
    duplicating existing ones.
    """
    from lxml import etree

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    W15 = "http://schemas.microsoft.com/office/word/2012/wordml"

    comments_path = unpacked / "word" / "comments.xml"
    if not comments_path.is_file():
        return

    authors: list[str] = []
    seen: set[str] = set()
    for c in etree.parse(str(comments_path)).getroot().findall(f"{{{W}}}comment"):
        a = c.get(f"{{{W}}}author")
        if a and a not in seen:
            seen.add(a)
            authors.append(a)
    if not authors:
        return

    people_path = unpacked / "word" / "people.xml"
    if people_path.is_file():
        tree = etree.parse(str(people_path))
        root = tree.getroot()
    else:
        root = etree.Element(
            f"{{{W15}}}people",
            nsmap={"w15": W15, "w": W},
        )
        tree = etree.ElementTree(root)

    existing = {p.get(f"{{{W15}}}author") for p in root.findall(f"{{{W15}}}person")}

    changed = False
    for author in authors:
        if author in existing:
            continue
        person = etree.SubElement(root, f"{{{W15}}}person")
        person.set(f"{{{W15}}}author", author)
        presence = etree.SubElement(person, f"{{{W15}}}presenceInfo")
        presence.set(f"{{{W15}}}providerId", "None")
        presence.set(f"{{{W15}}}userId", author)
        existing.add(author)
        changed = True

    if changed or not people_path.is_file():
        tree.write(
            str(people_path), xml_declaration=True, encoding="UTF-8", standalone=True,
        )


def _insert_nested_reply_markers(document_xml: Path, parent_w_id: str, new_w_id: str) -> None:
    """Place reply's commentRangeStart/End strictly inside the parent's range markers."""
    from lxml import etree

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    tree = etree.parse(str(document_xml))
    root = tree.getroot()

    parent_start = None
    parent_end = None
    for el in root.iter():
        tag = etree.QName(el).localname
        wid = el.get(f"{{{W}}}id")
        if wid != parent_w_id:
            continue
        if tag == "commentRangeStart":
            parent_start = el
        elif tag == "commentRangeEnd":
            parent_end = el

    if parent_start is None or parent_end is None:
        raise RuntimeError(
            f"Parent comment {parent_w_id} has no range markers in document.xml; "
            "cannot nest reply markers."
        )

    start = etree.Element(f"{{{W}}}commentRangeStart")
    start.set(f"{{{W}}}id", new_w_id)
    end = etree.Element(f"{{{W}}}commentRangeEnd")
    end.set(f"{{{W}}}id", new_w_id)
    parent_start.addnext(start)
    parent_end.addprevious(end)

    # Append reference run as a sibling after the parent's reference run.
    parent_ref_run = None
    for r in root.iter(f"{{{W}}}r"):
        cref = r.find(f"{{{W}}}commentReference")
        if cref is not None and cref.get(f"{{{W}}}id") == parent_w_id:
            parent_ref_run = r
            break

    new_ref_run = etree.Element(f"{{{W}}}r")
    rpr = etree.SubElement(new_ref_run, f"{{{W}}}rPr")
    rstyle = etree.SubElement(rpr, f"{{{W}}}rStyle")
    rstyle.set(f"{{{W}}}val", "CommentReference")
    cref = etree.SubElement(new_ref_run, f"{{{W}}}commentReference")
    cref.set(f"{{{W}}}id", new_w_id)

    if parent_ref_run is not None:
        parent_ref_run.addnext(new_ref_run)
    else:
        # Fallback: append to paragraph containing parent_end
        parent_end.getparent().append(new_ref_run)

    tree.write(str(document_xml), xml_declaration=True, encoding="UTF-8", standalone=True)


def _do_new(input_path: Path, out_path: Path, spec: AddCommentSpec) -> int:
    """Anchor a new comment on a span in a specific paragraph.

    Reuses apply_edits.py's run-split semantics so spans crossing run boundaries
    are handled the same way they are for tracked-edit replace/delete.
    """
    from anthropic_bridge import run_anthropic
    from apply_edits import W_NS
    from commands.pack import run as pack_run
    from commands.unpack import run as unpack_run
    from lxml import etree

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        unpacked = tmp_dir / "unpacked"
        code = unpack_run(input_path, unpacked, merge_runs=True)
        if code != 0:
            return code

        # Allocate the new comment's w:id
        comments_xml = unpacked / "word" / "comments.xml"
        new_id = "0"
        if comments_xml.is_file():
            tree = etree.parse(str(comments_xml))
            max_id = -1
            for c in tree.getroot().findall(f"{{{W_NS}}}comment"):
                wid = c.get(f"{{{W_NS}}}id")
                if wid is not None:
                    try:
                        max_id = max(max_id, int(wid))
                    except ValueError:
                        pass
            new_id = str(max_id + 1)

        # Insert range markers + reference run in document.xml
        ok = _insert_new_comment_markers(
            unpacked / "word" / "document.xml",
            paragraph_index=spec.anchor_paragraph,
            anchor_text=spec.anchor_text or "",
            new_w_id=new_id,
        )
        if not ok:
            print(
                f"Could not anchor: text {spec.anchor_text!r} not found in paragraph "
                f"{spec.anchor_paragraph}.",
                file=sys.stderr,
            )
            return 1

        # Ensure comments.xml has the namespace declarations that comment.py needs.
        # Pass commentsExtended.xml so that existing paraId values are preserved
        # rather than overwritten with random ones (Fix 2).
        _ensure_comment_xml_namespaces(comments_xml, unpacked / "word" / "commentsExtended.xml")

        # Ensure all four comment-related relationships and content-type entries exist
        _ensure_all_comment_relationships(unpacked)

        # Call comment.py to write the comment body XMLs (no --parent for new comments).
        # The body text must be XML-escaped because comment.py interpolates
        # it directly into a string later parsed as XML (codex audit issue 2).
        result = run_anthropic(
            "comment.py",
            str(unpacked),
            new_id,
            _escape_comment_body(spec.text),
            "--author",
            spec.author,
            check=False,
        )
        if result.returncode != 0:
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return result.returncode

        # Backfill durable ids for any pre-existing comments and
        # ensure people.xml lists every author (see _do_reply for rationale).
        _backfill_durable_ids(unpacked)
        _create_people_xml(unpacked)

        return pack_run(unpacked, out_path, original=input_path, validate=True)


def _insert_new_comment_markers(
    document_xml: Path,
    paragraph_index: int,
    anchor_text: str,
    new_w_id: str,
) -> bool:
    """Wrap a span in paragraph N with new commentRangeStart/End + reference run.

    Handles anchor text that spans multiple runs with different formatting by
    reusing _get_direct_run_groups and _find_in_group from apply_edits.py.
    Splits the first and last affected runs at the anchor boundaries, preserving
    each run's rPr formatting.  Returns True if the anchor was found and markers
    were inserted; False otherwise.
    """
    from lxml import etree

    from apply_edits import (
        _clone_rpr,
        _find_in_group,
        _get_direct_run_groups,
        _make_run,
        _normalize_multi_wt_runs,
    )

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    tree = etree.parse(str(document_xml))
    root = tree.getroot()
    body = root.find(f"{{{W}}}body")
    paragraphs = body.findall(f"{{{W}}}p")
    if paragraph_index < 0 or paragraph_index >= len(paragraphs):
        return False
    paragraph = paragraphs[paragraph_index]
    _normalize_multi_wt_runs(paragraph)

    for group in _get_direct_run_groups(paragraph):
        affected = _find_in_group(group, anchor_text)
        if affected is None:
            continue

        # affected is a list of (run, t_el, before_text, after_text) tuples.
        # The insertion position in the paragraph's child list is the position of
        # the first affected run.
        para_children = list(paragraph)
        insert_idx = para_children.index(affected[0][0])

        new_elements: list = []

        # Text before the match within the first run
        if affected[0][2]:
            new_elements.append(_make_run(affected[0][2], _clone_rpr(affected[0][0])))

        # commentRangeStart
        start_el = etree.Element(f"{{{W}}}commentRangeStart")
        start_el.set(f"{{{W}}}id", new_w_id)
        new_elements.append(start_el)

        # Re-emit each affected run's matched portion with its original rPr.
        # For single-run case: the full matched text goes in one run.
        # For multi-run case: each run contributes its slice of the match.
        for run_el, t_el, before_txt, after_txt in affected:
            matched_slice = t_el.text[len(before_txt):len(t_el.text) - len(after_txt)] if after_txt else t_el.text[len(before_txt):]
            if matched_slice:
                new_elements.append(_make_run(matched_slice, _clone_rpr(run_el)))

        # commentRangeEnd
        end_el = etree.Element(f"{{{W}}}commentRangeEnd")
        end_el.set(f"{{{W}}}id", new_w_id)
        new_elements.append(end_el)

        # Reference run (comment anchor marker)
        ref_run = etree.Element(f"{{{W}}}r")
        rstyle_rpr = etree.SubElement(ref_run, f"{{{W}}}rPr")
        rstyle = etree.SubElement(rstyle_rpr, f"{{{W}}}rStyle")
        rstyle.set(f"{{{W}}}val", "CommentReference")
        cref = etree.SubElement(ref_run, f"{{{W}}}commentReference")
        cref.set(f"{{{W}}}id", new_w_id)
        new_elements.append(ref_run)

        # Text after the match within the last run
        if affected[-1][3]:
            new_elements.append(_make_run(affected[-1][3], _clone_rpr(affected[-1][0])))

        # Remove all affected runs and splice in the new elements
        for run_el, _, _, _ in affected:
            paragraph.remove(run_el)
        for offset, el in enumerate(new_elements):
            paragraph.insert(insert_idx + offset, el)

        tree.write(str(document_xml), xml_declaration=True, encoding="UTF-8", standalone=True)
        return True

    return False


def _do_resolve(input_path: Path, out_path: Path, spec: AddCommentSpec) -> int:
    """Toggle w15:done='1' on the matching commentEx entry."""
    from commands.pack import run as pack_run
    from commands.unpack import run as unpack_run
    from extract_comments import extract_comments

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        unpacked = tmp_path / "unpacked"
        code = unpack_run(input_path, unpacked, merge_runs=True)
        if code != 0:
            return code

        # Map C-id -> w:id integer
        comments, _ = extract_comments(input_path)
        target_w_id = None
        for c in comments:
            if c.comment_id == spec.resolve:
                target_w_id = c.ooxml_id
                break
        if target_w_id is None:
            print(f"Comment {spec.resolve} not found in {input_path}", file=sys.stderr)
            return 1

        # Edit commentsExtended.xml: find the matching commentEx by paraId rather
        # than by ordinal index (Fix 3: ordinal matching is brittle when the two
        # files are out of sync).
        from lxml import etree
        ext_path = unpacked / "word" / "commentsExtended.xml"
        if not ext_path.is_file():
            print("word/commentsExtended.xml missing — cannot resolve comment", file=sys.stderr)
            return 1
        tree = etree.parse(str(ext_path))
        w15_ns = "http://schemas.microsoft.com/office/word/2012/wordml"
        w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"

        # Ensure comments.xml has w14:paraId attributes filled in from commentsExtended.xml
        # before we try to read them (relies on Fix 2).
        comments_path = unpacked / "word" / "comments.xml"
        _ensure_comment_xml_namespaces(comments_path, ext_path)

        # Find the target comment's w14:paraId from comments.xml
        comments_tree = etree.parse(str(comments_path))
        target_para_id = None
        for c in comments_tree.getroot().findall(f"{{{w_ns}}}comment"):
            if c.get(f"{{{w_ns}}}id") == target_w_id:
                para_el = c.find(f"{{{w_ns}}}p")
                if para_el is not None:
                    target_para_id = para_el.get(f"{{{W14_NS}}}paraId")
                break
        if target_para_id is None:
            print(
                f"Target comment {target_w_id} has no paraId in comments.xml",
                file=sys.stderr,
            )
            return 1

        # Find the matching commentEx by paraId and set done="1"
        target_ex = None
        for ex in tree.getroot().findall(f"{{{w15_ns}}}commentEx"):
            if ex.get(f"{{{w15_ns}}}paraId") == target_para_id:
                target_ex = ex
                break
        if target_ex is None:
            print(f"No commentEx with paraId {target_para_id}", file=sys.stderr)
            return 1
        target_ex.set(f"{{{w15_ns}}}done", "1")
        tree.write(str(ext_path), xml_declaration=True, encoding="UTF-8", standalone=True)

        return pack_run(unpacked, out_path, original=input_path, validate=True)
