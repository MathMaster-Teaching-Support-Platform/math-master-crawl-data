"""
Phase 4: Image Extraction Service — Standalone Test
Run with: python tests/test_phase4.py
(No pytest required, uses mocks, no API calls)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shutil
from PIL import Image, ImageDraw


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


# =============================================================================
# Test 1: Import and Initialization
# =============================================================================

def test_import_and_init():
    print_step(1, "Import ImageExtractor and initialize")
    try:
        from app.services.image_service import ImageExtractor, ImageResult, image_extractor

        assert ImageExtractor is not None
        print_ok("ImageExtractor imported")

        assert ImageResult is not None
        print_ok("ImageResult dataclass imported")

        assert image_extractor is not None
        print_ok("image_extractor singleton created")

        # Verify it's actually an ImageExtractor instance
        assert isinstance(image_extractor, ImageExtractor)
        print_ok("Singleton is ImageExtractor instance")

    except Exception as e:
        print_error(f"Failed: {e}")


# =============================================================================
# Test 2: Create Test Fixtures
# =============================================================================

def create_test_image(width=400, height=600, filename="page_test.jpg"):
    """Create a test JPEG image with colored rectangles."""
    test_dir = "data/books/test/pages"
    os.makedirs(test_dir, exist_ok=True)

    # Create base image (white)
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # Draw some colored rectangles (simulating figures)
    draw.rectangle([40, 180, 280, 480], fill="lightblue", outline="black", width=2)
    draw.text((60, 200), "Figure 1", fill="black")

    draw.rectangle([300, 100, 380, 200], fill="lightcoral", outline="black", width=2)
    draw.text((310, 120), "Fig 2", fill="black")

    filepath = os.path.join(test_dir, filename)
    img.save(filepath, "JPEG", quality=85)
    return filepath


def test_fixtures():
    print_step(2, "Create test image fixtures")
    try:
        path = create_test_image(400, 600, "page_001.jpg")
        assert os.path.exists(path)
        print_ok(f"Test image created: {path}")

        # Verify image dimensions
        with Image.open(path) as img:
            w, h = img.size
            assert w == 400 and h == 600
            print_ok(f"Image size verified: {w}x{h}")

    except Exception as e:
        print_error(f"Failed: {e}")


# =============================================================================
# Test 3: BBox Conversion (Relative to Pixel)
# =============================================================================

def test_bbox_conversion():
    print_step(3, "Test bbox_relative_to_pixel conversion")
    try:
        from app.services.image_service import ImageExtractor

        img_w, img_h = 400, 600

        # Test case 1: Simple conversion
        bbox_rel = [0.1, 0.3, 0.7, 0.8]
        result = ImageExtractor._bbox_relative_to_pixel(bbox_rel, img_w, img_h)
        expected = (40, 180, 280, 480)
        assert result == expected, f"Expected {expected}, got {result}"
        print_ok(f"Simple conversion: {bbox_rel} → {result}")

        # Test case 2: Out of bounds (should clamp)
        bbox_rel = [-0.1, -0.1, 1.5, 1.5]
        result = ImageExtractor._bbox_relative_to_pixel(bbox_rel, img_w, img_h)
        assert result == (0, 0, 400, 600)
        print_ok(f"Clamping: {bbox_rel} → {result}")

        # Test case 3: Swapped coordinates (should handle)
        bbox_rel = [0.7, 0.8, 0.1, 0.3]  # x1 > x2, y1 > y2
        result = ImageExtractor._bbox_relative_to_pixel(bbox_rel, img_w, img_h)
        x1, y1, x2, y2 = result
        assert x1 < x2 and y1 < y2
        print_ok(f"Swapped coords handled: {result}")

        # Test case 4: Edge values
        bbox_rel = [0.0, 0.0, 1.0, 1.0]
        result = ImageExtractor._bbox_relative_to_pixel(bbox_rel, img_w, img_h)
        assert result == (0, 0, 400, 600)
        print_ok(f"Full image: {result}")

    except Exception as e:
        print_error(f"Failed: {e}")


# =============================================================================
# Test 4: Skip Small Figures
# =============================================================================

def test_skip_if_too_small():
    print_step(4, "Test skip_if_too_small filtering")
    try:
        from app.services.image_service import ImageExtractor

        # Test case 1: Too small (width < 50)
        bbox = (10, 10, 40, 100)
        assert ImageExtractor._skip_if_too_small(bbox) == True
        print_ok("Skip: width < 50")

        # Test case 2: Too small (height < 50)
        bbox = (10, 10, 100, 40)
        assert ImageExtractor._skip_if_too_small(bbox) == True
        print_ok("Skip: height < 50")

        # Test case 3: OK (exactly 50x50)
        bbox = (10, 10, 60, 60)
        assert ImageExtractor._skip_if_too_small(bbox) == False
        print_ok("Keep: 50x50")

        # Test case 4: OK (larger)
        bbox = (10, 10, 200, 300)
        assert ImageExtractor._skip_if_too_small(bbox) == False
        print_ok("Keep: 190x290")

    except Exception as e:
        print_error(f"Failed: {e}")


# =============================================================================
# Test 5: Cleanup Figure (Whitespace Trimming)
# =============================================================================

def test_cleanup_figure():
    print_step(5, "Test cleanup_figure whitespace trimming")
    try:
        from app.services.image_service import ImageExtractor

        # Create image with whitespace padding
        img = Image.new("RGB", (200, 200), "white")
        draw = ImageDraw.Draw(img)

        # Draw content in the middle with 20px padding
        draw.rectangle([20, 20, 180, 180], fill="lightblue", outline="black")

        # Cleanup
        cleaned = ImageExtractor._cleanup_figure(img)
        w, h = cleaned.size

        # Should trim most of the white padding
        assert w < 200 and h < 200
        print_ok(f"Trimmed {200}x{200} → {w}x{h}")

        # Test case 2: No whitespace
        img_solid = Image.new("RGB", (100, 100), "red")
        cleaned = ImageExtractor._cleanup_figure(img_solid)
        assert cleaned.size == (100, 100)
        print_ok("No-trim (solid color): 100x100 → 100x100")

        # Test case 3: All white (should return as-is)
        img_white = Image.new("RGB", (100, 100), "white")
        cleaned = ImageExtractor._cleanup_figure(img_white)
        assert cleaned.size == (100, 100)
        print_ok("All-white: 100x100 → 100x100")

    except Exception as e:
        print_error(f"Failed: {e}")


# =============================================================================
# Test 6: Generate Thumbnail
# =============================================================================

def test_generate_thumbnail():
    print_step(6, "Test generate_thumbnail creation")
    try:
        from app.services.image_service import image_extractor

        # Create test image
        img_path = "data/books/test/pages/page_thumb_test.jpg"
        os.makedirs(os.path.dirname(img_path), exist_ok=True)

        img = Image.new("RGB", (800, 600), "lightgreen")
        img.save(img_path, "JPEG", quality=85)
        print_ok(f"Test image created: {img_path}")

        # Generate thumbnail
        thumb_path = image_extractor.generate_thumbnail(img_path, max_size=300)
        assert os.path.exists(thumb_path)
        print_ok(f"Thumbnail created: {thumb_path}")

        # Verify thumbnail dimensions
        with Image.open(thumb_path) as thumb:
            w, h = thumb.size
            assert w <= 300 and h <= 300
            print_ok(f"Thumbnail size: {w}x{h} (max 300)")

            # Verify aspect ratio preserved
            orig_ratio = 800 / 600
            thumb_ratio = w / h
            assert abs(orig_ratio - thumb_ratio) < 0.01
            print_ok(f"Aspect ratio preserved: {orig_ratio:.2f} ≈ {thumb_ratio:.2f}")

        # Cleanup
        os.remove(img_path)
        if os.path.exists(thumb_path):
            os.remove(thumb_path)

    except Exception as e:
        print_error(f"Failed: {e}")


# =============================================================================
# Test 7: Extract and Store Full Flow
# =============================================================================

def test_extract_and_store():
    print_step(7, "Test extract_and_store full flow")
    try:
        from app.services.image_service import image_extractor

        # Create test image
        img_path = create_test_image(400, 600, "page_007.jpg")

        # Extract figure
        result = image_extractor.extract_and_store(
            page_image_path=img_path,
            bbox_relative=[0.1, 0.3, 0.7, 0.8],
            book_id="test_book",
            page_num=7,
            fig_index=0,
            caption="Test Figure",
        )

        assert result is not None
        print_ok("Result returned (not None)")

        # Verify all fields
        assert result.file_path
        print_ok(f"file_path: {result.file_path}")

        assert result.url == "/static/images/test_book/page_007_fig_00.jpg"
        print_ok(f"url: {result.url}")

        assert result.thumbnail_url == "/static/images/test_book/thumbs/page_007_fig_00_thumb.jpg"
        print_ok(f"thumbnail_url: {result.thumbnail_url}")

        assert result.width > 0 and result.height > 0
        print_ok(f"dimensions: {result.width}x{result.height}")

        assert result.page_num == 7
        print_ok(f"page_num: {result.page_num}")

        assert result.fig_index == 0
        print_ok(f"fig_index: {result.fig_index}")

        assert result.caption == "Test Figure"
        print_ok(f"caption: {result.caption}")

        assert result.file_size_kb > 0
        print_ok(f"file_size_kb: {result.file_size_kb:.2f}")

        # Verify files exist
        assert os.path.exists(result.file_path)
        print_ok("Main image file exists")

        thumb_path = result.thumbnail_url.replace("/static/", "storage/")
        assert os.path.exists(thumb_path)
        print_ok("Thumbnail file exists")

    except Exception as e:
        print_error(f"Failed: {e}")


# =============================================================================
# Test 8: Skip Small Figures in Extract
# =============================================================================

def test_skip_small_in_extract():
    print_step(8, "Test that small figures are skipped in extract_and_store")
    try:
        from app.services.image_service import image_extractor

        img_path = create_test_image(400, 600, "page_008.jpg")

        # Try to extract a tiny region (will be skipped)
        result = image_extractor.extract_and_store(
            page_image_path=img_path,
            bbox_relative=[0.0, 0.0, 0.05, 0.05],  # 20x30 px — too small
            book_id="test_book",
            page_num=8,
            fig_index=0,
        )

        assert result is None
        print_ok("Tiny figure (20x30) correctly skipped")

        # Extract a larger region (will succeed)
        result = image_extractor.extract_and_store(
            page_image_path=img_path,
            bbox_relative=[0.1, 0.3, 0.7, 0.8],  # ~240x300 px
            book_id="test_book",
            page_num=8,
            fig_index=1,
        )

        assert result is not None
        print_ok("Larger figure extracted successfully")

    except Exception as e:
        print_error(f"Failed: {e}")


# =============================================================================
# Test 9: Multiple Figures from Same Page
# =============================================================================

def test_multiple_figures():
    print_step(9, "Test extracting multiple figures from same page")
    try:
        from app.services.image_service import image_extractor

        img_path = create_test_image(400, 600, "page_009.jpg")

        results = []
        for fig_idx, bbox_rel in enumerate([
            [0.0, 0.0, 0.5, 0.5],    # fig 0
            [0.5, 0.0, 1.0, 0.5],    # fig 1
            [0.0, 0.5, 1.0, 1.0],    # fig 2
        ]):
            result = image_extractor.extract_and_store(
                page_image_path=img_path,
                bbox_relative=bbox_rel,
                book_id="test_book_multi",
                page_num=9,
                fig_index=fig_idx,
            )
            if result:
                results.append(result)

        assert len(results) == 3
        print_ok(f"Extracted {len(results)} figures")

        # Verify all have correct fig_index
        for i, r in enumerate(results):
            assert r.fig_index == i
        print_ok("All fig_index values correct")

        # Verify URLs are unique
        urls = [r.url for r in results]
        assert len(urls) == len(set(urls))
        print_ok("All URLs are unique")

    except Exception as e:
        print_error(f"Failed: {e}")


# =============================================================================
# Test 10: ImageResult Dataclass
# =============================================================================

def test_image_result_dataclass():
    print_step(10, "Test ImageResult dataclass")
    try:
        from app.services.image_service import ImageResult

        result = ImageResult(
            file_path="/path/to/image.jpg",
            url="/static/images/book/page_001_fig_00.jpg",
            thumbnail_url="/static/images/book/thumbs/page_001_fig_00_thumb.jpg",
            width=240,
            height=300,
            caption="Test Figure",
            page_num=1,
            fig_index=0,
            file_size_kb=12.5,
        )

        assert result.file_path == "/path/to/image.jpg"
        print_ok("file_path field works")

        assert result.url == "/static/images/book/page_001_fig_00.jpg"
        print_ok("url field works")

        assert result.width == 240 and result.height == 300
        print_ok("dimensions fields work")

        # Verify can be converted to dict
        result_dict = result.__dict__
        assert len(result_dict) == 9
        print_ok(f"Dataclass converts to dict with {len(result_dict)} fields")

    except Exception as e:
        print_error(f"Failed: {e}")


# =============================================================================
# Cleanup
# =============================================================================

def cleanup():
    """Remove test directories."""
    test_dir = "storage/images"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
        print("✅ Cleaned up storage/images/")


# =============================================================================
# Main
# =============================================================================

async def main():
    print_header("PHASE 4: Image Extraction Service — Test Suite")
    print("All tests use local fixtures (no API calls)")

    try:
        test_import_and_init()
        test_fixtures()
        test_bbox_conversion()
        test_skip_if_too_small()
        test_cleanup_figure()
        test_generate_thumbnail()
        test_extract_and_store()
        test_skip_small_in_extract()
        test_multiple_figures()
        test_image_result_dataclass()

        print_header("✅ ALL 10 TESTS PASSED!")

        print("\n📊 SUMMARY:")
        print("  ✅ ImageExtractor import & singleton")
        print("  ✅ Test fixtures creation")
        print("  ✅ BBox relative→pixel conversion with clamping")
        print("  ✅ Skip small figures (< 50×50 px)")
        print("  ✅ Whitespace cleanup/trimming")
        print("  ✅ Thumbnail generation (LANCZOS, max 300px)")
        print("  ✅ Full extract_and_store flow")
        print("  ✅ Proper skipping of tiny figures")
        print("  ✅ Multiple figures from same page")
        print("  ✅ ImageResult dataclass validation")

        print("\n📁 Output directories created:")
        print("  - storage/images/{book_id}/page_XXX_fig_XX.jpg")
        print("  - storage/images/{book_id}/thumbs/page_XXX_fig_XX_thumb.jpg")

        print("\n⏭️  Next: Phase 5 — Structure Parser")

    except Exception as e:
        print_error(f"Unexpected error: {e}")
    finally:
        cleanup()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
