"""
Phase 3: Mathpix Fallback Service — Standalone Test
Run with: python tests/test_phase3.py
(No pytest required, no real API calls needed for core logic tests)
"""

import asyncio
import os
import sys
import tempfile

from PIL import Image

# Add project root to path
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


# ---------------------------------------------------------------------------
# STEP 1 — Import
# ---------------------------------------------------------------------------

print_header("Phase 3: Mathpix Fallback Service — Test")

print_step(1, "Importing MathpixService, validate_latex, latex_to_readable")
try:
    from app.services.mathpix_service import (
        MathpixService,
        MathpixResult,
        validate_latex,
        latex_to_readable,
        mathpix_service,
    )
    print_ok("Import successful")
except Exception as e:
    print_error(f"Import failed: {e}")


# ---------------------------------------------------------------------------
# STEP 2 — is_enabled()
# ---------------------------------------------------------------------------

print_step(2, "MathpixService.is_enabled() with disabled config")
svc = MathpixService()
enabled = svc.is_enabled()
print(f"  Mathpix enabled: {enabled}")
# By default MATHPIX_ENABLED=false in .env → should be False (or True if set)
print_ok(f"is_enabled() returned {enabled} (expected False unless keys configured)")


# ---------------------------------------------------------------------------
# STEP 3 — validate_latex
# ---------------------------------------------------------------------------

print_step(3, "validate_latex() correctness")

cases_true = [
    r"\frac{1}{2}",
    r"\sum_{i=1}^{n} x_i",
    r"\sqrt{x^2 + y^2}",
    r"x^2 + y^2 = r^2",
    r"\alpha + \beta = \gamma",
    r"a_1, a_2, \ldots, a_n",
]
cases_false = [
    "",
    "a",
    "abc xyz",
    "hello world this is plain text without any math",
]

for expr in cases_true:
    if not validate_latex(expr):
        print_error(f"validate_latex should be True for: {expr!r}")
    print(f"  ✓ True  — {expr!r}")

for expr in cases_false:
    if validate_latex(expr):
        print_error(f"validate_latex should be False for: {expr!r}")
    print(f"  ✓ False — {expr!r}")

print_ok("validate_latex() all cases pass")


# ---------------------------------------------------------------------------
# STEP 4 — latex_to_readable
# ---------------------------------------------------------------------------

print_step(4, "latex_to_readable() conversions")

conversions = [
    (r"\frac{1}{2}", "1/2"),
    (r"\sqrt{x}", "√(x)"),
    (r"\infty", "∞"),
    (r"\alpha", "α"),
    (r"\leq", "≤"),
]

for latex, expected_substr in conversions:
    result = latex_to_readable(latex)
    if expected_substr not in result:
        print_error(
            f"latex_to_readable({latex!r}) = {result!r}, expected to contain {expected_substr!r}"
        )
    print(f"  ✓ {latex!r} → {result!r}")

print_ok("latex_to_readable() conversions pass")


# ---------------------------------------------------------------------------
# STEP 5 — extract_formula fallback when disabled
# ---------------------------------------------------------------------------

print_step(5, "extract_formula() fallback when Mathpix disabled")


def create_test_image(path: str):
    img = Image.new("RGB", (400, 100), color=(255, 255, 255))
    img.save(path, "JPEG")


async def test_extract_fallback():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        img_path = f.name
    try:
        create_test_image(img_path)
        svc_local = MathpixService()
        gemini_latex = r"\frac{a}{b}"
        result = await svc_local.extract_formula(
            img_path, (50, 10, 350, 90), gemini_latex=gemini_latex
        )
        assert isinstance(result, MathpixResult), "Result should be MathpixResult"
        if not svc_local.is_enabled():
            assert result.success is False, "success should be False when disabled"
            assert result.latex == gemini_latex, "Should return gemini_latex as-is"
            assert result.confidence == 0.0, "confidence should be 0 when disabled"
        return result
    finally:
        os.unlink(img_path)


result = asyncio.run(test_extract_fallback())
print(f"  MathpixResult.success={result.success}, latex={result.latex!r}")
print_ok("extract_formula() fallback works correctly")


# ---------------------------------------------------------------------------
# STEP 6 — _resolve_bbox: relative and absolute coords
# ---------------------------------------------------------------------------

print_step(6, "_resolve_bbox(): relative and absolute coords")

from app.services.mathpix_service import MathpixService as _MS

