#!/usr/bin/env python
"""
tests/fixtures/create_test_pdf.py

Standalone script to generate the 3-page test PDF used by Phase 9 E2E tests.

Usage:
    python tests/fixtures/create_test_pdf.py

Output:
    tests/fixtures/test_book.pdf
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def create_test_pdf(output_path: str) -> None:
    """Create a minimal 3-page SGK-like PDF at *output_path*."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        print("❌ reportlab not installed. Run: pip install reportlab>=4.0.0")
        sys.exit(1)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # ── Page 1: chapter title ──────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, 780, "CHUONG I. SO HUU TI")
    c.setFont("Helvetica", 12)
    c.drawString(50, 740, "Gioi thieu ve so huu ti trong chuong trinh Toan 7.")
    c.showPage()

    # ── Page 2: lesson title + text + formula hint ────────────────────────
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 780, "Bai 1. So huu ti")
    c.setFont("Helvetica", 12)
    c.drawString(50, 750, "Dinh nghia: So huu ti la so co the viet duoi dang a/b,")
    c.drawString(50, 730, "trong do a, b la cac so nguyen va b khac 0.")
    c.drawString(50, 700, "Cong thuc: a/b (b != 0)")
    c.drawString(50, 670, "Vi du: 1/2, -3/4, 0 = 0/1, 5 = 5/1")
    c.showPage()

    # ── Page 3: exercise ──────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 780, "Vi du 1: Tim cac so huu ti trong day so sau.")
    c.setFont("Helvetica", 12)
    c.drawString(50, 750, "0,5 ; -3 ; 2/7 ; can(2) ; 3,14")
    c.drawString(50, 720, "Giai:")
    c.drawString(50, 700, "0,5 = 1/2 => la so huu ti")
    c.drawString(50, 680, "-3 = -3/1 => la so huu ti")
    c.drawString(50, 660, "2/7 => la so huu ti")
    c.drawString(50, 640, "can(2) => khong la so huu ti (vo ti)")
    c.drawString(50, 620, "Hinh 1: Bieu dien so huu ti tren truc so")
    # Draw a simple axis line to represent a figure
    c.line(50, 560, 500, 560)
    c.line(270, 540, 270, 580)
    c.drawString(260, 525, "0")
    c.drawString(340, 525, "1/2")
    c.showPage()

    c.save()

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(buf.getvalue())

    size_kb = len(buf.getvalue()) / 1024
    print(f"✅ Created: {output_path}  ({size_kb:.1f} KB, 3 pages)")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output = os.path.join(script_dir, "test_book.pdf")
    create_test_pdf(output)
