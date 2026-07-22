"""Generators for synthetic test PDFs with known characteristics.

Each helper produces a small PDF the probe should classify in a predictable bucket:
  - make_simple_pdf       → born_digital_simple
  - make_formula_pdf      → born_digital_formulas (math-glyph dense)
  - make_tabular_pdf      → born_digital_tables
  - make_complex_pdf      → born_digital_complex
  - make_scanned_pdf      → scanned (no text layer; image-only)
  - make_encrypted_pdf    → encrypted

These are used by tests in test_probe_pdf.py to verify classification thresholds.
"""

import io
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfgen import canvas


def make_simple_pdf(out_path: Path, num_pages: int = 3, words_per_page: int = 250) -> Path:
    """Born-digital, plain text only. Should classify as born_digital_simple."""
    c = canvas.Canvas(str(out_path), pagesize=letter)
    word = "lorem ipsum dolor sit amet consectetur adipiscing elit ".split()
    for page_no in range(num_pages):
        x, y = 72, 720
        words_placed = 0
        while words_placed < words_per_page:
            line = " ".join(word[words_placed % len(word)] for _ in range(12))
            c.drawString(x, y, line)
            y -= 14
            words_placed += 12
            if y < 72:
                break
        c.showPage()
    c.save()
    return out_path


def make_formula_pdf(out_path: Path, num_pages: int = 3) -> Path:
    """Born-digital PDF dense with Unicode math glyphs on every page.

    Exercises the formula GLYPH signal of the probe (the math-FONT signal is
    covered separately by the `_fontname_is_math` unit tests and the real-world
    math PDFs). Should classify as born_digital_formulas.

    Requires a math-capable TrueType font on the host (Segoe UI Symbol on
    Windows, DejaVu Sans on Linux). Raises RuntimeError when none is found so
    the caller can choose to skip rather than fail.
    """
    import os
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        r"C:\Windows\Fonts\seguisym.ttf",                          # Segoe UI Symbol (Windows)
        r"C:\Windows\Fonts\DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",         # Debian/Ubuntu
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",                  # Fedora
        "/Library/Fonts/Arial Unicode.ttf",                        # macOS
    ]
    font_name = None
    for cand in candidates:
        if os.path.exists(cand):
            try:
                pdfmetrics.registerFont(TTFont("MathTTF", cand))
                font_name = "MathTTF"
                break
            except Exception:
                continue
    if font_name is None:
        raise RuntimeError(
            "make_formula_pdf: no math-capable TTF found "
            "(looked for Segoe UI Symbol / DejaVu Sans / Arial Unicode)."
        )

    # Display-equation-like lines using glyphs confirmed to round-trip through
    # the embedded subset's ToUnicode map.
    equations = [
        "∑_{i=1}^{n} x_i ≤ ∫_0^∞ f(α) dα ≈ β ± √σ",
        "∂L/∂θ = ∇·F − λ·g,   ω ∈ ℝ,   φ ⊆ ℂ,   π² ⋅ μ ≥ ξ",
        "∀ε > 0 ∃δ : |x − x₀| < δ ⇒ |f(x) − L| < ε,   Γ·Θ → ∞",
        "ρ ≡ ξ (mod ℤ),   Σ ≥ Φ,   ∏ (1 − ρ) ⋅ τ ≠ ∅",
    ]
    filler = (
        "We establish the estimator and derive its asymptotic distribution "
        "under the regularity conditions stated in the appendix. "
    )

    c = canvas.Canvas(str(out_path), pagesize=letter)
    for page_no in range(num_pages):
        c.setFont(font_name, 12)
        y = 740
        c.drawString(72, y, f"Proposition {page_no + 1}.")
        y -= 24
        for eq in equations:
            c.drawString(72, y, eq)
            y -= 24
        # Prose filler so text_layer_coverage clearly exceeds the simple-min
        # threshold; confirms the page is born-digital, not scanned.
        c.setFont(font_name, 10)
        for _ in range(18):
            if y < 80:
                break
            c.drawString(72, y, filler)
            y -= 14
        c.showPage()
    c.save()
    return out_path


