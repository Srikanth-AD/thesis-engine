"""Tests for Reddit sentiment scoring."""
from modules.reddit import _sentiment_score


class TestRedditSentiment:
    def test_bullish(self):
        assert _sentiment_score("I'm buying more, this stock is going to the moon") == "bullish"

    def test_bearish(self):
        assert _sentiment_score("This is a fraud, short it, puts printing") == "bearish"

    def test_neutral(self):
        assert _sentiment_score("What do you think about this stock?") == "neutral"

    def test_mixed_leans_bullish(self):
        assert _sentiment_score("Bullish on the growth story, buying calls") == "bullish"

    def test_empty(self):
        assert _sentiment_score("") == "neutral"

    def test_squeeze_is_bullish(self):
        assert _sentiment_score("short squeeze incoming, hold strong") == "bullish"
