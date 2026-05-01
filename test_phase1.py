#!/usr/bin/env python3
"""
Simple test script for Phase 1: PDF Ingestion

This script:
1. Creates a minimal test PDF
2. Tests all pdf_parser functions
3. Displays results
"""

import os
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.pdf_parser import (
    validate_pdf,
    render_pages,
    extract_pdf_metadata,
    check_image_size,
)


def create_test_pdf():
    """Create a simple 3-page test PDF using reportlab."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except ImportError:
        print("❌ reportlab not installed. Install with: pip install reportlab")
        return None

    test_pdf_path = "tests/fixtures/test_book.pdf"
    os.makedirs(os.path.dirname(test_pdf_path), exist_ok=True)

    c = canvas.Canvas(test_pdf_path, pagesize=letter)
    
    # Page 1: Chapter title
    c.setFont("Helvetica-Bold", 20)
    c.drawString(100, 750, "CHƯƠNG I. SỐ HỮU TỈ")
    c.setFont("Helvetica", 12)
    c.drawString(100, 700, "Số hữu tỉ là số có thể viết dưới dạng a/b.")
    c.showPage()
    
    # Page 2: Lesson with formula
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 750, "Bài 1. Số hữu tỉ")
    c.setFont("Helvetica", 12)
    c.drawString(100, 700, "Định nghĩa: Số hữu tỉ là tỉ số của hai số nguyên.")
    c.drawString(100, 650, "Ví dụ: 1/2 + 1/3 = 3/6 + 2/6 = 5/6")
    c.showPage()
    
    # Page 3: Exercise
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 750, "Ví dụ 1")
    c.setFont("Helvetica", 12)
    c.drawString(100, 700, "Chứng minh rằng: (1/2) + (1/3) = 5/6")
    c.drawString(100, 650, "Giải: Ta có 1/2 = 3/6 và 1/3 = 2/6")
    c.drawString(100, 600, "Vậy 1/2 + 1/3 = 3/6 + 2/6 = 5/6 (đpcm)")
    c.showPage()
    
    c.save()
    return test_pdf_path


def test_pdf_parser():
    """Test all pdf_parser functions."""
    print("=" * 70)
    print("PHASE 1: PDF Ingestion — Test Suite")
    print("=" * 70)
    
    # Create test PDF
    print("\n1️⃣  Creating test PDF...")
    test_pdf = create_test_pdf()
    if not test_pdf:
        print("⚠️  Could not create test PDF")
        return False
    print(f"✅ Test PDF created: {test_pdf}")
    
    # Test validate_pdf
    print("\n2️⃣  Testing validate_pdf()...")
    is_valid = validate_pdf(test_pdf)
    if is_valid:
        print(f"✅ PDF is valid")
    else:
        print(f"❌ PDF validation failed")
        return False
    
    # Test extract_pdf_metadata
    print("\n3️⃣  Testing extract_pdf_metadata()...")
    metadata = extract_pdf_metadata(test_pdf)
    print(f"   Title: {metadata['title']}")
    print(f"   Author: {metadata['author']}")
    print(f"   Num Pages: {metadata['num_pages']}")
    print(f"   File Size: {metadata['file_size_mb']} MB")
    assert metadata['num_pages'] == 3, "Expected 3 pages"
    print("✅ Metadata extraction OK")
    
    # Test render_pages
    print("\n4️⃣  Testing render_pages()...")
    output_dir = "data/books/test_phase1"
    pages = render_pages(test_pdf, output_dir)
    
    print(f"   Rendered {len(pages)} pages:")
    for page in pages:
        print(f"   - {page.image_path}")
        print(f"     Size: {page.file_size_kb} KB, {page.width}x{page.height} px, grayscale={page.is_grayscale}")
    
    assert len(pages) == 3, f"Expected 3 pages, got {len(pages)}"
    print("✅ Render pages OK")
    
    # Test check_image_size
    print("\n5️⃣  Testing check_image_size()...")
    for page in pages:
        size_info = check_image_size(page.image_path)
        status = "⚠️  NEEDS COMPRESSION" if size_info['needs_compression'] else "✅"
        print(f"   Page {page.page_num}: {size_info['size_kb']:.1f} KB {status}")
    
    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED!")
    print("=" * 70)
    
    # Summary
    print("\n📊 SUMMARY:")
    print(f"  - PDF pages rendered: {len(pages)}")
    print(f"  - Average size/page: {sum(p.file_size_kb for p in pages)/len(pages):.1f} KB")
    total_size = sum(p.file_size_kb for p in pages)
    print(f"  - Total size: {total_size:.1f} KB")
    oversized = sum(1 for p in pages if p.file_size_kb > 100)
    if oversized:
        print(f"  - ⚠️  {oversized} page(s) > 100 KB (may impact API latency)")
    else:
        print(f"  - ✅ All pages < 100 KB (optimal for OCR)")
    
    return True


if __name__ == "__main__":
    try:
        success = test_pdf_parser()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
