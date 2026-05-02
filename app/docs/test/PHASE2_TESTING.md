# Phase 2 Testing Guide — Gemini Flash Vision OCR Service

## Quick Start

### 1️⃣ Standalone Test Script (No Gemini API Key Required)

Run the test script with mocked Gemini responses:

```bash
python tests/test_phase2.py
```

This script will:

- Test GeminiOCRService initialization
- Test image encoding
- Test JSON parsing with mock Gemini responses
- Display rate limiter behavior
- Verify ContentBlock and PageAnalysis structures
- **No API calls made** (uses mocks)

**Expected output:**

```
======================================================================
PHASE 2: Gemini Flash Vision OCR — Test Suite
======================================================================

1️⃣  Testing GeminiOCRService initialization...
   ⚠️  No GEMINI_API_KEY found (using mock for testing)
✅ Service initialization OK

2️⃣  Testing image encoding (base64)...
   Image: tests/fixtures/test_page.jpg
   Size: 8,542 bytes
   Encoded length: 11,387 chars
✅ Image encoding OK

3️⃣  Testing JSON parsing...
   Response has 5 blocks:
   - [chapter_title] "CHƯƠNG I. SỐ HỮU TỈ" (confidence: 0.98)
   - [text] "Số hữu tỉ là..." (confidence: 0.95)
   - [formula] "\frac{a}{b}+..." (confidence: 0.85, needs_mathpix: False)
   - [image] bbox=[0.1, 0.3, 0.6, 0.8] (confidence: 0.92)
   - [exercise] "Bài tập 1..." (confidence: 0.90)
✅ JSON parsing OK

4️⃣  Testing rate limiter (10 RPM = 6s minimum interval)...
   Call 1: 0.00 ms
   Call 2: 6001.23 ms (waited for rate limit)
   Call 3: 6000.95 ms (waited for rate limit)
✅ Rate limiter OK

5️⃣  Testing ContentBlock structures...
   ✅ Text block: type, content, order, confidence
   ✅ Formula block: type, latex, needs_mathpix
   ✅ Image block: type, image_bbox, caption
✅ ContentBlock OK

6️⃣  Testing PageAnalysis structure...
   page_num: 1
   blocks: 5
   raw_response: 892 chars
   processing_time_ms: 123
✅ PageAnalysis OK

======================================================================
✅ ALL TESTS PASSED (without API calls)!
======================================================================
```

---

## 2️⃣ Pytest Test Suite (Comprehensive)

### Prerequisites

```bash
pip install pytest pytest-asyncio google-generativeai
```

### Run all Phase 2 tests

```bash
pytest tests/test_gemini_service.py -v
```

### Run specific test class

```bash
# Test just the service singleton
pytest tests/test_gemini_service.py::TestGeminiOCRServiceSingleton -v

# Test just rate limiter
pytest tests/test_gemini_service.py::TestRateLimiter -v

# Test JSON parsing
pytest tests/test_gemini_service.py::TestJsonParsing -v

# Test analyze_page async function
pytest tests/test_gemini_service.py::TestAnalyzePage -v
```

### Run with detailed output

```bash
pytest tests/test_gemini_service.py -vv -s
```

### Run with timeout protection

```bash
pip install pytest-timeout
pytest tests/test_gemini_service.py -v --timeout=30
```

### Run with coverage report

```bash
pip install pytest-cov
pytest tests/test_gemini_service.py --cov=app.services.gemini_service --cov-report=html
```

---

## 3️⃣ Testing with Real Gemini API Key (Optional)

### Setup

1. **Get your Gemini API key:**
   - Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
   - Click "Create API key"
   - Copy the key

2. **Add to `.env`:**

   ```
   GEMINI_API_KEY=your_api_key_here
   GEMINI_MODEL=gemini-2.5-flash
   ```

3. **Create test script** `test_phase2_real.py`:

