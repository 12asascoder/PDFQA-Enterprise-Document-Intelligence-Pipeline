"""
Tests for the TextCleaner module.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleaner.text_cleaner import TextCleaner
from config import PipelineConfig


@pytest.fixture
def cleaner() -> TextCleaner:
    return TextCleaner(PipelineConfig())


class TestTextCleaner:
    """Test individual cleaning transformations."""

    def test_unicode_normalization(self, cleaner: TextCleaner):
        """NFKC normalisation should unify characters."""
        # ﬁ (fi ligature, U+FB01) should become "fi"
        raw = "bene\ufb01t"
        result = cleaner.clean(raw)
        assert "benefit" in result

    def test_fix_broken_words(self, cleaner: TextCleaner):
        """Hyphenated line-end words should be rejoined."""
        raw = "pro-\ngramming is fun"
        result = cleaner.clean(raw)
        assert "programming" in result

    def test_normalize_whitespace(self, cleaner: TextCleaner):
        """Multiple spaces/tabs should collapse to single space."""
        raw = "hello    world\t\tfoo"
        result = cleaner.clean(raw)
        assert "hello world foo" in result

    def test_remove_page_numbers(self, cleaner: TextCleaner):
        """Standalone page-number lines should be removed."""
        raw = "Some text\n42\nMore text"
        result = cleaner.clean(raw)
        assert "42" not in result.split("\n")

    def test_remove_page_number_with_dash(self, cleaner: TextCleaner):
        """Page numbers with dashes like '— 5 —' should be removed."""
        raw = "Some text\n— 5 —\nMore text"
        result = cleaner.clean(raw)
        lines = [l.strip() for l in result.split("\n") if l.strip()]
        assert "— 5 —" not in lines

    def test_remove_repeated_headers(self, cleaner: TextCleaner):
        """Lines appearing on >40% of pages should be stripped."""
        pages = [
            "ACME Corp Annual Report\nContent page 1",
            "ACME Corp Annual Report\nContent page 2",
            "ACME Corp Annual Report\nContent page 3",
            "ACME Corp Annual Report\nContent page 4",
            "ACME Corp Annual Report\nContent page 5",
        ]
        raw = "\n\n".join(pages)
        result = cleaner.clean(raw, pages)
        # The repeated header should appear 0 or at most 1 time (cleaned)
        assert result.count("ACME Corp Annual Report") <= 1

    def test_remove_ocr_garbage(self, cleaner: TextCleaner):
        """Non-printable characters should be stripped."""
        raw = "Hello\x00\x01\x02World"
        result = cleaner.clean(raw)
        assert "HelloWorld" in result or "Hello World" in result

    def test_empty_input(self, cleaner: TextCleaner):
        """Empty strings should not crash."""
        assert cleaner.clean("") == ""
        assert cleaner.clean("   ") == ""

    def test_preserves_normal_text(self, cleaner: TextCleaner):
        """Normal text should pass through mostly unchanged."""
        raw = "The quick brown fox jumps over the lazy dog."
        result = cleaner.clean(raw)
        assert result == raw
