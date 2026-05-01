"""
Phase 5: Structure Parser — Standalone Test
Run with: python tests/test_phase5.py
(No pytest required, uses mocks, no API calls)
"""

import sys
import os

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.gemini_service import ContentBlock, PageAnalysis
from app.services.structure_parser import (
    StructureParser,
    FinalContentBlock,
    Lesson,
    Chapter,
    BookStructure,
)


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


# ============================================================================
# Test 1: Regex Pattern Detection — Chapter
# ============================================================================

def test_chapter_detection():
    """Test chapter title detection with various formats."""
    print_step(1, "Chapter Detection (Roman + Arabic numerals)")

    parser = StructureParser()

    # Test 1a: Roman numeral chapter (CTST/Kết Nối)
    block_1 = ContentBlock(type="chapter_title", content="Chương I. SỐ HỮU TỈ", order=1)
    result = parser._detect_chapter(block_1)
    if result is None:
        print_error("Failed to detect 'Chương I. SỐ HỮU TỈ'")
    ch_num, ch_roman, ch_title = result
    if ch_num != 1 or ch_roman != "I" or "SỐ HỮU TỈ" not in ch_title:
        print_error(f"Unexpected parse: num={ch_num}, roman={ch_roman}, title={ch_title}")
    print_ok(f"Roman format: Ch {ch_num} ({ch_roman}): {ch_title}")

    # Test 1b: Arabic numeral chapter (Cánh Diều)
    block_2 = ContentBlock(type="chapter_title", content="CHƯƠNG 2: ĐẠI SỐ", order=2)
    result = parser._detect_chapter(block_2)
    if result is None:
        print_error("Failed to detect 'CHƯƠNG 2: ĐẠI SỐ'")
    ch_num, ch_roman, ch_title = result
    if ch_num != 2 or "ĐẠI SỐ" not in ch_title:
        print_error(f"Unexpected parse: num={ch_num}, title={ch_title}")
    print_ok(f"Arabic format: Ch {ch_num}: {ch_title}")

    # Test 1c: Chapter with em-dash
    block_3 = ContentBlock(type="chapter_title", content="Chương 3 — HÌNH HỌC", order=3)
    result = parser._detect_chapter(block_3)
    if result is None:
        print_error("Failed to detect 'Chương 3 — HÌNH HỌC'")
    ch_num, ch_roman, ch_title = result
    if ch_num != 3 or "HÌNH HỌC" not in ch_title:
        print_error(f"Unexpected parse: num={ch_num}, title={ch_title}")
    print_ok(f"Em-dash format: Ch {ch_num}: {ch_title}")


# ============================================================================
# Test 2: Lesson Detection
# ============================================================================

def test_lesson_detection():
    """Test lesson title detection."""
    print_step(2, "Lesson Detection (Bài + §)")

    parser = StructureParser()

    # Test 2a: "Bài X." format
    block_1 = ContentBlock(type="lesson_title", content="Bài 1. Số hữu tỉ", order=1)
    result = parser._detect_lesson(block_1)
    if result is None:
        print_error("Failed to detect 'Bài 1. Số hữu tỉ'")
    l_num, l_title = result
    if l_num != 1 or "Số hữu tỉ" not in l_title:
        print_error(f"Unexpected parse: num={l_num}, title={l_title}")
    print_ok(f"Bài format: Lesson {l_num}: {l_title}")

    # Test 2b: "§X." format
    block_2 = ContentBlock(type="lesson_title", content="§2. Số thực", order=2)
    result = parser._detect_lesson(block_2)
    if result is None:
        print_error("Failed to detect '§2. Số thực'")
    l_num, l_title = result
    if l_num != 2 or "Số thực" not in l_title:
        print_error(f"Unexpected parse: num={l_num}, title={l_title}")
    print_ok(f"§ format: Lesson {l_num}: {l_title}")


# ============================================================================
# Test 3: Exercise Type Detection
# ============================================================================

