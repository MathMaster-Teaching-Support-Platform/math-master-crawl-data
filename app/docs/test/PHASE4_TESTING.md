# Phase 4 Testing Guide — Image Extraction Service

## Overview

Phase 4 implements the **ImageExtractor** service for cropping image regions identified by Gemini and persisting them to disk with automatic thumbnail generation.

**Key Features Tested:**
- Relative→pixel bbox conversion with clamping
- Whitespace auto-cropping
- Thumbnail generation (LANCZOS, max 300px)
- File naming convention (`page_XXX_fig_XX.jpg`)
- JPEG compression & optimization

---

## Quick Start

### 1️⃣ Standalone Test Script

```bash
cd /path/to/math-master-crawl-data
python tests/test_phase4.py
```

**Expected Output:**
```
======================================================================
PHASE 4: Image Extraction Service — Test Suite
All tests use local fixtures (no API calls)

1️⃣  Import ImageExtractor and initialize...
✅ ImageExtractor imported
✅ ImageResult dataclass imported
✅ image_extractor singleton created
✅ Singleton is ImageExtractor instance

2️⃣  Create test image fixtures...
✅ Test image created: data/books/test/pages/page_001.jpg
✅ Image size verified: 400x600

3️⃣  Test bbox_relative_to_pixel conversion...
✅ Simple conversion: [0.1, 0.3, 0.7, 0.8] → (40, 180, 280, 480)
✅ Clamping: [-0.1, -0.1, 1.5, 1.5] → (0, 0, 400, 600)
✅ Swapped coords handled: (0, 180, 280, 480)
✅ Full image: (0, 0, 400, 600)

... (more tests)

======================================================================
✅ ALL 10 TESTS PASSED!

📊 SUMMARY:
  ✅ ImageExtractor import & singleton
  ✅ Test fixtures creation
  ✅ BBox relative→pixel conversion with clamping
  ✅ Skip small figures (< 50×50 px)
  ✅ Whitespace cleanup/trimming
  ✅ Thumbnail generation (LANCZOS, max 300px)
  ✅ Full extract_and_store flow
  ✅ Proper skipping of tiny figures
  ✅ Multiple figures from same page
  ✅ ImageResult dataclass validation

⏭️  Next: Phase 5 — Structure Parser
```

**Duration:** ~2 seconds (no network calls)

---

## 2️⃣ Pytest Test Suite

### Run All Phase 4 Tests

```bash
pytest tests/test_phase4.py -v
```

### Run Specific Test

```bash
pytest tests/test_phase4.py::test_extract_and_store -v
```

### Run with Output

```bash
pytest tests/test_phase4.py -v -s
```

### Full Output Example

```
tests/test_phase4.py::test_import_and_init PASSED                    [10%]
tests/test_phase4.py::test_fixtures PASSED                           [20%]
tests/test_phase4.py::test_bbox_conversion PASSED                    [30%]
tests/test_phase4.py::test_skip_if_too_small PASSED                  [40%]
tests/test_phase4.py::test_cleanup_figure PASSED                     [50%]
tests/test_phase4.py::test_generate_thumbnail PASSED                 [60%]
tests/test_phase4.py::test_extract_and_store PASSED                  [70%]
tests/test_phase4.py::test_skip_small_in_extract PASSED              [80%]
tests/test_phase4.py::test_multiple_figures PASSED                   [90%]
tests/test_phase4.py::test_image_result_dataclass PASSED             [100%]

============= 10 passed in 2.34s =============
```

---

## Test Coverage

| Test # | Name | Focus |
|--------|------|-------|
| 1 | `test_import_and_init` | Module import, dataclass, singleton |
| 2 | `test_fixtures` | Create synthetic test image |
| 3 | `test_bbox_conversion` | Relative→pixel, clamping, edge cases |
| 4 | `test_skip_if_too_small` | Filter figures < 50×50 px |
| 5 | `test_cleanup_figure` | Whitespace trimming, auto-crop |
| 6 | `test_generate_thumbnail` | LANCZOS resize, quality, ratio |
| 7 | `test_extract_and_store` | Full flow: crop→cleanup→save→thumb |
| 8 | `test_skip_small_in_extract` | Verify None returned for tiny figs |
| 9 | `test_multiple_figures` | Extract 3 figures from same page |
| 10 | `test_image_result_dataclass` | Validate dataclass structure |