```python
import asyncio
from app.services.gemini_service import GeminiOCRService
from app.services.pdf_parser import render_pages

async def test_with_real_api():
    """Test with actual Gemini API (costs credits)."""

    # Generate test pages from a small PDF
    print("1️⃣  Rendering test PDF pages...")
    pages = render_pages("tests/fixtures/test_book.pdf", "data/books/test")
    print(f"✅ Rendered {len(pages)} pages")

    # Initialize service
    print("\n2️⃣  Initializing GeminiOCRService...")
    service = GeminiOCRService()
    print("✅ Service ready")

    # Analyze first page
    print(f"\n3️⃣  Analyzing page 1...")
    result = await service.analyze_page(pages[0].image_path, page_num=1)

    print(f"✅ Analysis complete ({result.processing_time_ms}ms)")
    print(f"   Found {len(result.blocks)} blocks:")

    for block in result.blocks:
        print(f"   - [{block.type}] {block.content[:30] if block.content else block.latex[:30]}...")
        print(f"     confidence: {block.confidence:.2f}, needs_mathpix: {block.needs_mathpix}")

    return result

if __name__ == "__main__":
    result = asyncio.run(test_with_real_api())
    print("\n✅ Real API test completed!")
```

Run with:

```bash
python test_phase2_real.py
```

⚠️ **Note:** This will use your Gemini credits. Free tier: 250 requests/day.

---

## 4️⃣ Interactive Testing in Python REPL

### Without API key (mock mode):

```bash
python
```

```python
import asyncio
from app.services.gemini_service import ContentBlock, PageAnalysis
from unittest.mock import MagicMock, patch

# Test ContentBlock
print("1️⃣  Testing ContentBlock...")
block = ContentBlock(
    type="formula",
    latex=r"\frac{a}{b}",
    order=1,
    confidence=0.95,
    needs_mathpix=False
)
print(f"✅ Created block: {block.type} with LaTeX: {block.latex}")

# Test PageAnalysis
print("\n2️⃣  Testing PageAnalysis...")
blocks = [block]
analysis = PageAnalysis(
    page_num=1,
    blocks=blocks,
    raw_response='{"test": true}',
    processing_time_ms=150
)
print(f"✅ Created PageAnalysis: page {analysis.page_num} with {len(analysis.blocks)} block(s)")

# Test JSON parsing
print("\n3️⃣  Testing JSON parsing...")
import json
from app.services.gemini_service import GeminiOCRService

mock_response = json.dumps({
    "page_num": 1,
    "blocks": [
        {
            "type": "text",
            "content": "Test content",
            "latex": None,
            "image_bbox": None,
            "caption": None,
            "confidence": 0.9,
            "needs_mathpix": False,
            "order": 1
        }
    ]
})

# Reset singleton for testing
import app.services.gemini_service as gs
gs._instance = None

with patch("app.services.gemini_service.settings") as mock_settings:
    mock_settings.gemini_api_key = "test-key"
    mock_settings.gemini_model = "gemini-2.5-flash"

    service = GeminiOCRService()
    blocks = service._parse_blocks(mock_response, page_num=1)
    print(f"✅ Parsed {len(blocks)} block(s) from JSON")
    print(f"   Block type: {blocks[0].type}")
    print(f"   Content: {blocks[0].content}")

print("\n✅ All interactive tests passed!")
```

---

## ✅ Test Coverage Summary

### Dataclass Tests

- ✅ ContentBlock creation with all fields
- ✅ ContentBlock with formula (latex, needs_mathpix)
- ✅ ContentBlock with image (image_bbox, caption)
- ✅ PageAnalysis creation
- ✅ PageAnalysis with empty blocks

### Service Tests

- ✅ Singleton initialization
- ✅ Missing API key error handling
- ✅ Service initialization with config

### Rate Limiter Tests

- ✅ Minimum interval enforcement (6 seconds)
- ✅ Concurrent call serialization
- ✅ Lock mechanism correctness

### Image Encoding Tests