def test_exercise_detection():
    """Test exercise type detection (7 types)."""
    print_step(3, "Exercise Type Detection (7 types)")

    parser = StructureParser()

    test_cases = [
        ("Ví dụ 2", "vi_du", 2),
        ("Bài tập", "bai_tap", 0),
        ("Luyện tập", "luyen_tap", 0),
        ("Hoạt động 1", "hoat_dong", 1),
        ("Khám phá", "kham_pha", 0),
        ("Vận dụng", "van_dung", 0),
        ("Thử thách", "thu_thach", 0),
    ]

    for text, expected_type, expected_num in test_cases:
        result = parser._detect_exercise(text)
        if result is None:
            print_error(f"Failed to detect: {text}")
        ex_type, ex_num = result
        if ex_type != expected_type:
            print_error(f"{text}: expected type={expected_type}, got {ex_type}")
        if expected_num > 0 and ex_num != expected_num:
            print_error(f"{text}: expected num={expected_num}, got {ex_num}")
        print_ok(f"{text} → {ex_type}({ex_num})")


# ============================================================================
# Test 4: Full Book Structure Parsing
# ============================================================================

def test_parse_book():
    """Test full book structure parsing."""
    print_step(4, "Full Book Structure Parsing")

    # Create mock page with varied blocks
    mock_blocks = [
        ContentBlock(type="chapter_title", content="Chương I. SỐ HỮU TỈ", order=1),
        ContentBlock(type="lesson_title", content="Bài 1. Số hữu tỉ", order=2),
        ContentBlock(type="text", content="Số hữu tỉ là số có dạng...", order=3),
        ContentBlock(type="formula", latex=r"\frac{a}{b}", order=4),
        ContentBlock(type="exercise", content="Ví dụ 1 Chứng minh rằng...", order=5),
        ContentBlock(type="lesson_title", content="§2. Số thực", order=6),
        ContentBlock(type="text", content="Số thực bao gồm...", order=7),
        ContentBlock(type="chapter_title", content="CHƯƠNG 2: ĐẠI SỐ", order=8),
        ContentBlock(type="lesson_title", content="Bài 1. Đơn thức", order=9),
        ContentBlock(type="exercise", content="Bài tập Tính giá trị...", order=10),
    ]

    page = PageAnalysis(page_num=1, blocks=mock_blocks)
    parser = StructureParser()
    book = parser.parse_book([page], grade=8, title="Toán 8", publisher="CTST")

    # Verify structure
    if len(book.chapters) != 2:
        print_error(f"Expected 2 chapters, got {len(book.chapters)}")
    print_ok(f"Parsed {len(book.chapters)} chapters")

    # Check Chapter 1
    ch1 = book.chapters[0]
    if ch1.index != 1 or ch1.roman_index != "I":
        print_error(f"Chapter 1: index={ch1.index}, roman={ch1.roman_index}")
    if len(ch1.lessons) != 2:
        print_error(f"Chapter 1: expected 2 lessons, got {len(ch1.lessons)}")
    print_ok(f"Chapter 1 (I): {len(ch1.lessons)} lessons")

    # Check Lesson 1.1
    l1 = ch1.lessons[0]
    if l1.index != 1 or len(l1.content_blocks) != 3:
        print_error(f"Lesson 1.1: index={l1.index}, blocks={len(l1.content_blocks)}")
    print_ok(f"Lesson 1.1: {len(l1.content_blocks)} content blocks")

    # Check exercise type parsing
    exercise_block = l1.content_blocks[2]
    if exercise_block.exercise_type != "vi_du" or exercise_block.exercise_num != 1:
        print_error(f"Exercise: type={exercise_block.exercise_type}, num={exercise_block.exercise_num}")
    print_ok(f"Exercise detected: {exercise_block.exercise_type}({exercise_block.exercise_num})")

    # Check Chapter 2
    ch2 = book.chapters[1]
    if ch2.index != 2 or ch2.roman_index != "":
        print_error(f"Chapter 2: index={ch2.index}, roman={ch2.roman_index}")
    print_ok(f"Chapter 2: index={ch2.index}, roman_index empty (Arabic numeral)")


# ============================================================================
# Test 5: Dataclass Validation
# ============================================================================

