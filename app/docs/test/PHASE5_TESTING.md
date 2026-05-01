# Phase 5 Testing Guide — Structure Parser

## Overview

**Phase 5** implements the **Structure Parser** — a rule engine that converts a flat list of `PageAnalysis` objects (from Gemini) into a hierarchical `BookStructure` (Book → Chapter → Lesson → ContentBlocks).

**Key Features:**
- ✅ Chapter detection (Roman numerals + Arabic digits)
- ✅ Lesson detection (Bài + §)
- ✅ Exercise type classification (7 types)
- ✅ Gemini labels prioritized over regex patterns
- ✅ Synthetic chapter creation for lessons before first chapter
- ✅ Unassigned blocks for content before chapter 1

---

## Quick Start

### 1️⃣ Standalone Test Script

Run without pytest, no API keys required:

```bash
python tests/test_phase5.py
```

**Expected Output:**
```
======================================================================
PHASE 5: Structure Parser — Test Suite
======================================================================

1️⃣  Chapter Detection (Roman + Arabic numerals)...
✅ Roman format: Ch 1 (I): SỐ HỮU TỈ
✅ Arabic format: Ch 2: ĐẠI SỐ
✅ Em-dash format: Ch 3: HÌNH HỌC

2️⃣  Lesson Detection (Bài + §)...
✅ Bài format: Lesson 1: Số hữu tỉ
✅ § format: Lesson 2: Số thực

... (5 more tests) ...

======================================================================
✅ ALL TESTS PASSED (without API calls)!

📊 SUMMARY:
   Test 1: Chapter detection (Roman + Arabic numerals)
   Test 2: Lesson detection (Bài + §)
   Test 3: Exercise type detection (7 types)
   Test 4: Full book structure parsing
   Test 5: Dataclass validation
   Test 6: Unassigned blocks handling
   Test 7: Lesson before chapter (synthetic chapter)

✅ Total: 7 tests passed
   No API calls made (no Gemini/Mathpix keys required)
   Execution time: < 1 second
```

### 2️⃣ Pytest Test Suite

Run with pytest (more verbose):

```bash
pytest tests/test_phase5.py -v
```

**Output:**
```
tests/test_phase5.py::test_chapter_detection PASSED
tests/test_phase5.py::test_lesson_detection PASSED
tests/test_phase5.py::test_exercise_detection PASSED
tests/test_phase5.py::test_parse_book PASSED
tests/test_phase5.py::test_dataclasses PASSED
tests/test_phase5.py::test_unassigned_blocks PASSED
tests/test_phase5.py::test_lesson_before_chapter PASSED

============================== 7 passed in 0.12s ==============================
```

---

## What Gets Tested

### Test 1️⃣ — Chapter Detection

**Tests:**
- Roman numeral format: `Chương I. SỐ HỮU TỈ` → Ch 1 (I)
- Arabic numeral format: `CHƯƠNG 2: ĐẠI SỐ` → Ch 2
- Em-dash format: `Chương 3 — HÌNH HỌC` → Ch 3

**Covers:**
- `_CHAPTER_PATTERNS` regex compilation
- Roman → Arabic conversion
- Title extraction

**Methods Tested:**
- `_detect_chapter(block)`
- `_parse_chapter_text(text)`

### Test 2️⃣ — Lesson Detection

**Tests:**
- "Bài X." format: `Bài 1. Số hữu tỉ` → Lesson 1
- "§X." format: `§2. Số thực` → Lesson 2

**Covers:**
- `_LESSON_PATTERNS` regex compilation
- Pattern priority (Gemini labels first, regex fallback)

**Methods Tested:**
- `_detect_lesson(block)`
- `_parse_lesson_text(text)`

### Test 3️⃣ — Exercise Type Detection

**Tests 7 exercise types:**
1. `Ví dụ 2` → `vi_du` (num=2)
2. `Bài tập` → `bai_tap`
3. `Luyện tập` → `luyen_tap`
4. `Hoạt động 1` → `hoat_dong` (num=1)
5. `Khám phá` → `kham_pha`
6. `Vận dụng` → `van_dung`
7. `Thử thách` → `thu_thach`

**Covers:**
- All 7 exercise pattern recognition
- Optional number extraction

**Methods Tested:**
- `_detect_exercise(text)`

### Test 4️⃣ — Full Book Structure Parsing

**Tests:**
- Multi-chapter structure (2 chapters)
- Multi-lesson structure (2 lessons in Ch 1)
- Content blocks per lesson
- Exercise metadata parsing

**Input (10 blocks across 2 chapters, 3 lessons):**
```
Ch I / Lesson 1 (Bài 1)
  ├─ text
  ├─ formula
  └─ exercise (Ví dụ)
Ch I / Lesson 2 (§2)
  └─ text
Ch II / Lesson 1 (Bài 1)
  └─ exercise (Bài tập)
```

**Output Validation:**
- ✅ 2 chapters detected
- ✅ Chapter 1: roman_index = "I"
- ✅ 2 lessons in Chapter 1
- ✅ 3 content blocks in Lesson 1.1
- ✅ Exercise type/num extracted correctly

**Methods Tested:**
- `parse_book(pages, grade, title, publisher, image_results)`

### Test 5️⃣ — Dataclass Validation

**Tests:**
- `FinalContentBlock` instantiation
- `Lesson` with content blocks
- `Chapter` with lessons
- `BookStructure` with chapters

**Covers:**
- Default values
- Field types
- List append operations

**Classes Tested:**
- `FinalContentBlock`
- `Lesson`
- `Chapter`
- `BookStructure`

