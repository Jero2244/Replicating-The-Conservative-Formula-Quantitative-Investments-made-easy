"""Unit tests for factor math and portfolio selection, on synthetic data.
No PPI credentials needed — run with `pytest tests/`.
"""
import numpy as np
import pandas as pd

from src.formula.factors import (
    dividend_yield,
    momentum_12_1,
    net_buyback_yield,
    net_payout_yield,
    trailing_volatility,
)
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


def _dividends(rows):
    return pd.DataFrame(rows, columns=["ticker", "ex_date", "dividend_per_share", "price_before_ex"]).assign(
        ex_date=lambda d: pd.to_datetime(d["ex_date"])
    )


def test_dividend_yield_sums_event_yields_over_trailing_window():
    idx = _monthly_index(24, start="2020-01-31")
    prices = pd.DataFrame({"A": 100.0, "B": 50.0}, index=idx)
    divs = _dividends([
        ("A", "2020-03-10", 5.0, 100.0),   # 5%
        ("A", "2021-02-10", 3.0, 150.0),   # 2% — measured against the price when paid
        ("A", "2021-06-10", 1.0, 100.0),   # 1%
    ])

    dy = dividend_yield(prices, divs, window=12)

    assert dy["A"].iloc[:11].isna().all()  # window not yet full
    assert np.isclose(dy.loc["2020-12-31", "A"], 0.05)
    assert np.isclose(dy.loc["2021-02-28", "A"], 0.07)
    assert np.isclose(dy.loc["2021-03-31", "A"], 0.02)  # March 2020 dividend rolled out
    assert np.isclose(dy.loc["2021-12-31", "A"], 0.03)
    assert (dy["B"].iloc[11:] == 0.0).all()  # no dividends -> zero yield, not NaN


def test_dividend_yield_falls_back_to_previous_month_end_price():
    idx = _monthly_index(13, start="2020-01-31")
    prices = pd.DataFrame({"A": [100.0] * 5 + [200.0] * 8}, index=idx)
    divs = _dividends([("A", "2020-06-15", 10.0, np.nan)])  # May month-end price = 100

    dy = dividend_yield(prices, divs, window=12)
    assert np.isclose(dy["A"].iloc[-1], 0.10)


def test_dividend_yield_drops_implausible_events():
    idx = _monthly_index(12, start="2020-01-31")
    prices = pd.DataFrame({"A": 100.0}, index=idx)
    divs = _dividends([("A", "2020-03-10", 2.0, 100.0), ("A", "2020-06-10", 300.0, 100.0)])

    dy = dividend_yield(prices, divs, window=12, max_event_yield=0.25)
    assert np.isclose(dy["A"].iloc[-1], 0.02)


def test_dividend_yield_handles_tz_aware_index_and_missing_prices():
    idx = _monthly_index(12, start="2020-01-31").tz_localize("America/Argentina/Buenos_Aires")
    prices = pd.DataFrame({"A": [np.nan] * 11 + [100.0]}, index=idx)
    divs = _dividends([("A", "2020-06-10", 4.0, 80.0)])

    dy = dividend_yield(prices, divs, window=12)
    assert dy.index.equals(idx)
    assert dy["A"].iloc[:11].isna().all()  # NaN where the stock has no price
    assert np.isclose(dy["A"].iloc[-1], 0.05)


def test_net_buyback_yield_positive_when_shares_shrink():
    idx = _monthly_index(24, start="2020-01-31")
    prices = pd.DataFrame({"A": 100.0, "B": 100.0}, index=idx)
    shares = pd.DataFrame({
        "ticker": ["A"] * 24,
        "date": idx,
        "shares_outstanding": [1000.0] * 12 + [900.0] * 12,  # 10% bought back halfway
    })

    by = net_buyback_yield(prices, shares, window=24)
    assert np.isclose(by["A"].iloc[-1], 1 - 900 / 950)
    assert (by["B"] == 0.0).all()


def test_net_payout_yield_is_none_without_dividends():
    prices = pd.DataFrame({"A": 100.0}, index=_monthly_index(12))
    assert net_payout_yield(prices, None) is None


def test_select_portfolios_averages_momentum_and_npy_ranks():
    tickers = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
    vol_row = pd.Series([0.1] * 5 + [0.5] * 5, index=tickers)
    mom_row = pd.Series([0.30, 0.20, 0.10, 0.05, 0.01, -0.01, -0.05, -0.10, -0.20, -0.30], index=tickers)
    # Within the low-vol half, C and D pay big dividends and A pays nothing,
    # so the combined rank should prefer B and C over momentum leader A.
    npy_row = pd.Series([0.00, 0.06, 0.08, 0.07, 0.01, 0.10, 0.08, 0.06, 0.00, 0.01], index=tickers)

    conservative, speculative = select_portfolios(vol_row, mom_row, npy_row, low_vol_pct=0.5, top_pct=0.4)

    # Low-vol ranks (mom, npy -> avg): A(5,1)=3, B(4,3)=3.5, C(3,5)=4, D(2,4)=3, E(1,2)=1.5
    assert conservative == ["C", "B"]
    # High-vol ranks: F(5,5)=5, G(4,4)=4, H(3,3)=3, I(2,1)=1.5, J(1,2)=1.5
    assert speculative == ["I", "J"]
