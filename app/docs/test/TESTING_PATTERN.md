# Testing Pattern — All Phases (1-10)

## Overview

Each phase of the project follows a consistent testing structure with **2 files per phase**:

1. **`tests/test_phaseX.py`** — Standalone test script
2. **`app/docs/test/PHASEX_TESTING.md`** — Testing guide & documentation

This ensures:
- ✅ Tests work standalone (no pytest required)
- ✅ Tests work with pytest (comprehensive)
- ✅ Clear documentation for manual testing
- ✅ Consistent structure across all phases

---

## File Structure

```
project-root/
├─ tests/
│  ├─ test_phase1.py          # Standalone test for Phase 1
│  ├─ test_phase2.py          # Standalone test for Phase 2
│  ├─ test_phase3.py          # Standalone test for Phase 3
│  ├─ test_phase4.py          # Standalone test for Phase 4
│  ├─ test_phase5.py          # Standalone test for Phase 5
│  └─ ... (test_phase6.py through test_phase10.py)
│
└─ app/docs/test/
   ├─ PHASE1_TESTING.md       # Testing guide for Phase 1
   ├─ PHASE2_TESTING.md       # Testing guide for Phase 2
   ├─ PHASE3_TESTING.md       # Testing guide for Phase 3
   ├─ PHASE4_TESTING.md       # Testing guide for Phase 4
   ├─ PHASE5_TESTING.md       # Testing guide for Phase 5
   └─ ... (PHASE6_TESTING.md through PHASE10_TESTING.md)
```

---

## Running Tests

### Standalone Test (No pytest)

```bash
# Run any phase directly
python tests/test_phase1.py
python tests/test_phase2.py
python tests/test_phase3.py
# ... and so on
```

**Characteristics:**
- ✅ No dependencies on pytest
- ✅ No API keys required (uses mocks)
- ✅ Fast execution
- ✅ Formatted output with emoji checkmarks
- ✅ Shows summary statistics

### Full Test Suite (With pytest)

```bash
# Run all tests
pytest tests/ -v

# Run single phase
pytest tests/test_phase1.py -v
pytest tests/test_phase2.py -v

# Run with coverage
pytest tests/ --cov=app.services --cov-report=html
```

---

## What Each Phase Tests

### Phase 1 ✅ — PDF Ingestion
- **File:** `tests/test_phase1.py` & `PHASE1_TESTING.md`
- **Covers:** PDF validation, page rendering (JPEG), metadata extraction, image sizing, grayscale detection
- **Tests:** 7 tests (validate_pdf, render_pages, extract_pdf_metadata, check_image_size, grayscale_detection, integration)

### Phase 2 ✅ — Gemini Flash Vision OCR
- **File:** `tests/test_phase2.py` & `PHASE2_TESTING.md`
- **Covers:** GeminiOCRService initialization, image encoding, JSON parsing, rate limiting, retry logic
- **Tests:** 6 tests (singleton, image_encoding, json_parsing, rate_limiter, content_block, page_analysis)

### Phase 3 ✅ — Mathpix Fallback Service
- **File:** `tests/test_phase3.py` & `PHASE3_TESTING.md`
- **Covers:** Formula extraction, image preprocessing, Mathpix API calls, LaTeX validation, bbox resolution
- **Tests:** 9 tests (import, is_enabled, validate_latex, latex_to_readable, extract_formula, resolve_bbox, preprocess, batch_extract, dataclass)

### Phase 4 — Image Extraction Service
- **File:** `tests/test_phase4.py` & `PHASE4_TESTING.md` *(create when implementing)*
- **Covers:** Image cropping, whitespace trimming, thumbnail generation
- **Tests:** *(to be determined)*

### Phase 5 — Structure Parser
- **File:** `tests/test_phase5.py` & `PHASE5_TESTING.md` *(create when implementing)*
- **Covers:** Chapter detection, lesson hierarchy, exercise type parsing
- **Tests:** *(to be determined)*