### Test 6️⃣ — Unassigned Blocks

**Tests:**
- Content appearing before Chapter 1 is captured in `book.unassigned_blocks`

**Input:**
```
Text block (lời nói đầu)
Text block (cấu trúc sách)
Chapter title
Lesson title
```

**Output Validation:**
- ✅ 2 unassigned blocks captured
- ✅ Not lost or merged with chapter content

**Methods Tested:**
- `parse_book()` unassigned block handling

### Test 7️⃣ — Synthetic Chapter Creation

**Tests:**
- Lesson appearing before any chapter gets placed in synthetic `Chapter(index=0)`

**Input:**
```
Lesson title (Bài 1)
Text block
Chapter title (Chương I)
```

**Output Validation:**
- ✅ Synthetic `Chapter(index=0)` created
- ✅ Lesson placed inside synthetic chapter
- ✅ Actual Chapter I follows

**Methods Tested:**
- `parse_book()` synthetic chapter logic

---

## Manual Testing with Real Data

### Use Case: Parse a Real PDF

```python
from app.services.pdf_parser import PDFParser
from app.services.gemini_service import GeminiOCRService
from app.services.structure_parser import StructureParser

# Phase 1: Render PDF pages
pdf_parser = PDFParser()
pages_info = pdf_parser.render_pages("data/books/toán8.pdf", "data/books/toán8/pages")

# Phase 2: OCR with Gemini (requires GEMINI_API_KEY)
gemini = GeminiOCRService()
page_analyses = []
for page in pages_info:
    analysis = await gemini.analyze_page(page.image_path, page.page_num)
    page_analyses.append(analysis)

# Phase 5: Parse structure
parser = StructureParser()
book = parser.parse_book(
    pages=page_analyses,
    grade=8,
    title="Toán 8",
    publisher="CTST"
)

# Query results
print(f"Chapters: {len(book.chapters)}")
for ch in book.chapters:
    print(f"  Ch {ch.index} ({ch.roman_index}): {ch.title}")
    for lesson in ch.lessons:
        print(f"    Lesson {lesson.index}: {lesson.title}")
        for block in lesson.content_blocks[:2]:  # First 2 blocks
            print(f"      [{block.type}]")
```

---

## Interactive Testing

### Quick Regex Test

```python
from app.services.structure_parser import StructureParser

parser = StructureParser()

# Test chapter parsing
chapter_text = "Chương XII. LƯỢNG GIÁC"
result = parser._parse_chapter_text(chapter_text)
print(result)  # (12, 'XII', 'LƯỢNG GIÁC')

# Test lesson parsing
lesson_text = "§5. Phương trình lượng giác cơ bản"
result = parser._parse_lesson_text(lesson_text)
print(result)  # (5, 'Phương trình lượng giác cơ bản')

# Test exercise
exercise_text = "Hoạt động 3"
result = parser._detect_exercise(exercise_text)
print(result)  # ('hoat_dong', 3)
```

### Inspect Internal Patterns

```python
from app.services.structure_parser import _CHAPTER_PATTERNS, _EXERCISE_PATTERNS

# View compiled regex
for pat in _CHAPTER_PATTERNS:
    print(pat.pattern)

# View all exercise patterns
for name, pat in _EXERCISE_PATTERNS.items():
    print(f"{name}: {pat.pattern}")
```

---

## Checklist

Before considering Phase 5 complete:

- [ ] `python tests/test_phase5.py` runs without errors
- [ ] All 7 tests pass (shown in summary)
- [ ] `pytest tests/test_phase5.py -v` passes
- [ ] Chapter detection: Roman (`I`, `II`…) and Arabic (`1`, `2`…) both work
- [ ] Lesson detection: `Bài X` and `§X` both work
- [ ] Exercise type: all 7 types detected correctly
- [ ] Gemini labels (`chapter_title`, `lesson_title`) prioritized over regex
- [ ] `unassigned_blocks` captures content before Chapter 1
- [ ] Synthetic `Chapter(index=0)` created when lesson appears before first chapter
- [ ] No crashes with edge cases (empty title, missing fields, etc.)

---

## Troubleshooting

### Issue: "Module 'app' not found"

**Solution:**
```bash
cd c:\Users\IznA\math-master-crawl-data
python tests/test_phase5.py
```

Run from the project root, not from `tests/` directory.

### Issue: "FutureWarning: google.generativeai"

**Expected.** The warning comes from Phase 2 imports. Can be ignored for Phase 5 testing.

### Issue: "AssertionError in test X"

**Debug:**
```python
# Run the specific test function
from tests.test_phase5 import test_chapter_detection
test_chapter_detection()  # Will print which assertion failed
```

### Issue: Regex matches wrong patterns

**Check:**
- Input text capitalization (patterns use `re.UNICODE`)
- Whitespace (patterns handle `\s+`)
- Non-ASCII characters (patterns use `re.UNICODE`)

---

## Performance Baseline

**Standalone test:**
- **Execution time:** < 1 second
- **Memory:** ~10 MB
- **No external calls:** 0 API calls

**pytest run:**
- **Total time:** ~0.2-0.3 seconds
- **Including overhead:** imports, setup, teardown

---

## Next Phase

Once Phase 5 ✅ passes:

👉 **Phase 6:** MongoDB Schemas & Repositories — Save parsed book structure to database

---

**Last Updated:** May 1, 2026  
**Files:**
- `tests/test_phase5.py` — Standalone test script
- `app/services/structure_parser.py` — Implementation
- This file — Testing guide
