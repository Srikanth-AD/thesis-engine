"""Tests for press release classification."""
from modules.press_releases import _classify_pr


class TestClassifyPr:
    def test_dilution_by_8k_item(self):
        assert _classify_pr("Some filing", items=["3.02"]) == "dilution"

    def test_contract_by_8k_item(self):
        assert _classify_pr("Some filing", items=["1.01"]) == "contract"

    def test_executive_by_8k_item(self):
        assert _classify_pr("Some filing", items=["5.02"]) == "executive"

    def test_dilution_by_title(self):
        assert _classify_pr("Company announces public offering of shares") == "dilution"

    def test_contract_by_title(self):
        assert _classify_pr("Company wins $50M DoD contract") == "contract"

    def test_executive_by_title(self):
        assert _classify_pr("Company appoints new CEO") == "executive"

    def test_earnings_by_title(self):
        assert _classify_pr("Q3 2026 earnings results beat estimates") == "earnings"

    def test_general_fallback(self):
        assert _classify_pr("Company provides update on operations") == "general"

    def test_dilution_item_takes_priority(self):
        """8-K item codes should override title-based classification."""
        assert _classify_pr("New partnership agreement", items=["3.02"]) == "dilution"
