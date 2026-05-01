# Structure parser — Chapter/Lesson rule engine — Phase 5
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.gemini_service import ContentBlock, PageAnalysis
from app.services.image_service import ImageResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

_CHAPTER_PATTERNS = [
    # CTST, Kết Nối: "Chương I.", "CHƯƠNG 2:", "Chương III"
    re.compile(r"^(CHƯƠNG|Chương)\s+([IVXivx]+|\d+)[.:\s]?\s*(.*)$", re.UNICODE),
    # Cánh Diều: "Chương 1 —"
    re.compile(r"^(CHƯƠNG|Chương)\s+(\d+)\s*[—–\-]\s*(.*)$", re.UNICODE),
]

_LESSON_PATTERNS = [
    # "Bài 1.", "Bài 2:", "BÀI 3"
    re.compile(r"^(BÀI|Bài)\s+(\d+)[.:\s]?\s*(.*)$", re.UNICODE),
    # "§1.", "§ 2:"
    re.compile(r"^§\s*(\d+)[.:\s]?\s*(.*)$", re.UNICODE),
    # "1.", "2." at start of line — last-resort fallback (short headings only)
    re.compile(r"^(\d+)\.\s+(.+)$", re.UNICODE),
]

_EXERCISE_PATTERNS: dict[str, re.Pattern] = {
    "vi_du":     re.compile(r"^(Ví dụ|VÍ DỤ)\s*(\d+)", re.UNICODE),
    "bai_tap":   re.compile(r"^(Bài tập|BÀI TẬP)", re.UNICODE),
    "luyen_tap": re.compile(r"^(Luyện tập|LUYỆN TẬP)", re.UNICODE),
    "hoat_dong": re.compile(r"^(Hoạt động|HOẠT ĐỘNG)\s*(\d+)", re.UNICODE),
    "kham_pha":  re.compile(r"^(Khám phá|KHÁM PHÁ)", re.UNICODE),
    "van_dung":  re.compile(r"^(Vận dụng|VẬN DỤNG)", re.UNICODE),
    "thu_thach": re.compile(r"^(Thử thách|THỬ THÁCH)", re.UNICODE),
}

# Roman numeral → integer (up to XII covers all common SGK chapters)
_ROMAN_TO_INT: dict[str, int] = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12,
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
    "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
    "xi": 11, "xii": 12,
}


def _roman_to_int(s: str) -> int:
    return _ROMAN_TO_INT.get(s.strip(), 0)


def _to_roman_upper(s: str) -> str:
    upper = s.strip().upper()
    return upper if upper in _ROMAN_TO_INT else s.strip()


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FinalContentBlock:
    type: str            # "text"|"formula"|"image"|"exercise"|"table"|"definition"|"note"
    content: str = ""
    latex: str = ""
    image_url: str = ""
    thumbnail_url: str = ""
    caption: str = ""
    exercise_type: str = ""   # "vi_du"|"bai_tap"|"luyen_tap"|... when type==exercise
    exercise_num: int = 0
    order: int = 0
    confidence: float = 1.0
    source: str = "gemini"    # "gemini" | "mathpix"


@dataclass
class Lesson:
    index: int
    title: str
    page_start: int
    content_blocks: list[FinalContentBlock] = field(default_factory=list)


@dataclass
class Chapter:
    index: int         # integer order (1, 2, 3 …)
    roman_index: str   # "I", "II", "III" if present, else ""
    title: str
    page_start: int
    lessons: list[Lesson] = field(default_factory=list)


@dataclass
class BookStructure:
    grade: int
    title: str
    publisher: str
    chapters: list[Chapter] = field(default_factory=list)
    unassigned_blocks: list[FinalContentBlock] = field(default_factory=list)


# ---------------------------------------------------------------------------
# StructureParser
# ---------------------------------------------------------------------------

