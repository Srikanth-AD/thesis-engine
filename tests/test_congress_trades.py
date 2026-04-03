"""Tests for congress trades -- dynamic sector-based committee relevance."""
from modules.congress_trades import _build_committee_ticker_map, _is_relevant_committee


def _make_portfolio(stocks):
    """Helper to create a minimal portfolio dict."""
    return {"portfolio": stocks}


class TestBuildCommitteeTickerMap:
    def test_defense_sector(self):
        portfolio = _make_portfolio([
            {"ticker": "LMT", "sector": "Defense / Aerospace", "thesis": "F-35 production ramp"},
        ])
        mapping = _build_committee_ticker_map(portfolio)
        assert "LMT" in mapping["armed services"]
        assert "LMT" in mapping["defense"]

    def test_ai_semiconductor(self):
        portfolio = _make_portfolio([
            {"ticker": "NVDA", "sector": "AI Semiconductors", "thesis": "GPU dominance"},
        ])
        mapping = _build_committee_ticker_map(portfolio)
        assert "NVDA" in mapping["technology"]
        assert "NVDA" in mapping["science"]

    def test_healthcare(self):
        portfolio = _make_portfolio([
            {"ticker": "ISRG", "sector": "Medical Device / Healthcare", "thesis": "surgical robotics"},
        ])
        mapping = _build_committee_ticker_map(portfolio)
        assert "ISRG" in mapping["health"]

    def test_no_portfolio(self):
        mapping = _build_committee_ticker_map(None)
        assert all(v == [] for v in mapping.values())

    def test_unrelated_sector(self):
        portfolio = _make_portfolio([
            {"ticker": "KO", "sector": "Consumer Beverages", "thesis": "brand moat"},
        ])
        mapping = _build_committee_ticker_map(portfolio)
        # KO shouldn't match any committee
        assert all("KO" not in v for v in mapping.values())


class TestIsRelevantCommittee:
    def test_relevant(self):
        mapping = {"armed services": ["LMT", "RTX"], "technology": ["NVDA"]}
        assert _is_relevant_committee("Armed Services Committee", "LMT", mapping) is True

    def test_not_relevant(self):
        mapping = {"armed services": ["LMT"], "technology": ["NVDA"]}
        assert _is_relevant_committee("Armed Services Committee", "AAPL", mapping) is False

    def test_none_committee(self):
        mapping = {"armed services": ["LMT"]}
        assert _is_relevant_committee(None, "LMT", mapping) is False

    def test_empty_committee(self):
        mapping = {"armed services": ["LMT"]}
        assert _is_relevant_committee("", "LMT", mapping) is False