---

## 3️⃣ Manual Testing with Real Data

### Test with Actual PDF Page Image

```python
from app.services.image_service import image_extractor

# Extract figure from Gemini output
result = image_extractor.extract_and_store(
    page_image_path="data/books/toan8/pages/page_015.jpg",
    bbox_relative=[0.1, 0.25, 0.9, 0.75],  # From Gemini analysis
    book_id="toan8_ctst",
    page_num=15,
    fig_index=0,
    caption="Hình 2.1 — Định lý Pythagoras"
)

print(f"File: {result.file_path}")
print(f"URL: {result.url}")
print(f"Size: {result.width}x{result.height}")
print(f"KB: {result.file_size_kb:.1f}")
```

### Inspect Generated Files

```bash
# List extracted images
ls -lah storage/images/toan8_ctst/

# List thumbnails
ls -lah storage/images/toan8_ctst/thumbs/

# Check file sizes
du -sh storage/images/toan8_ctst/*

# View thumbnail (macOS)
open storage/images/toan8_ctst/thumbs/page_015_fig_00_thumb.jpg

# View thumbnail (Linux)
display storage/images/toan8_ctst/thumbs/page_015_fig_00_thumb.jpg

# View thumbnail (Windows)
start storage/images/toan8_ctst/thumbs/page_015_fig_00_thumb.jpg
```

---

## 4️⃣ Interactive Testing

### Python REPL Test

```python
import os
from PIL import Image
from app.services.image_service import ImageExtractor, image_extractor

# Create test image
img = Image.new('RGB', (600, 800), 'white')
from PIL import ImageDraw
draw = ImageDraw.Draw(img)
draw.rectangle([50, 100, 550, 700], fill='lightblue', outline='black', width=3)
draw.text((100, 300), 'Geometry Figure', fill='black')
os.makedirs('data/books/test/pages', exist_ok=True)
img.save('data/books/test/pages/test_geom.jpg', 'JPEG', quality=85)

# Test extraction
result = image_extractor.extract_and_store(
    page_image_path='data/books/test/pages/test_geom.jpg',
    bbox_relative=[0.1, 0.1, 0.9, 0.9],
    book_id='test_geom',
    page_num=1,
    fig_index=0,
    caption='Hình hình học'
)

print("✅ Success!")
print(f"   File: {result.file_path}")
print(f"   Size: {result.width}x{result.height}")
print(f"   URL: {result.url}")

# Verify files exist
assert os.path.exists(result.file_path)
assert os.path.exists(result.thumbnail_url.replace('/static/', 'storage/'))
print("✅ Files verified!")
```

### Test Edge Cases

```python
# Test 1: Very small figure (should skip)
result = image_extractor.extract_and_store(
    page_image_path='data/books/test/pages/test_geom.jpg',
    bbox_relative=[0.0, 0.0, 0.05, 0.05],  # 30x40 px
    book_id='test_edge',
    page_num=1,
    fig_index=0,
)
assert result is None
print("✅ Correctly skipped small figure")

# Test 2: Out of bounds (should clamp)
result = image_extractor.extract_and_store(
    page_image_path='data/books/test/pages/test_geom.jpg',
    bbox_relative=[-0.2, -0.1, 1.2, 1.1],
    book_id='test_edge',
    page_num=1,
    fig_index=1,
)
assert result is not None
print(f"✅ Clamped out-of-bounds: {result.width}x{result.height}")

# Test 3: Full page
result = image_extractor.extract_and_store(
    page_image_path='data/books/test/pages/test_geom.jpg',
    bbox_relative=[0.0, 0.0, 1.0, 1.0],
    book_id='test_edge',
    page_num=1,
    fig_index=2,
)
assert result is not None
print(f"✅ Full page: {result.width}x{result.height}")
```

---

## 5️⃣ Integration with Phase 2-3

### Simulate Gemini → ImageExtractor → Storage