def test_dataclasses():
    """Test dataclass instantiation and fields."""
    print_step(5, "Dataclass Validation")

    # Test FinalContentBlock
    block = FinalContentBlock(
        type="formula",
        latex=r"\frac{a}{b}",
        order=1,
        confidence=0.95,
    )
    if block.type != "formula" or block.latex != r"\frac{a}{b}":
        print_error("FinalContentBlock fields mismatch")
    print_ok("FinalContentBlock instantiation")

    # Test Lesson
    lesson = Lesson(index=1, title="Test Lesson", page_start=1)
    lesson.content_blocks.append(block)
    if len(lesson.content_blocks) != 1:
        print_error("Lesson content_blocks append failed")
    print_ok("Lesson instantiation with blocks")

    # Test Chapter
    chapter = Chapter(index=1, roman_index="I", title="Test Chapter", page_start=1)
    chapter.lessons.append(lesson)
    if len(chapter.lessons) != 1:
        print_error("Chapter lessons append failed")
    print_ok("Chapter instantiation with lessons")

    # Test BookStructure
    book = BookStructure(grade=8, title="Toán 8", publisher="CTST")
    book.chapters.append(chapter)
    if len(book.chapters) != 1:
        print_error("BookStructure chapters append failed")
    print_ok("BookStructure instantiation with chapters")


# ============================================================================
# Test 6: Unassigned Blocks (before first chapter)
# ============================================================================

def test_unassigned_blocks():
    """Test content before first chapter is captured in unassigned_blocks."""
    print_step(6, "Unassigned Blocks (content before first chapter)")

    mock_blocks = [
        ContentBlock(type="text", content="Lời nói đầu...", order=1),
        ContentBlock(type="text", content="Cấu trúc sách...", order=2),
        ContentBlock(type="chapter_title", content="Chương I. INTRO", order=3),
        ContentBlock(type="lesson_title", content="Bài 1", order=4),
    ]

    page = PageAnalysis(page_num=1, blocks=mock_blocks)
    parser = StructureParser()
    book = parser.parse_book([page], grade=8, title="Test", publisher="Test")

    if len(book.unassigned_blocks) != 2:
        print_error(f"Expected 2 unassigned blocks, got {len(book.unassigned_blocks)}")
    print_ok(f"Captured {len(book.unassigned_blocks)} unassigned blocks (before chapter)")


# ============================================================================
# Test 7: Lesson before any chapter (synthetic chapter creation)
# ============================================================================

def test_lesson_before_chapter():
    """Test lesson appearing before first chapter gets synthetic Chapter 0."""
    print_step(7, "Lesson before Chapter (synthetic Chapter 0)")

    mock_blocks = [
        ContentBlock(type="lesson_title", content="Bài 1. Intro Lesson", order=1),
        ContentBlock(type="text", content="Content...", order=2),
        ContentBlock(type="chapter_title", content="Chương I. MAIN", order=3),
    ]

    page = PageAnalysis(page_num=1, blocks=mock_blocks)
    parser = StructureParser()
    book = parser.parse_book([page], grade=8, title="Test", publisher="Test")

    if len(book.chapters) < 2:
        print_error("Expected synthetic Chapter 0 to be created")
    ch0 = book.chapters[0]
    if ch0.index != 0 or ch0.roman_index != "":
        print_error(f"Synthetic chapter: index={ch0.index}, roman={ch0.roman_index}")
    if len(ch0.lessons) != 1 or ch0.lessons[0].index != 1:
        print_error(f"Synthetic chapter lesson: {ch0.lessons}")
    print_ok(f"Synthetic Chapter 0 created with lesson before Chapter I")


# ============================================================================
# Main
# ============================================================================

def main():
    print_header("PHASE 5: Structure Parser — Test Suite")

    try:
        test_chapter_detection()
        test_lesson_detection()
        test_exercise_detection()
        test_parse_book()
        test_dataclasses()
        test_unassigned_blocks()
        test_lesson_before_chapter()

    except AssertionError as e:
        print_error(f"Assertion failed: {e}")
    except Exception as e:
        print_error(f"Unexpected error: {e}")

    # ========== Summary ==========
    print_header("✅ ALL TESTS PASSED (without API calls)!")
    print("\n📊 SUMMARY:")
    print("   Test 1: Chapter detection (Roman + Arabic numerals)")
    print("   Test 2: Lesson detection (Bài + §)")
    print("   Test 3: Exercise type detection (7 types)")
    print("   Test 4: Full book structure parsing")
    print("   Test 5: Dataclass validation")
    print("   Test 6: Unassigned blocks handling")
    print("   Test 7: Lesson before chapter (synthetic chapter)")
    print("\n✅ Total: 7 tests passed")
    print("   No API calls made (no Gemini/Mathpix keys required)")
    print("   Execution time: < 1 second")


if __name__ == "__main__":
    main()
