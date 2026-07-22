# -*- coding: utf-8 -*-
"""Deterministic docx post-processing for fidelity. Currently: force every
footnote-reference marker to render superscript (run-level vertAlign + the
FootnoteReference character style), which pandoc occasionally drops on some
markers. Idempotent. Usage: postprocess_docx.py <docx>"""
import sys, zipfile, shutil
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
def w(t): return f"{{{W}}}{t}"
def m(t): return f"{{{M}}}{t}"

def child(parent, tag, insert_at_start=False):
    node = parent.find(tag)
    if node is None:
        node = etree.Element(tag)
        if insert_at_start:
            parent.insert(0, node)
        else:
            parent.append(node)
    return node

def text_of(element):
    return "".join(t.text or "" for t in element.iter(w("t"))).strip()

def p_style(paragraph):
    ppr = paragraph.find(w("pPr"))
    if ppr is None:
        return ""
    pstyle = ppr.find(w("pStyle"))
    return pstyle.get(w("val")) if pstyle is not None else ""

def append_text_run(paragraph, text, bold=False):
    r = etree.Element(w("r"))
    if bold:
        rpr = etree.SubElement(r, w("rPr"))
        etree.SubElement(rpr, w("b"))
    t = etree.SubElement(r, w("t"))
    t.text = text
    if text.startswith(" ") or text.endswith(" "):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    paragraph.append(r)

path = sys.argv[1]
with zipfile.ZipFile(path) as zin:
    names = zin.namelist()
    data = {n: zin.read(n) for n in names}

doc = etree.fromstring(data["word/document.xml"])
total = fixed = 0
math_blocks = 0
for p in doc.iter(w("p")):
    if p.find(m("oMathPara")) is None:
        continue
    math_blocks += 1
    ppr = child(p, w("pPr"), insert_at_start=True)
    spacing = child(ppr, w("spacing"))
    spacing.set(w("before"), "160")
    spacing.set(w("after"), "160")
    spacing.set(w("line"), "360")
    spacing.set(w("lineRule"), "auto")

merged_defs = 0
body = doc.find(w("body"))
if body is not None:
    nodes = list(body)
    i = 0
    while i + 1 < len(nodes):
        p = nodes[i]
        nxt = nodes[i + 1]
        if p.tag == w("p") and nxt.tag == w("p") and p_style(p) == "DefinitionTerm" and p_style(nxt) == "Definition":
            term = text_of(p)
            if term:
                for node in list(p):
                    if node.tag != w("pPr"):
                        p.remove(node)
                append_text_run(p, term, bold=True)
                append_text_run(p, ": ")
                for node in list(nxt):
                    if node.tag == w("pPr"):
                        continue
                    nxt.remove(node)
                    p.append(node)
                body.remove(nxt)
                nodes.pop(i + 1)
                merged_defs += 1
                continue
        i += 1

for r in doc.iter(w("r")):
    if r.find(w("footnoteReference")) is None:
        continue
    total += 1
    rpr = r.find(w("rPr"))
    if rpr is None:
        rpr = etree.Element(w("rPr")); r.insert(0, rpr)
    va = rpr.find(w("vertAlign"))
    if va is None:
        va = etree.SubElement(rpr, w("vertAlign"))
    if va.get(w("val")) != "superscript":
        va.set(w("val"), "superscript"); fixed += 1
data["word/document.xml"] = etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)

if "word/styles.xml" in data:
    st = etree.fromstring(data["word/styles.xml"])
    for style in st.iter(w("style")):
        if style.get(w("styleId")) == "FootnoteReference":
            rpr = child(style, w("rPr"))
            va = rpr.find(w("vertAlign"))
            if va is None:
                va = etree.SubElement(rpr, w("vertAlign"))
            va.set(w("val"), "superscript")
        elif style.get(w("styleId")) == "DefinitionTerm":
            rpr = child(style, w("rPr"))
            child(rpr, w("b"))
    data["word/styles.xml"] = etree.tostring(st, xml_declaration=True, encoding="UTF-8", standalone=True)

shutil.copyfile(path, path + ".bak")
tmp = path + ".tmp"
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    for n in names:
        zout.writestr(n, data[n])
shutil.move(tmp, path)
print(f"footnoteReference runs: {total}; forced to superscript: {fixed}; display math blocks: {math_blocks}; description terms merged: {merged_defs}")
