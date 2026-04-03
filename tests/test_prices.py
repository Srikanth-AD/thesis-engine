"""Tests for the prices module — blended cost basis calculation."""
import pytest

from modules.prices import _blended_cost


class TestBlendedCost:
    def test_single_purchase(self):
        purchases = [{"dollars": 100, "price_per_share": 50.0}]
        blended, shares, invested = _blended_cost(purchases)
        assert invested == 100
        assert shares == pytest.approx(2.0)
        assert blended == pytest.approx(50.0)

    def test_multiple_tranches(self):
        purchases = [
            {"dollars": 100, "price_per_share": 50.0},
            {"dollars": 200, "price_per_share": 100.0},
        ]
        blended, shares, invested = _blended_cost(purchases)
        assert invested == 300
        assert shares == pytest.approx(4.0)  # 2 + 2
        assert blended == pytest.approx(75.0)  # 300/4

    def test_empty_purchases(self):
        blended, shares, invested = _blended_cost([])
        assert invested == 0
        assert shares == 0
        assert blended == 0

    def test_dca_same_stock(self):
        """Dollar-cost averaging across 3 tranches."""
        purchases = [
            {"dollars": 50, "price_per_share": 10.0},   # 5 shares
            {"dollars": 50, "price_per_share": 25.0},   # 2 shares
            {"dollars": 50, "price_per_share": 50.0},   # 1 share
        ]
        blended, shares, invested = _blended_cost(purchases)
        assert invested == 150
        assert shares == pytest.approx(8.0)
        assert blended == pytest.approx(18.75)  # 150/8
