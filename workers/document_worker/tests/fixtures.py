"""Programmatically generated PDF fixtures for parsing tests — no binaries
committed to the repo. `reportlab` is a worker dev-only dependency.

Uses `reportlab.platypus` flowables (not raw `canvas.drawString`) so each
heading/paragraph is its own distinct PDF text object with real spacing —
Docling's layout model clusters bare absolute-positioned `drawString` lines
into one merged paragraph when they're visually close, which doesn't
exercise per-item node splitting the way a real Word/LibreOffice-exported
regulation PDF would.
"""

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

_STYLES = getSampleStyleSheet()
_TITLE = ParagraphStyle("FixtureTitle", parent=_STYLES["Title"], fontSize=16, spaceAfter=18)
_HEADING = ParagraphStyle("FixtureHeading", parent=_STYLES["Heading1"], spaceBefore=12, spaceAfter=10)
_BODY = ParagraphStyle("FixtureBody", parent=_STYLES["BodyText"], spaceBefore=24, spaceAfter=24)
_NESTED = ParagraphStyle("FixtureNested", parent=_BODY, leftIndent=1.5 * cm)


def digital_text_pdf() -> bytes:
    """A small multi-page PDF with a title, headings, a numbered list with
    nested letter items, and a table — enough to exercise Level 1 native
    extraction without any OCR escalation.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    story = [
        Paragraph("PERATURAN CONTOH NOMOR 1 TAHUN 2026", _TITLE),
        Paragraph("TENTANG PENGUJIAN DOKUMEN", _BODY),
        PageBreak(),
        Paragraph("BAB III", _HEADING),
        Paragraph("TAHAP PERENCANAAN", _HEADING),
        Paragraph("10. Umum", _BODY),
        Paragraph("Penjelasan umum mengenai tahap perencanaan.", _NESTED),
        Paragraph("11. Urut-urutan Kegiatan", _BODY),
        Paragraph("a. Kegiatan pertama dalam urutan.", _NESTED),
        Paragraph("b. Kegiatan kedua dalam urutan.", _NESTED),
        Paragraph("12. Dukungan", _BODY),
        Paragraph("a. Dukungan teknis dan administratif.", _NESTED),
        PageBreak(),
        Table(
            [
                ["No", "Nama", "Jumlah"],
                ["1", "Item Pertama", "10"],
                ["2", "Item Kedua", "20"],
            ],
            style=TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, (0, 0, 0)),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                ]
            ),
        ),
    ]
    doc.build(story)
    return buffer.getvalue()


def image_only_pdf() -> bytes:
    """A PDF with no extractable text layer at all (a solid rectangle drawn
    with no text operators) — exercises the "never fail on empty text layer"
    path (addendum §14) and OCR/UNKNOWN_BLOCK handling.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.rect(72, 400, 400, 300, fill=1, stroke=0)
    c.showPage()
    c.save()
    return buffer.getvalue()