### Phases 6-10
- Follow the same pattern as above
- Each phase has its own test_phaseX.py and PHASEX_TESTING.md

---

## Creating a New Phase

When implementing a new phase (e.g., Phase 3), follow these steps:

### 1. Create Standalone Test Script

Create `tests/test_phase3.py` with this structure:

```python
"""
Phase 3: Mathpix Fallback Service — Standalone Test
Run with: python tests/test_phase3.py
(No pytest required, uses mocks, no API calls)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def print_header(text):
    print(f"\n{text}")
    print("=" * 70)

def print_step(num, text):
    print(f"\n{num}️⃣  {text}...")

def print_ok(text=""):
    if text:
        print(f"✅ {text}")
    else:
        print("✅")

def print_error(text):
    print(f"❌ {text}")
    sys.exit(1)

# Test functions here...

async def main():
    print_header("PHASE 3: Mathpix Fallback Service — Test Suite")
    
    # Run tests...
    
    print_header("✅ ALL TESTS PASSED (without API calls)!")
    print("\n📊 SUMMARY:")
    # Show summary...

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Create Testing Guide

Create `app/docs/test/PHASE3_TESTING.md` with sections:
- Quick Start (standalone test command)
- Pytest Suite
- Manual Testing with Real Data
- Interactive Testing
- Checklist
- Troubleshooting
- Output Directories

**Template:**
```markdown
# Phase 3 Testing Guide — [Service Name]

## Quick Start

### 1️⃣ Standalone Test Script

```bash
python tests/test_phase3.py
```

## 2️⃣ Pytest Test Suite

```bash
pytest tests/test_phase3.py -v
```

... (rest of sections)
```

### 3. Run and Verify

```bash
# Test standalone
python tests/test_phase3.py

# Test with pytest
pytest tests/test_phase3.py -v

# Update main README.md with phase info
```

---

## Documentation Checklist for Each Phase

- [ ] Create `tests/test_phaseX.py` with standalone tests
- [ ] Create `app/docs/test/PHASEX_TESTING.md` with guide
- [ ] Run both test methods successfully
- [ ] Update main `README.md` with testing info for new phase
- [ ] Verify path: `python tests/test_phaseX.py` works
- [ ] Verify pytest: `pytest tests/test_phaseX.py -v` works
- [ ] Add phase to this TESTING_PATTERN.md file

---

## Example: Running All Tests

```bash
# Run all phases
python tests/test_phase1.py
python tests/test_phase2.py
python tests/test_phase3.py
python tests/test_phase4.py
python tests/test_phase5.py
# ... and so on

# Or with pytest
pytest tests/ -v --tb=short

# Or with coverage
pytest tests/ --cov=app.services --cov-report=term-missing
```

---

## Best Practices

### ✅ DO:
- Use mocks for external services (Gemini, Mathpix, etc.)
- Make tests standalone (no API keys required)
- Keep tests fast (< 1 second per test)
- Use descriptive output with emoji checkmarks
- Document expected output in PHASEX_TESTING.md
- Update path references in docs when files move

### ❌ DON'T:
- Call real APIs in tests (no real API keys)
- Add heavy dependencies to test files
- Make tests slower than development cycles
- Leave outdated paths in documentation
- Skip creating PHASEX_TESTING.md files

---

## Quick Reference

| Phase | Status | Standalone | Pytest | Docs |
|-------|--------|-----------|--------|------|
| Phase 1 | ✅ | `python tests/test_phase1.py` | ✅ | ✅ PHASE1_TESTING.md |
| Phase 2 | ✅ | `python tests/test_phase2.py` | ✅ | ✅ PHASE2_TESTING.md |
| Phase 3 | ✅ | `python tests/test_phase3.py` | ✅ | ✅ PHASE3_TESTING.md |
| Phase 4 | 🔲 | TBD | TBD | TBD |
| Phase 5 | 🔲 | TBD | TBD | TBD |
| ... | ... | ... | ... | ... |

---

**Last Updated:** May 1, 2026  
**Total Phases:** 10  
**Phases Implemented:** 3
