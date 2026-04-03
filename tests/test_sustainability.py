"""Tests for sustainability/ESG signal extraction."""
from modules.sustainability import (
    ENVIRONMENTAL_KEYWORDS,
    ESG_RED_FLAGS,
    GOVERNANCE_KEYWORDS,
    _scan_text,
    _score_category,
    extract_sustainability_signals,
)


class TestScanText:
    def test_finds_climate_keyword(self):
        matches = _scan_text("Company announces net zero target by 2030", ENVIRONMENTAL_KEYWORDS)
        assert "net zero" in matches

    def test_finds_governance_keyword(self):
        matches = _scan_text("SEC investigation into accounting fraud", GOVERNANCE_KEYWORDS)
        assert "sec investigation" in matches
        assert "accounting fraud" in matches

    def test_finds_red_flag(self):
        matches = _scan_text("EPA fine issued for toxic waste disposal", ESG_RED_FLAGS)
        assert "epa fine" in matches
        assert "toxic" in matches

    def test_no_matches(self):
        matches = _scan_text("Company reports quarterly earnings", ENVIRONMENTAL_KEYWORDS)
        assert matches == []

    def test_case_insensitive(self):
        matches = _scan_text("CARBON emissions rising globally", ENVIRONMENTAL_KEYWORDS)
        assert "carbon" in matches


class TestScoreCategory:
    def test_none(self):
        assert _score_category([]) == "none"

    def test_low(self):
        assert _score_category(["carbon"]) == "low"

    def test_moderate(self):
        assert _score_category(["a", "b", "c"]) == "moderate"

    def test_high(self):
        assert _score_category(["a", "b", "c", "d", "e", "f"]) == "high"


class TestExtractSustainabilitySignals:
    def test_extracts_from_news(self):
        portfolio = {
            "portfolio": [
                {"ticker": "TEST", "thesis_risks": []}
            ]
        }
        data = {
            "news_rss": {
                "TEST": [
                    {"title": "Company faces SEC investigation for securities fraud"},
                    {"title": "New carbon emission regulations impact sector"},
                ]
            },
            "press_releases": {},
            "reddit": {},
            "world_news": {"top_events": []},
        }
        result = extract_sustainability_signals(data, portfolio)
        assert result["TEST"]["has_esg_signal"] is True
        assert result["TEST"]["governance"]["signal"] != "none"

    def test_no_signals(self):
        portfolio = {
            "portfolio": [
                {"ticker": "SAFE", "thesis_risks": []}
            ]
        }
        data = {
            "news_rss": {
                "SAFE": [{"title": "Company beats earnings estimates"}]
            },
            "press_releases": {},
            "reddit": {},
            "world_news": {"top_events": []},
        }
        result = extract_sustainability_signals(data, portfolio)
        assert result["SAFE"]["has_esg_signal"] is False

    def test_thesis_risk_governance(self):
        portfolio = {
            "portfolio": [
                {"ticker": "RISKY", "thesis_risks": [
                    "Securities fraud class action filed"
                ]}
            ]
        }
        data = {
            "news_rss": {},
            "press_releases": {},
            "reddit": {},
            "world_news": {"top_events": []},
        }
        result = extract_sustainability_signals(data, portfolio)
        assert result["RISKY"]["has_esg_signal"] is True
        assert "securities fraud" in result["RISKY"]["governance"]["keywords"]

    def test_global_esg_from_gdelt(self):
        portfolio = {"portfolio": []}
        data = {
            "news_rss": {},
            "press_releases": {},
            "reddit": {},
            "world_news": {
                "top_events": [
                    "[20260401] (reuters.com) Climate summit reaches new emission targets",
                    "[20260401] (bbc.com) Stock market hits new high",
                ]
            },
        }
        result = extract_sustainability_signals(data, portfolio)
        assert len(result["__global_esg__"]) == 1
        assert "climate" in result["__global_esg__"][0].lower() or "emission" in result["__global_esg__"][0].lower()
