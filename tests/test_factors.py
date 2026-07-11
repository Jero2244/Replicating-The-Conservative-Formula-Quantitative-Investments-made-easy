"""Unit tests for factor math and portfolio selection, on synthetic data.
No PPI credentials needed — run with `pytest tests/`.
"""
import numpy as np
import pandas as pd

from src.formula.factors import momentum_12_1, trailing_volatility
from src.formula.portfolio import build_portfolio_returns, select_portfolios


def _monthly_index(n, start="2018-01-31"):
    return pd.date_range(start, periods=n, freq="ME")


def test_momentum_12_1_known_return():
    idx = _monthly_index(14)
    # Flat at 100 for months 0..12, then jumps to 120 in the last month (13).
    # 12-1 momentum at month 13 = price[12] / price[1] - 1 = 100/100 - 1 = 0
    # (last month's own jump is skipped by construction: shift(1) vs shift(12))
    prices = pd.Series([100.0] * 13 + [120.0], index=idx)
    df = pd.DataFrame({"A": prices})

    mom = momentum_12_1(df)
    assert np.isclose(mom["A"].iloc[13], 0.0)


def test_momentum_12_1_reflects_prior_trend():
    idx = _monthly_index(14)
    # Steady drift: price doubles from month 1 to month 12.
    prices = [100.0] + [100.0 * (2 ** (i / 11)) for i in range(1, 13)] + [1000.0]
    df = pd.DataFrame({"A": pd.Series(prices, index=idx)})

    mom = momentum_12_1(df)
    # shift(1)/shift(12) at last row = price[12]/price[1] - 1 ~= 2 - 1 = 1.0
    assert mom["A"].iloc[13] > 0.9


def test_trailing_volatility_zero_for_constant_returns():
    idx = _monthly_index(40)
    prices = pd.Series([100.0 * (1.01 ** i) for i in range(40)], index=idx)
    df = pd.DataFrame({"A": prices})

    vol = trailing_volatility(df, window=36, min_periods=12)
    # Constant 1% monthly return -> zero volatility once the window fills.
    assert np.isclose(vol["A"].iloc[-1], 0.0, atol=1e-8)


def test_select_portfolios_picks_low_vol_high_momentum():
    tickers = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
    vol_row = pd.Series([0.1, 0.1, 0.1, 0.1, 0.1, 0.5, 0.5, 0.5, 0.5, 0.5], index=tickers)
    mom_row = pd.Series([0.30, 0.20, 0.10, 0.05, 0.01, -0.01, -0.05, -0.10, -0.20, -0.30], index=tickers)

    conservative, speculative = select_portfolios(vol_row, mom_row, low_vol_pct=0.5, top_pct=0.4)

    # Low-vol pool is {A..E}; top 40% (2 names) by momentum should be A, B.
    assert conservative == ["A", "B"]
    # High-vol pool is {F..J}; worst momentum (most negative) should be J, I.
    assert speculative == ["J", "I"]


def test_select_portfolios_returns_empty_for_tiny_universe():
    vol_row = pd.Series([0.1, 0.2, 0.3], index=["A", "B", "C"])
    mom_row = pd.Series([0.1, 0.2, 0.3], index=["A", "B", "C"])

    conservative, speculative = select_portfolios(vol_row, mom_row)
    assert conservative == []
    assert speculative == []


def test_build_portfolio_returns_only_rebalances_quarterly():
    idx = _monthly_index(6, start="2019-01-31")  # Jan..Jun 2019
    tickers = ["A", "B", "C", "D"]
    rng = np.random.default_rng(0)
    prices = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0, 0.01, size=(6, 4)), axis=0),
        index=idx,
        columns=tickers,
    )
    vol_df = trailing_volatility(prices, window=3, min_periods=2)
    mom_df = momentum_12_1(prices)
    # Force momentum to have valid (non-NaN) values for this short synthetic sample.
    mom_df = prices.pct_change().fillna(0.0)

    returns_df, holdings = build_portfolio_returns(prices, vol_df, mom_df, freq="Q")

    # Holdings should only be recorded on quarter-end months present in the index,
    # and at least one rebalance should actually fire.
    quarter_ends = {d for d in idx if d.month in (3, 6, 9, 12)}
    assert set(holdings.keys()).issubset(quarter_ends)
    assert len(holdings) > 0


def test_build_portfolio_returns_rebalances_with_tz_aware_index():
    # Regression test: PPI's historical data comes back tz-aware
    # (America/Argentina/Buenos_Aires). The rebalance-date matching used to
    # compare tz-aware Timestamps against UTC-normalized numpy.datetime64
    # (via `.values`), which silently never matched -> holdings was always
    # empty. See src/formula/portfolio.py's use of `.tolist()` instead.
    idx = _monthly_index(6, start="2019-01-31").tz_localize("America/Argentina/Buenos_Aires")
    tickers = ["A", "B", "C", "D"]
    rng = np.random.default_rng(0)
    prices = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0, 0.01, size=(6, 4)), axis=0),
        index=idx,
        columns=tickers,
    )
    vol_df = trailing_volatility(prices, window=3, min_periods=2)
    mom_df = prices.pct_change().fillna(0.0)

    _, holdings = build_portfolio_returns(prices, vol_df, mom_df, freq="Q")
    assert len(holdings) > 0