def make_tabular_pdf(out_path: Path, num_pages: int = 2, rows_per_table: int = 15) -> Path:
    """Born-digital with prominent tables. Should classify as born_digital_tables."""
    doc = SimpleDocTemplate(str(out_path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    filler = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor "
        "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. "
    )
    for page_no in range(num_pages):
        story.append(Paragraph(f"Report Page {page_no + 1}", styles["Heading1"]))
        story.append(Spacer(1, 6))
        # Add a paragraph of text so text_layer_coverage exceeds TUNE_TEXT_LAYER_SIMPLE_MIN
        story.append(Paragraph(filler * 4, styles["Normal"]))
        story.append(Spacer(1, 6))
        data = [["Col A", "Col B", "Col C", "Col D"]] + [
            [f"r{r}c1", f"r{r}c2", f"r{r}c3", f"r{r}c4"] for r in range(rows_per_table)
        ]
        t = Table(data)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(t)
        if page_no < num_pages - 1:
            story.append(PageBreak())
    doc.build(story)
    return out_path


def make_complex_pdf(out_path: Path, num_pages: int = 2) -> Path:
    """Born-digital with images and tables mixed. Should classify as born_digital_complex."""
    import io
    import tempfile
    from PIL import Image

    # Generate a small grey JPEG once — drawImage embeds it as a real XObject,
    # so pdfplumber's page.images will pick it up for image_density measurement.
    img = Image.new("RGB", (300, 200), color=(200, 200, 200))
    img_buf = io.BytesIO()
    img.save(img_buf, format="JPEG", quality=80)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
        tf.write(img_buf.getvalue())
        img_path = tf.name

    # Build a long filler string (repeated) so text_layer_coverage easily exceeds 500
    filler_line = (
        "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor "
        "incididunt ut labore et dolore magna aliqua ut enim ad minim veniam quis nostrud "
    )
    filler_block = (filler_line * 6).strip()

    c = canvas.Canvas(str(out_path), pagesize=letter)
    page_w, page_h = letter  # 612 x 792 pts
    for page_no in range(num_pages):
        # --- text section (top half) ---
        y = page_h - 60
        c.drawString(72, y, f"Complex page {page_no + 1} — mixed content with figures")
        y -= 18
        # Write filler lines until we hit ~400 pt mark
        words = filler_block.split()
        line_buf: list[str] = []
        for word in words:
            trial = " ".join(line_buf + [word])
            if c.stringWidth(trial, "Helvetica", 10) > 460:
                c.setFont("Helvetica", 10)
                c.drawString(72, y, " ".join(line_buf))
                y -= 13
                line_buf = [word]
                if y < 410:
                    break
            else:
                line_buf.append(word)
        if line_buf and y >= 410:
            c.setFont("Helvetica", 10)
            c.drawString(72, y, " ".join(line_buf))

        # --- image section (bottom ~45% of page) — large images for high image_density ---
        # page_h = 792, so bottom 360 pts = 45%.  Two images side by side fill ~530x340 pts.
        # Combined image area: 265*340 * 2 = 180200; page area: 612*792 = 484704 → ~37% density
        img_h = 340
        img_w = int((page_w - 3 * 36) / 2)  # two images with 36pt margins and gap
        c.drawImage(img_path, 36, 60, width=img_w, height=img_h)
        c.drawImage(img_path, 36 + img_w + 36, 60, width=img_w, height=img_h)
        c.setFont("Helvetica", 9)
        c.drawString(72, 42, "Figure captions for the two panels shown above.")
        c.showPage()
    c.save()
    Path(img_path).unlink()
    return out_path


def make_scanned_pdf(out_path: Path, num_pages: int = 2) -> Path:
    """Image-only PDF with no text layer. Should classify as scanned.

    Strategy: render a born-digital PDF to images via pypdfium2, then embed those
    images back into a fresh PDF with no text layer.
    """
    import pypdfium2 as pdfium
    from PIL import Image
    import tempfile

    # Step 1: make a temporary born-digital PDF
    tmp_src = out_path.with_suffix(".tmp.pdf")
    make_simple_pdf(tmp_src, num_pages=num_pages)

    # Step 2: render each page to a PIL image
    pdf = pdfium.PdfDocument(str(tmp_src))
    images = []
    for page in pdf:
        bitmap = page.render(scale=1.5)
        images.append(bitmap.to_pil().convert("RGB"))
    pdf.close()
    tmp_src.unlink()

    # Step 3: write a PDF that contains only those images, no text layer
    c = canvas.Canvas(str(out_path), pagesize=letter)
    page_w, page_h = letter
    for img in images:
        img_buf = io.BytesIO()
        img.save(img_buf, format="JPEG", quality=80)
        img_buf.seek(0)
        # ReportLab's drawImage accepts a file-like object via a temp file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            tf.write(img_buf.getvalue())
            tf_path = tf.name
        c.drawImage(tf_path, 0, 0, width=page_w, height=page_h)
        c.showPage()
        Path(tf_path).unlink()
    c.save()
    return out_path


def make_encrypted_pdf(out_path: Path, password: str = "secret") -> Path:
    """Born-digital simple PDF, then encrypted with a user password."""
    from pypdf import PdfReader, PdfWriter

    tmp_src = out_path.with_suffix(".tmp.pdf")
    make_simple_pdf(tmp_src, num_pages=2)

    reader = PdfReader(str(tmp_src))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password, password)
    with open(out_path, "wb") as f:
        writer.write(f)
    tmp_src.unlink()
    return out_path