```python
from app.services.gemini_service import ContentBlock
from app.services.image_service import image_extractor

# Mock Gemini output (ContentBlock with image)
image_block = ContentBlock(
    type='image',
    content=None,
    latex=None,
    image_bbox=[0.15, 0.25, 0.85, 0.75],
    caption='Hình 5.2: Hàm bậc hai',
    order=7,
    confidence=0.98,
    needs_mathpix=False,
)

# Extract using Gemini's bbox
result = image_extractor.extract_and_store(
    page_image_path='data/books/toan10/pages/page_087.jpg',
    bbox_relative=image_block.image_bbox,
    book_id='toan10',
    page_num=87,
    fig_index=0,
    caption=image_block.caption,
)

print(f"✅ Extracted: {result.caption}")
print(f"   URL: {result.url}")
```

---

## Checklist

- [ ] **Test 1** — Module imports without errors
- [ ] **Test 2** — Fixtures (synthetic images) created successfully
- [ ] **Test 3** — BBox conversion handles normal, edge, and swapped coordinates
- [ ] **Test 4** — Skip filtering works for small figures (< 50×50 px)
- [ ] **Test 5** — Whitespace trimming reduces image dimensions
- [ ] **Test 6** — Thumbnails created with correct dimensions (≤ 300px)
- [ ] **Test 7** — Full flow produces ImageResult with correct fields
- [ ] **Test 8** — Small figures return None (not saved)
- [ ] **Test 9** — Multiple figures extracted with unique URLs
- [ ] **Test 10** — ImageResult dataclass has all required fields

---

## Output Directories

After running tests, check these directories:

```
storage/images/
├── test_book/
│   ├── page_007_fig_00.jpg          (main image)
│   └── thumbs/
│       └── page_007_fig_00_thumb.jpg (thumbnail)
├── test_book_multi/
│   ├── page_009_fig_00.jpg
│   ├── page_009_fig_01.jpg
│   ├── page_009_fig_02.jpg
│   └── thumbs/
│       ├── page_009_fig_00_thumb.jpg
│       ├── page_009_fig_01_thumb.jpg
│       └── page_009_fig_02_thumb.jpg
└── test_edge/
    ├── page_001_fig_01.jpg
    ├── page_001_fig_02.jpg
    └── thumbs/...
```

**File Naming Convention:**
- Main: `page_{page_num:03d}_fig_{fig_index:02d}.jpg`
- Thumb: `thumbs/page_{page_num:03d}_fig_{fig_index:02d}_thumb.jpg`

**URL Convention:**
- Main: `/static/images/{book_id}/page_XXX_fig_XX.jpg`
- Thumb: `/static/images/{book_id}/thumbs/page_XXX_fig_XX_thumb.jpg`

---

## Troubleshooting

### Issue: PIL Not Installed

```bash
pip install pillow -q
```

### Issue: Test Hangs

- Check that no other process is using `storage/images/`
- Kill process: `lsof | grep storage/images` (macOS/Linux) or Task Manager (Windows)

### Issue: File Exists Error

- `storage/images/` directory has permissions issue
- Solution: `rm -rf storage/images/` and retry

### Issue: Thumbnail Quality Too Low

- Default quality is 85 (good balance of size/quality)
- For higher quality: modify `quality=95` in `generate_thumbnail()`
- Tradeoff: larger file size (~2x)

### Issue: BBox Out of Bounds

- Check that `bbox_relative` values are `[0, 1]` or will be clamped
- Test clamping: `_bbox_relative_to_pixel([-0.5, -0.5, 1.5, 1.5], 400, 600)`

---

## Performance Notes

| Operation | Time |
|-----------|------|
| Import + init | ~50ms |
| Create fixture | ~100ms |
| BBox conversion | <1ms |
| Whitespace cleanup | ~50ms |
| Thumbnail generation | ~150ms |
| Full extract_and_store | ~300ms |
| **Total (10 tests)** | **~2s** |

---

## Next Steps

After Phase 4 passes:

1. ✅ Phase 4: Image Extraction — **DONE**
2. ➡️ Phase 5: Structure Parser — Chapter/Lesson hierarchy
3. Phase 6: MongoDB models & repositories
4. Phase 7: Processing pipeline (end-to-end)
5. Phase 8: FastAPI endpoints
6. Phase 9: Integration tests
7. Phase 10: Docker & docs

---

**Last Updated:** May 1, 2026  
**Status:** Ready for testing  
**Test Count:** 10 standalone + pytest  
**Estimated Duration:** ~2 seconds
