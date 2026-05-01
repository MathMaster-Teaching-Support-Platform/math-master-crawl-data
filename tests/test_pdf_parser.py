"""
Pytest tests for Phase 1: PDF Ingestion
Run with: pytest tests/test_pdf_parser.py -v
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from app.services.pdf_parser import (
    PageInfo,
    validate_pdf,
    render_pages,
    extract_pdf_metadata,
    check_image_size,
    _is_effectively_grayscale,
)


@pytest.fixture
def test_pdf_path():
    """Create a minimal test PDF."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except ImportError:
        pytest.skip("reportlab not installed")

    # Create temp PDF
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name

    c = canvas.Canvas(pdf_path, pagesize=letter)
    
    # Page 1
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, "Test Page 1")
    c.setFont("Helvetica", 12)
    c.drawString(50, 700, "This is a test page for PDF parsing.")
    c.showPage()
    
    # Page 2
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, "Test Page 2")
    c.drawString(50, 700, "Another test page.")
    c.showPage()
    
    c.save()
    
    yield pdf_path
    
    # Cleanup
    if os.path.exists(pdf_path):
        os.remove(pdf_path)


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestValidatePdf:
    """Test validate_pdf function."""
    
    def test_valid_pdf(self, test_pdf_path):
        """Test that a valid PDF is recognized."""
        assert validate_pdf(test_pdf_path) is True
    
    def test_invalid_pdf_nonexistent(self):
        """Test that nonexistent file returns False."""
        assert validate_pdf("nonexistent_file.pdf") is False
    
    def test_invalid_pdf_empty_file(self):
        """Test that empty file returns False."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            empty_path = f.name
            # Write nothing (empty file)
        
        try:
            assert validate_pdf(empty_path) is False
        finally:
            os.remove(empty_path)


class TestRenderPages:
    """Test render_pages function."""
    
    def test_render_creates_pages(self, test_pdf_path, temp_output_dir):
        """Test that render_pages creates correct files."""
        pages = render_pages(test_pdf_path, temp_output_dir)
        
        # Check count
        assert len(pages) == 2, "Expected 2 pages"
        
        # Check each page
        for page in pages:
            assert isinstance(page, PageInfo)
            assert page.page_num > 0
            assert os.path.exists(page.image_path)
            assert page.image_path.endswith(".jpg")
            assert page.file_size_kb > 0
            assert page.width > 0
            assert page.height > 0
            assert isinstance(page.is_grayscale, bool)
    
    def test_pages_in_correct_directory(self, test_pdf_path, temp_output_dir):
        """Test that pages are saved in correct directory."""
        pages = render_pages(test_pdf_path, temp_output_dir)
        
        expected_dir = os.path.join(temp_output_dir, "pages")
        for page in pages:
            assert page.image_path.startswith(expected_dir)
            assert f"page_{page.page_num:03d}.jpg" in page.image_path
    
    def test_page_numbering(self, test_pdf_path, temp_output_dir):
        """Test that page numbers are 1-based."""
        pages = render_pages(test_pdf_path, temp_output_dir)
        page_nums = [p.page_num for p in pages]
        
        assert page_nums == [1, 2]


class TestExtractPdfMetadata:
    """Test extract_pdf_metadata function."""
    
    def test_metadata_structure(self, test_pdf_path):
        """Test that metadata has required keys."""
        metadata = extract_pdf_metadata(test_pdf_path)
        
        assert "title" in metadata
        assert "author" in metadata
        assert "num_pages" in metadata
        assert "file_size_mb" in metadata
    
    def test_metadata_values(self, test_pdf_path):
        """Test that metadata values are correct."""
        metadata = extract_pdf_metadata(test_pdf_path)
        
        assert metadata["num_pages"] == 2
        assert isinstance(metadata["title"], str)
        assert isinstance(metadata["author"], str)
        assert isinstance(metadata["file_size_mb"], float)
        assert metadata["file_size_mb"] > 0


class TestCheckImageSize:
    """Test check_image_size function."""
    
    def test_size_info_structure(self, test_pdf_path, temp_output_dir):
        """Test that size info has required keys."""
        pages = render_pages(test_pdf_path, temp_output_dir)
        
        for page in pages:
            info = check_image_size(page.image_path)
            assert "path" in info
            assert "size_kb" in info
            assert "needs_compression" in info
    
    def test_compression_flag(self, test_pdf_path, temp_output_dir):
        """Test that compression flag is set correctly."""
        pages = render_pages(test_pdf_path, temp_output_dir)
        
        for page in pages:
            info = check_image_size(page.image_path)
            # Most test pages should be < 100KB
            if info["size_kb"] <= 100:
                assert info["needs_compression"] is False
            else:
                assert info["needs_compression"] is True
    
    def test_size_value(self, test_pdf_path, temp_output_dir):
        """Test that reported size matches actual file size."""
        pages = render_pages(test_pdf_path, temp_output_dir)
        
        for page in pages:
            info = check_image_size(page.image_path)
            actual_size = os.path.getsize(page.image_path) / 1024
            
            # Allow 0.1 KB difference due to rounding
            assert abs(info["size_kb"] - actual_size) < 0.1


class TestGrayscaleDetection:
    """Test _is_effectively_grayscale function."""
    
    def test_grayscale_detection(self):
        """Test that grayscale detection works."""
        from PIL import Image
        
        # Create a grayscale image
        gray_img = Image.new("RGB", (100, 100), (128, 128, 128))
        assert _is_effectively_grayscale(gray_img) is True
        
        # Create a color image
        color_img = Image.new("RGB", (100, 100), (255, 0, 0))
        assert _is_effectively_grayscale(color_img) is False


class TestIntegration:
    """Integration tests combining multiple functions."""
    
    def test_full_workflow(self, test_pdf_path, temp_output_dir):
        """Test complete workflow: validate → render → check sizes."""
        # Validate
        assert validate_pdf(test_pdf_path)
        
        # Get metadata
        metadata = extract_pdf_metadata(test_pdf_path)
        assert metadata["num_pages"] == 2
        
        # Render pages
        pages = render_pages(test_pdf_path, temp_output_dir)
        assert len(pages) == metadata["num_pages"]
        
        # Check all sizes
        for page in pages:
            info = check_image_size(page.image_path)
            # All pages should be successfully rendered
            assert info["size_kb"] > 0
