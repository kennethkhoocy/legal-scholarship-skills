"""Generate a pandoc reference.docx with custom styles.

Creates or updates reference.docx with:
- Normal: Aptos 12pt, black, single spacing
- Heading 1/2/3: Aptos, black, bold, appropriate sizes
- Footnote Text: Aptos 10pt, black, single spacing, contextual spacing on
"""

import subprocess
import sys
import os
import tempfile

import toolcheck


def main():
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_LINE_SPACING
    from docx.enum.style import WD_STYLE_TYPE
    from docx.oxml.ns import qn
    from lxml import etree

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(root, "scripts", "reference.docx")

    # Try pandoc first for a clean base; fall back to existing file
    try:
        pandoc = toolcheck.find_pandoc()
    except toolcheck.ToolNotFoundError:
        pandoc = None
    tmp_path = os.path.join(tempfile.gettempdir(), "pandoc_default_reference.docx")

    if pandoc:
        subprocess.run(
            [pandoc, "-o", tmp_path, "--print-default-data-file", "reference.docx"],
            check=True,
        )
        print("Generated fresh pandoc default reference.docx as base")
        base_path = tmp_path
    else:
        print("pandoc not found — modifying existing reference.docx in place")
        base_path = output_path
        if not os.path.exists(base_path):
            print(f"Error: {base_path} not found and pandoc unavailable")
            sys.exit(1)

    doc = Document(base_path)

    BLACK = RGBColor(0, 0, 0)
    FONT_NAME = "Aptos"

    def get_or_create_style(name, style_type, base_style_name=None):
        """Get an existing style or create it."""
        try:
            return doc.styles[name]
        except KeyError:
            print(f"  Creating missing style: '{name}'")
            style = doc.styles.add_style(name, style_type)
            if base_style_name:
                try:
                    style.base_style = doc.styles[base_style_name]
                except KeyError:
                    pass
            return style

    def set_font(style, size_pt, bold=False):
        font = style.font
        font.name = FONT_NAME
        font.size = Pt(size_pt)
        font.color.rgb = BLACK
        font.bold = bold
        # Clear theme color overrides in XML so explicit RGB sticks
        rPr = style.element.find(qn("w:rPr"))
        if rPr is not None:
            color_el = rPr.find(qn("w:color"))
            if color_el is not None:
                for attr in ["themeColor", "themeShade", "themeTint"]:
                    key = qn("w:" + attr)
                    if key in color_el.attrib:
                        del color_el.attrib[key]

    def set_single_spacing(style, no_space_same_style=False):
        pf = style.paragraph_format
        pf.line_spacing = 1.0  # single spacing (proportion)
        # Also set via XML to ensure w:spacing line="240" lineRule="auto"
        pPr = style.element.find(qn("w:pPr"))
        if pPr is None:
            pPr = etree.SubElement(style.element, qn("w:pPr"))
        spacing_el = pPr.find(qn("w:spacing"))
        if spacing_el is None:
            spacing_el = etree.SubElement(pPr, qn("w:spacing"))
        spacing_el.set(qn("w:line"), "240")       # 240 twips = single
        spacing_el.set(qn("w:lineRule"), "auto")
        if no_space_same_style:
            ctx = pPr.find(qn("w:contextualSpacing"))
            if ctx is None:
                ctx = etree.SubElement(pPr, qn("w:contextualSpacing"))
            ctx.set(qn("w:val"), "1")

    # --- Normal ---
    normal = doc.styles["Normal"]
    set_font(normal, 12)
    set_single_spacing(normal)

    # --- Headings ---
    heading_sizes = {"Heading 1": 16, "Heading 2": 14, "Heading 3": 12}
    for name, size in heading_sizes.items():
        style = get_or_create_style(name, WD_STYLE_TYPE.PARAGRAPH, "Normal")
        set_font(style, size, bold=True)

    # --- Footnote Text ---
    fn_style = get_or_create_style("Footnote Text", WD_STYLE_TYPE.PARAGRAPH, "Normal")
    set_font(fn_style, 10)
    set_single_spacing(fn_style, no_space_same_style=True)

    doc.save(output_path)
    print(f"\nSaved: {output_path}")

    # --- Verify ---
    doc2 = Document(output_path)
    print("\n=== Style Verification ===")
    for name in ["Normal", "Heading 1", "Heading 2", "Heading 3", "Footnote Text"]:
        try:
            s = doc2.styles[name]
            f = s.font
            pf = s.paragraph_format
            spacing = "single" if pf.line_spacing_rule == WD_LINE_SPACING.SINGLE else str(pf.line_spacing_rule)
            bold = f.bold if f.bold is not None else "inherit"
            color = f.color.rgb if f.color and f.color.rgb else "inherit"
            size = f"{f.size.pt}pt" if f.size else "inherit"
            print(f"  {name}: {f.name or 'inherit'} {size} bold={bold} color={color} spacing={spacing}")
        except (KeyError, AttributeError) as e:
            print(f"  {name}: error - {e}")


if __name__ == "__main__":
    main()
