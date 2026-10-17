import numpy as np
import pytest

from src.backtest.ratios import annualized_vol, cagr, cumulative_returns, max_drawdown, sharpe_ratio


def test_cumulative_returns_compounds():
    cum = cumulative_returns(np.array([0.10, -0.10, 0.20]))
    assert cum == pytest.approx([0.10, -0.01, 0.188])


def test_cagr_doubling_over_two_years():
    assert cagr(3.0, 2.0) == pytest.approx(1.0)  # 4x in 2 years = 100%/yr


def test_annualized_vol_and_sharpe_scale_with_sqrt_periods():
    r = np.array([0.01, 0.03, -0.01, 0.05])
    assert annualized_vol(r, periods=12) == pytest.approx(np.std(r, ddof=1) * np.sqrt(12))
    assert sharpe_ratio(r, periods=12) == pytest.approx(r.mean() / np.std(r, ddof=1) * np.sqrt(12))


def test_sharpe_nan_for_constant_returns():
    assert np.isnan(sharpe_ratio(np.array([0.01, 0.01, 0.01])))


def test_max_drawdown_peak_to_trough():
    assert max_drawdown(np.array([1.0, 2.0, 1.0, 1.5, 0.5, 3.0])) == pytest.approx(-0.75)
