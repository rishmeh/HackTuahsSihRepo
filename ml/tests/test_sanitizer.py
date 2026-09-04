"""
tests/test_sanitizer.py — Unit tests for the PII sanitizer.

Run with: pytest tests/test_sanitizer.py -v
"""

import pytest
from chat.sanitizer import sanitize


class TestRegexPatterns:
    def test_email_removed(self):
        result = sanitize("My email is john.doe@school.edu please reply")
        assert "john.doe@school.edu" not in result.sanitized_text
        assert result.pii_detected is True

    def test_phone_number_removed(self):
        result = sanitize("Call me at +1 555-867-5309")
        assert "867-5309" not in result.sanitized_text
        assert result.pii_detected is True

    def test_name_mention_removed(self):
        result = sanitize("My name is Alice Johnson and I have a question")
        assert "Alice Johnson" not in result.sanitized_text

    def test_age_mention_removed(self):
        result = sanitize("I am 9 years old and I want to know about dinosaurs")
        assert "9 years old" not in result.sanitized_text

    def test_address_removed(self):
        result = sanitize("I live at 123 Maple Street in Springfield")
        assert "123 Maple Street" not in result.sanitized_text

    def test_clean_text_unchanged(self):
        query = "What is photosynthesis?"
        result = sanitize(query)
        assert result.sanitized_text == query
        assert result.pii_detected is False

    def test_multiple_pii_removed(self):
        result = sanitize(
            "Hi, I'm Bob aged 10, my email is bob@school.org, "
            "and I live at 45 Oak Avenue."
        )
        assert result.pii_detected is True
        assert len(result.removed_entities) >= 2

    def test_empty_string(self):
        result = sanitize("")
        assert result.sanitized_text == ""
        assert result.pii_detected is False

    def test_no_crash_on_unicode(self):
        result = sanitize("¿Cómo se llama? My name is Sofía López")
        # Should not raise; may or may not detect NER depending on spaCy model
        assert isinstance(result.sanitized_text, str)
