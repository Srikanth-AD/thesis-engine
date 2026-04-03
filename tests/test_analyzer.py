"""Tests for analyzer.py core functions."""
from unittest.mock import patch

from analyzer import (
    extract_subject,
    is_weekend,
    should_alert,
)


class TestShouldAlert:
    def test_urgent_yes(self):
        assert should_alert("URGENT ALERT NEEDED? YES\nSome reason") is True

    def test_urgent_no(self):
        assert should_alert("URGENT ALERT NEEDED? NO") is False

    def test_case_insensitive(self):
        assert should_alert("urgent alert needed? yes") is True

    def test_no_mention(self):
        assert should_alert("Everything looks fine, thesis intact.") is False


class TestExtractSubject:
    def test_extracts_next_line(self):
        response = "URGENT ALERT NEEDED? YES\nPLTR thesis broken — insider selling accelerated"
        subject = extract_subject(response)
        assert "PLTR" in subject
        assert "insider selling" in subject

    def test_fallback_when_no_subject(self):
        response = "URGENT ALERT NEEDED? YES\n"
        subject = extract_subject(response)
        assert "Portfolio Alert" in subject

    def test_includes_date(self):
        response = "URGENT ALERT NEEDED? YES\nSomething happened"
        subject = extract_subject(response)
        assert subject.startswith("[ALERT]")


class TestIsWeekend:
    @patch("analyzer.datetime")
    def test_saturday(self, mock_dt):
        mock_dt.now.return_value.weekday.return_value = 5
        assert is_weekend() is True

    @patch("analyzer.datetime")
    def test_monday(self, mock_dt):
        mock_dt.now.return_value.weekday.return_value = 0
        assert is_weekend() is False