class StructureParser:
    """
    Converts a flat list of ``PageAnalysis`` objects (from Gemini) into a
    hierarchical ``BookStructure`` (Book → Chapter → Lesson → Blocks).

    Priority rule:
    - Gemini labels (``chapter_title``, ``lesson_title``) are used directly.
    - Regex patterns are the safety net for ``text`` blocks that contain
      structural markers Gemini may have missed.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_book(
        self,
        pages: list[PageAnalysis],
        grade: int,
        title: str,
        publisher: str = "",
        # Optional map: (page_num, block_order) → ImageResult
        image_results: Optional[dict[tuple[int, int], ImageResult]] = None,
    ) -> BookStructure:
        """Parse all pages into a BookStructure tree."""
        image_results = image_results or {}

        book = BookStructure(grade=grade, title=title, publisher=publisher)

        current_chapter: Optional[Chapter] = None
        current_lesson: Optional[Lesson] = None
        global_order = 0  # running order counter across the whole book

        for page in pages:
            for block in sorted(page.blocks, key=lambda b: b.order):
                global_order += 1
                text = (block.content or "").strip()

                # ---- 1. Chapter detection --------------------------------
                chapter_info = self._detect_chapter(block)
                if chapter_info is not None:
                    ch_num, ch_roman, ch_title = chapter_info
                    current_chapter = Chapter(
                        index=ch_num,
                        roman_index=ch_roman,
                        title=ch_title,
                        page_start=page.page_num,
                    )
                    book.chapters.append(current_chapter)
                    current_lesson = None
                    logger.debug("Chapter %d (%s): %s", ch_num, ch_roman, ch_title)
                    continue  # structural — not added as content block

                # ---- 2. Lesson detection ---------------------------------
                lesson_info = self._detect_lesson(block)
                if lesson_info is not None:
                    l_num, l_title = lesson_info
                    current_lesson = Lesson(
                        index=l_num,
                        title=l_title,
                        page_start=page.page_num,
                    )
                    if current_chapter is not None:
                        current_chapter.lessons.append(current_lesson)
                    else:
                        # Lesson before any chapter — create a synthetic chapter 0
                        synthetic = Chapter(
                            index=0, roman_index="", title="", page_start=page.page_num
                        )
                        book.chapters.append(synthetic)
                        current_chapter = synthetic
                        current_chapter.lessons.append(current_lesson)
                    logger.debug("  Lesson %d: %s", l_num, l_title)
                    continue  # structural — not added as content block

                # ---- 3. Content block ------------------------------------
                img_result = image_results.get((page.page_num, block.order))
                final_block = self._convert_block(block, img_result, global_order)

                if current_lesson is not None:
                    current_lesson.content_blocks.append(final_block)
                elif current_chapter is not None:
                    # Content between chapter title and first lesson
                    if not current_chapter.lessons:
                        current_chapter.lessons.append(
                            Lesson(index=0, title="", page_start=page.page_num)
                        )
                    current_chapter.lessons[-1].content_blocks.append(final_block)
                else:
                    book.unassigned_blocks.append(final_block)

        logger.info(
            "Parsed: %d chapters, %d unassigned blocks",
            len(book.chapters),
            len(book.unassigned_blocks),
        )
        return book

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------

    def _detect_chapter(self, block: ContentBlock) -> Optional[tuple[int, str, str]]:
        """Return ``(chapter_num, roman_index, chapter_title)`` or ``None``.

        Gemini ``chapter_title`` labels are trusted directly; regex is the
        safety net for misclassified ``text`` blocks.
        """
        if block.type not in ("chapter_title", "text"):
            return None
        text = (block.content or "").strip()
        if not text:
            return None
        return self._parse_chapter_text(text)

    def _parse_chapter_text(self, text: str) -> Optional[tuple[int, str, str]]:
        for pat in _CHAPTER_PATTERNS:
            m = pat.match(text)
            if m is None:
                continue
            groups = m.groups()
            # groups[0] = keyword ("Chương"/"CHƯƠNG") — skip
            # groups[1] = number/roman
            # groups[2] = remaining title (may be empty string)
            raw_num = groups[1].strip()
            remaining = groups[2].strip() if len(groups) > 2 else ""

            if raw_num.isdigit():
                ch_int = int(raw_num)
                roman = ""
            else:
                roman = _to_roman_upper(raw_num)
                ch_int = _roman_to_int(raw_num)
                if ch_int == 0:
                    ch_int = len(raw_num)  # crude fallback

            return ch_int, roman, remaining
        return None

    def _detect_lesson(self, block: ContentBlock) -> Optional[tuple[int, str]]:
        """Return ``(lesson_num, lesson_title)`` or ``None``.

        Gemini ``lesson_title`` labels are trusted directly; regex is fallback.
        """
        if block.type not in ("lesson_title", "text"):
            return None
        text = (block.content or "").strip()
        if not text:
            return None

        if block.type == "lesson_title":
            result = self._parse_lesson_text(text)
            if result:
                return result
            # Gemini is confident — treat whole text as title even without regex match
            return 0, text

        # Safety net on text blocks — skip if it looks like a chapter instead
        if self._parse_chapter_text(text) is not None:
            return None

        return self._parse_lesson_text(text)

    def _parse_lesson_text(self, text: str) -> Optional[tuple[int, str]]:
        for i, pat in enumerate(_LESSON_PATTERNS):
            m = pat.match(text)
            if m is None:
                continue
            groups = m.groups()

            if i == 0:
                # ^(BÀI|Bài)\s+(\d+)[.:\s]?\s*(.*)$
                l_num = int(groups[1])
                l_title = groups[2].strip() if len(groups) > 2 else ""
            elif i == 1:
                # ^§\s*(\d+)[.:\s]?\s*(.*)$
                l_num = int(groups[0])
                l_title = groups[1].strip() if len(groups) > 1 else ""
            else:
                # ^(\d+)\.\s+(.+)$  — loose; skip long lines (numbered lists)
                if len(text) > 120:
                    return None
                l_num = int(groups[0])
                l_title = groups[1].strip()

            return l_num, l_title
        return None

    def _detect_exercise(self, text: str) -> Optional[tuple[str, int]]:
        """Return ``(exercise_type, exercise_num)`` or ``None``.

        ``exercise_num`` is 0 when the pattern carries no number.
        """
        for ex_type, pat in _EXERCISE_PATTERNS.items():
            m = pat.match(text.strip())
            if m is None:
                continue
            groups = m.groups()
            ex_num = 0
            if groups:
                last = groups[-1]
                if last and last.isdigit():
                    ex_num = int(last)
            return ex_type, ex_num
        return None

    # ------------------------------------------------------------------
    # Block conversion
    # ------------------------------------------------------------------

    def _convert_block(
        self,
        block: ContentBlock,
        image_result: Optional[ImageResult],
        order: int,
    ) -> FinalContentBlock:
        """Convert a Gemini ``ContentBlock`` into a ``FinalContentBlock``."""
        block_type = block.type
        # Structural types that somehow reach here are treated as plain text
        if block_type in ("chapter_title", "lesson_title"):
            block_type = "text"

        image_url = ""
        thumbnail_url = ""
        if image_result is not None:
            image_url = image_result.url
            thumbnail_url = image_result.thumbnail_url

        exercise_type = ""
        exercise_num = 0
        if block_type == "exercise":
            ex_info = self._detect_exercise((block.content or "").strip())
            if ex_info:
                exercise_type, exercise_num = ex_info

        return FinalContentBlock(
            type=block_type,
            content=block.content or "",
            latex=block.latex or "",
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            caption=block.caption or "",
            exercise_type=exercise_type,
            exercise_num=exercise_num,
            order=order,
            confidence=block.confidence,
            source="gemini",
        )