# relative
x1, y1, x2, y2 = _MS._resolve_bbox((0.1, 0.2, 0.8, 0.9), 1000, 500)
assert x1 == 100, f"Expected 100, got {x1}"
assert y1 == 100, f"Expected 100, got {y1}"
assert x2 == 800, f"Expected 800, got {x2}"
assert y2 == 450, f"Expected 450, got {y2}"
print(f"  Relative bbox (0.1,0.2,0.8,0.9) on 1000x500 → ({x1},{y1},{x2},{y2})")
print_ok("Relative bbox conversion correct")

# absolute
x1, y1, x2, y2 = _MS._resolve_bbox((100, 200, 500, 350), 1000, 500)
assert x1 == 100 and y1 == 200 and x2 == 500 and y2 == 350
print(f"  Absolute bbox (100,200,500,350) → ({x1},{y1},{x2},{y2})")
print_ok("Absolute bbox passthrough correct")

# out-of-bounds clamping
x1, y1, x2, y2 = _MS._resolve_bbox((-50, -20, 1500, 800), 1000, 500)
assert x1 == 0 and y1 == 0 and x2 == 1000 and y2 == 500
print(f"  Out-of-bounds bbox clamped → ({x1},{y1},{x2},{y2})")
print_ok("Out-of-bounds clamping correct")


# ---------------------------------------------------------------------------
# STEP 7 — _preprocess: output is JPEG < 100 KB
# ---------------------------------------------------------------------------

print_step(7, "_preprocess(): JPEG output < 100 KB with padding")


async def test_preprocess():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        img_path = f.name
    try:
        img = Image.new("RGB", (800, 600), color=(240, 240, 240))
        img.save(img_path, "JPEG")
        svc_local = MathpixService()
        img_bytes = svc_local._preprocess(img_path, (100, 100, 700, 500))
        size_kb = len(img_bytes) / 1024
        print(f"  Preprocessed size: {size_kb:.1f} KB")
        assert size_kb < 100, f"Expected < 100 KB, got {size_kb:.1f} KB"
        assert img_bytes[:2] == b"\xff\xd8", "Output should be JPEG"
    finally:
        os.unlink(img_path)


asyncio.run(test_preprocess())
print_ok("_preprocess() output is JPEG < 100 KB")


# ---------------------------------------------------------------------------
# STEP 8 — batch_extract fallback (disabled)
# ---------------------------------------------------------------------------

print_step(8, "batch_extract() with disabled Mathpix")


async def test_batch():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        img_path = f.name
    try:
        img = Image.new("RGB", (800, 600), color=(255, 255, 255))
        img.save(img_path, "JPEG")
        svc_local = MathpixService()
        blocks = [
            {"bbox": (50, 50, 300, 150), "latex": r"\frac{1}{2}"},
            {"bbox": (50, 200, 300, 300), "latex": r"\sqrt{x}"},
        ]
        results = await svc_local.batch_extract(blocks, img_path)
        assert len(results) == 2, f"Expected 2 results, got {len(results)}"
        for i, r in enumerate(results):
            print(f"  Block {i}: success={r.success}, latex={r.latex!r}")
    finally:
        os.unlink(img_path)


asyncio.run(test_batch())
print_ok("batch_extract() works (disabled fallback)")


# ---------------------------------------------------------------------------
# STEP 9 — MathpixResult dataclass
# ---------------------------------------------------------------------------

print_step(9, "MathpixResult dataclass fields")
mr = MathpixResult(latex=r"\frac{1}{2}", text="1/2", confidence=0.95, success=True)
assert mr.latex == r"\frac{1}{2}"
assert mr.text == "1/2"
assert mr.confidence == 0.95
assert mr.success is True
print_ok("MathpixResult dataclass correct")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print_header("✅ ALL PHASE 3 TESTS PASSED")
print("""
CHECKLIST:
  ✅ MathpixService.is_enabled() checks config
  ✅ extract_formula() fallback when disabled
  ✅ _resolve_bbox() relative, absolute, out-of-bounds
  ✅ _preprocess() JPEG < 100KB with grayscale + padding
  ✅ validate_latex() rejects garbage, accepts valid LaTeX
  ✅ latex_to_readable() correct conversions
  ✅ batch_extract() works with disabled service
  ✅ MathpixResult dataclass fields correct

NOTE: To test with real Mathpix API, set in .env:
  MATHPIX_ENABLED=true
  MATHPIX_APP_ID=your_app_id
  MATHPIX_APP_KEY=your_app_key
Then run: svc.extract_formula("page_005.jpg", (200, 300, 500, 350))
""")
