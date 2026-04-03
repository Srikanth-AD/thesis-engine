"""Tests for RSS news sentiment scoring."""
from modules.news_rss import _sentiment


class TestSentiment:
    def test_positive(self):
        assert _sentiment("PLTR beats earnings estimates, stock surges") == "positive"

    def test_negative(self):
        assert _sentiment("Stock drops on fraud investigation concerns") == "negative"

    def test_neutral(self):
        assert _sentiment("Company to present at industry conference") == "neutral"

    def test_mixed_leans_positive(self):
        assert _sentiment("Company beats revenue but cuts guidance") == "positive"

    def test_dilution_negative(self):
        assert _sentiment("Company announces dilution through share offering") == "negative"

    def test_empty_string(self):
        assert _sentiment("") == "neutral"

    def test_upgrade(self):
        assert _sentiment("Analyst upgrades stock with record price target") == "positive"

    def test_downgrade(self):
        assert _sentiment("Major downgrade as concern grows over loss") == "negative"