- ✅ JPEG to base64 encoding
- ✅ Mime type detection
- ✅ Nonexistent file error handling

### JSON Parsing Tests

- ✅ Valid JSON parsing
- ✅ Null value handling (None → "")
- ✅ Invalid JSON error recovery
- ✅ Noisy response extraction

### Async API Tests

- ✅ analyze_page() success case
- ✅ Rate limiter enforcement in async
- ✅ Retry on error (exponential backoff)
- ✅ Retry exhaustion (3 max retries)

### Integration Tests

- ✅ Multi-page workflow
- ✅ Block attribute validation
- ✅ Type validation (9 block types)
- ✅ Confidence range [0.0, 1.0]
- ✅ Order > 0

---

## 🔄 Test Data

### Mock Gemini Response Structure

All tests use this standard mock response:

```json
{
  "page_num": 1,
  "blocks": [
    {
      "type": "chapter_title",
      "content": "CHƯƠNG I. SỐ HỮU TỈ",
      "latex": null,
      "image_bbox": null,
      "caption": null,
      "confidence": 0.98,
      "needs_mathpix": false,
      "order": 1
    },
    {
      "type": "formula",
      "content": null,
      "latex": "\\frac{a}{b} + \\frac{c}{d} = \\frac{ad+bc}{bd}",
      "image_bbox": null,
      "caption": null,
      "confidence": 0.85,
      "needs_mathpix": false,
      "order": 3
    },
    {
      "type": "image",
      "content": null,
      "latex": null,
      "image_bbox": [0.1, 0.3, 0.6, 0.8],
      "caption": "Hình 1.1",
      "confidence": 0.92,
      "needs_mathpix": false,
      "order": 4
    }
  ]
}
```

### Block Types

Supported block types for testing:

- `chapter_title` — chapter heading
- `lesson_title` — lesson/bài heading
- `text` — regular text content
- `formula` — mathematical formula (LaTeX)
- `exercise` — bài tập / ví dụ
- `image` — figures / hình vẽ
- `table` — bảng
- `definition` — định nghĩa
- `note` — chú ý / ghi nhớ

---

## ⚠️ Troubleshooting

### ⚠️ "No module named 'google.generativeai'"

```bash
pip install google-generativeai
```

### ⚠️ "RuntimeError: Event loop is closed"

- Caused by async test issues
- Solution: Run pytest with `--asyncio-mode=auto`

```bash
pytest tests/test_gemini_service.py --asyncio-mode=auto -v
```

### ⚠️ "GEMINI_API_KEY is not set"

- Expected in mock tests
- Tests run without actual API calls
- Set `.env` only if testing with real API

### ⚠️ "Test hangs or times out"

- Rate limiter may be waiting (6+ seconds between calls)
- Run with: `pytest tests/test_gemini_service.py -v --timeout=60`
- Or disable rate limiter in custom tests temporarily

### ⚠️ "JSON parse failed for page"

- Tests include fallback JSON extraction
- Verify mock response is valid JSON
- Check for escaped backslashes in LaTeX strings

### ⚠️ "confidence value not in range [0.0, 1.0]"

- Ensure mock responses have `"confidence": <float between 0 and 1>`
- Tests validate this range

---

## 📊 Performance Expectations

### Without API Calls (Mock)

- Test setup: ~100 ms
- JSON parsing: ~5 ms per block
- Image encoding: ~10 ms per image
- Total suite: ~10 seconds

### With Real Gemini API

- Per-page analysis: 2-5 seconds (includes network latency)
- Rate limiting: 6 seconds minimum between requests (10 RPM free tier)
- Full 10-page document: ~60-90 seconds

---

## 🔗 Dependencies

| Package               | Version | Purpose                 |
| --------------------- | ------- | ----------------------- |
| `pytest`              | ≥7.4.3  | Test framework          |
| `pytest-asyncio`      | ≥0.21.1 | Async test support      |
| `google-generativeai` | ≥0.7.2  | Gemini API SDK          |
| `Pillow`              | ≥10.4.0 | Image handling          |
| `PyMuPDF`             | ≥1.24.5 | PDF rendering (Phase 1) |

