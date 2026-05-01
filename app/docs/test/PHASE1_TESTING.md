# Phase 1 Testing Guide

## Quick Start

### 1️⃣ Simple Test Script (No pytest required)

Run the standalone test script:

```bash
python test_phase1.py
```

This script will:
- Create a simple 3-page test PDF
- Run all pdf_parser functions
- Display results and statistics
- Verify file sizes are optimal for OCR

**Expected output:**
```
======================================================================
PHASE 1: PDF Ingestion — Test Suite
======================================================================

1️⃣  Creating test PDF...
✅ Test PDF created: tests/fixtures/test_book.pdf

2️⃣  Testing validate_pdf()...
✅ PDF is valid

3️⃣  Testing extract_pdf_metadata()...
   Title: 
   Author: 
   Num Pages: 3
   File Size: 0.002 MB
✅ Metadata extraction OK

4️⃣  Testing render_pages()...
   Rendered 3 pages:
   - data/books/test_phase1/pages/page_001.jpg
     Size: 25.5 KB, 612x792 px, grayscale=False
   ...
✅ Render pages OK

5️⃣  Testing check_image_size()...
   Page 1: 25.5 KB ✅
   Page 2: 26.1 KB ✅
   Page 3: 26.3 KB ✅

======================================================================
✅ ALL TESTS PASSED!
======================================================================
```

---

## 2️⃣ Pytest Test Suite (Comprehensive)

### Prerequisites
```bash
pip install pytest pytest-asyncio reportlab
```

### Run all tests
```bash
pytest tests/test_pdf_parser.py -v
```

### Run specific test class
```bash
pytest tests/test_pdf_parser.py::TestRenderPages -v
```

### Run with detailed output
```bash
pytest tests/test_pdf_parser.py -vv -s
```

### Run with coverage report
```bash
pip install pytest-cov
pytest tests/test_pdf_parser.py --cov=app.services.pdf_parser --cov-report=html
```

---

## Manual Testing with a Real PDF

### Test with an actual PDF from your system

```python
from app.services.pdf_parser import validate_pdf, render_pages, check_image_size

# Replace with your PDF path
pdf_path = "path/to/your/book.pdf"

# Validate
if validate_pdf(pdf_path):
    print("✅ PDF is valid")
    
    # Render pages
    pages = render_pages(pdf_path, "data/books/my_book")
    print(f"✅ Rendered {len(pages)} pages")
    
    # Check sizes
    for page in pages:
        info = check_image_size(page.image_path)
        print(f"Page {page.page_num}: {info['size_kb']:.1f} KB")
else:
    print("❌ PDF is invalid")
```

Save this as `test_real_pdf.py` and run:
```bash
python test_real_pdf.py
```

---

## 3️⃣ Interactive Testing in Python REPL

```bash
python
```

Then in the Python shell:

```python
from app.services.pdf_parser import render_pages, check_image_size, extract_pdf_metadata

# Create or use test PDF
pdf_path = "tests/fixtures/test_book.pdf"

# Extract metadata
meta = extract_pdf_metadata(pdf_path)
print(f"Pages: {meta['num_pages']}, Size: {meta['file_size_mb']} MB")

# Render pages
pages = render_pages(pdf_path, "data/books/test")
print(f"Rendered: {len(pages)} pages")

# Check each page
for p in pages:
    info = check_image_size(p.image_path)
    print(f"Page {p.page_num}: {info['size_kb']:.1f} KB")
    
    # Check image dimensions
    print(f"  Dimensions: {p.width}x{p.height}, Grayscale: {p.is_grayscale}")
```

---

## ✅ Checklist

After running tests, verify:

- [x] `validate_pdf()` correctly identifies valid PDFs
- [x] `render_pages()` generates JPEG files (not PNG)
- [x] All page images are in `<output>/pages/` directory
- [x] Filenames follow pattern `page_001.jpg`, `page_002.jpg`, etc.
- [x] File sizes are reasonable (< 200 KB at 150 DPI)
- [x] `extract_pdf_metadata()` returns correct page count
- [x] `check_image_size()` warns when files > 100 KB
- [x] All images are valid JPEG (can open with PIL)
- [x] No memory leaks (file handles properly closed)

---

## Troubleshooting

### ⚠️ "reportlab not installed"
```bash
pip install reportlab
```

### ⚠️ "fitz not found" 
```bash
pip install PyMuPDF
```

### ⚠️ "JPEG quality 85 produces files > 200 KB"
- This is normal for some documents. The compression is working as intended.
- Quality=85 is balanced between file size and OCR accuracy.
- If needed for your specific PDFs, you can adjust DPI from 150 to 100 in pdf_parser.py.

### ⚠️ "Tests hang or timeout"
- Rendering large PDFs can be slow. Test with small PDFs first.
- Use smaller DPI (100 instead of 150) for initial tests.

---

## Output Directories

After running tests, check these locations:

```
data/books/test_phase1/        # Main test output
  └─ pages/
      ├─ page_001.jpg
      ├─ page_002.jpg
      └─ page_003.jpg

tests/fixtures/                # Test fixtures
  └─ test_book.pdf
```

All files are safe to delete between test runs.

---

## Next Steps

Once Phase 1 tests pass:

1. ✅ Phase 1 is confirmed working
2. ➡️ Ready for Phase 2: Gemini Flash OCR Service
3. You can now test Phase 2 with the rendered JPEG files from Phase 1

Confirm with: **"OK Phase 1"** to proceed to Phase 2 implementation.
