"""Tests for alert formatting helpers."""
from modules.alerts import _action_badge, _extract_section


class TestActionBadge:
    def test_buy_more(self):
        response = "PLTR — ACTION: BUY MORE — thesis strengthening"
        label, color, bg = _action_badge(response, "PLTR")
        assert label == "BUY MORE"

    def test_sell(self):
        response = "RR — ACTION: SELL — fraud lawsuit risk too high"
        label, color, bg = _action_badge(response, "RR")
        assert label == "SELL"

    def test_keep(self):
        response = "VRT — ACTION: KEEP — thesis intact"
        label, color, bg = _action_badge(response, "VRT")
        assert label == "KEEP"

    def test_default_keep(self):
        response = "Some analysis without clear action"
        label, color, bg = _action_badge(response, "PLTR")
        assert label == "KEEP"


class TestExtractSection:
    def test_extract_risk(self):
        response = "BIGGEST RISK: PLTR insider selling pattern\nMultiple C-suite exits\n\nBIGGEST OPPORTUNITY: VRT earnings"
        items = _extract_section(response, "BIGGEST RISK")
        assert len(items) > 0
        assert "PLTR" in items[0]

    def test_extract_empty(self):
        response = "No relevant sections here"
        items = _extract_section(response, "BIGGEST RISK")
        assert items == []
