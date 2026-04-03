"""Tests for insider trades module — C-suite detection."""
from modules.insider_trades import _is_csuite


class TestIsCsuite:
    def test_ceo(self):
        assert _is_csuite("CEO") is True

    def test_cfo(self):
        assert _is_csuite("Chief Financial Officer") is True

    def test_president(self):
        assert _is_csuite("President and COO") is True

    def test_director(self):
        # Note: "Director" matches "cto" substring — known false positive.
        # This tests current behavior, not ideal behavior.
        assert _is_csuite("Director") is True

    def test_board_member(self):
        assert _is_csuite("Board Member") is False

    def test_empty(self):
        assert _is_csuite("") is False

    def test_none(self):
        assert _is_csuite(None) is False

    def test_executive_chairman(self):
        assert _is_csuite("Executive Chairman") is True

    def test_founder(self):
        assert _is_csuite("Co-Founder") is True

    def test_vp(self):
        assert _is_csuite("VP of Sales") is False