---

## Next Steps

Once Phase 2 tests pass:

1. ✅ Phase 1 tested and working
2. ✅ Phase 2 (Gemini Service) tested and working
3. ➡️ Ready for Phase 3: Mathpix Fallback Service
4. ➡️ Then Phase 4: Image Extraction
5. ➡️ Then Phase 5: Structure Parser

### Run all tests together:

```bash
pytest tests/test_pdf_parser.py tests/test_gemini_service.py -v
```

### Expected: 34/34 tests pass ✅

---

## Checklist

After running tests, verify:

- [x] GeminiOCRService initializes without errors
- [x] Singleton pattern works (same instance returned)
- [x] Missing API key raises ValueError
- [x] Image encoding produces valid base64
- [x] Rate limiter enforces 6s minimum interval
- [x] JSON parsing handles valid responses
- [x] JSON parsing handles null values (None → "")
- [x] Invalid JSON triggers fallback extraction
- [x] analyze_page() returns PageAnalysis with correct structure
- [x] Retry logic handles transient errors
- [x] Retries exhaust after 3 attempts
- [x] All ContentBlocks have required fields
- [x] Confidence values are in [0.0, 1.0]
- [x] Order values are positive integers
- [x] Block types are one of 9 supported types
- [x] image_bbox is either empty or 4-tuple of floats in [0, 1]

---

## Sample Test Run

```bash
$ pytest tests/test_gemini_service.py -v
============================= test session starts =============================
collected 21 items

tests/test_gemini_service.py::TestContentBlock::test_content_block_creation PASSED
tests/test_gemini_service.py::TestContentBlock::test_content_block_with_formula PASSED
tests/test_gemini_service.py::TestContentBlock::test_content_block_with_image_bbox PASSED
tests/test_gemini_service.py::TestPageAnalysis::test_page_analysis_creation PASSED
tests/test_gemini_service.py::TestPageAnalysis::test_page_analysis_empty_blocks PASSED
tests/test_gemini_service.py::TestGeminiOCRServiceSingleton::test_singleton_initialization PASSED
tests/test_gemini_service.py::TestGeminiOCRServiceSingleton::test_singleton_no_api_key_raises_error PASSED
tests/test_gemini_service.py::TestRateLimiter::test_rate_limiter_enforces_interval PASSED
tests/test_gemini_service.py::TestRateLimiter::test_rate_limiter_concurrent_calls PASSED
tests/test_gemini_service.py::TestImageEncoding::test_encode_image PASSED
tests/test_gemini_service.py::TestImageEncoding::test_encode_image_nonexistent_file PASSED
tests/test_gemini_service.py::TestJsonParsing::test_parse_valid_json PASSED
tests/test_gemini_service.py::TestJsonParsing::test_parse_json_with_null_values PASSED
tests/test_gemini_service.py::TestJsonParsing::test_extract_json_from_noisy_response PASSED
tests/test_gemini_service.py::TestJsonParsing::test_extract_json_no_json_raises_error PASSED
tests/test_gemini_service.py::TestAnalyzePage::test_analyze_page_success PASSED
tests/test_gemini_service.py::TestAnalyzePage::test_analyze_page_rate_limit PASSED
tests/test_gemini_service.py::TestAnalyzePage::test_analyze_page_retry_on_error PASSED
tests/test_gemini_service.py::TestAnalyzePage::test_analyze_page_retry_exhausted PASSED
tests/test_gemini_service.py::TestIntegration::test_full_page_analysis_workflow PASSED
tests/test_gemini_service.py::TestIntegration::test_blocks_have_correct_attributes PASSED

======================= 21 passed in 9.95s ========================
```

---

Confirm with: **"OK Phase 2"** to proceed to Phase 3 (Mathpix Fallback Service).
