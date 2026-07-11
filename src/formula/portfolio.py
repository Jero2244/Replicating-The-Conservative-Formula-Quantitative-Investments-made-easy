"""Cross-sectional stock selection and equal-weight portfolio construction,
following the paper's mechanism (Figure 1) at Argentina's smaller scale:

    1. Split the eligible universe into low-vol / high-vol halves by trailing
       volatility (LOW_VOL_PCT).
    2. Within the low-vol half, rank by 12-1 month momentum and take the top
       TOP_PCT as "Conservative". Within the high-vol half, take the worst
       momentum names as "Speculative" (long-short comparison portfolio, same
       as the paper's CMS construction).
    3. Equal-weight both, rebalanced quarterly.

NPY is not part of the ranking yet (see src/formula/factors.py::compute_npy).
"""
from __future__ import annotations

import pandas as pd

from src import config


def select_portfolios(
    vol_row: pd.Series,
    mom_row: pd.Series,
    low_vol_pct: float = config.LOW_VOL_PCT,
    top_pct: float = config.TOP_PCT,
) -> tuple[list[str], list[str]]:
    """Cross-sectional selection for a single rebalance date.

    `vol_row` / `mom_row` are the vol/momentum values for every ticker as of
    that date (e.g. `vol_df.loc[date]`). Returns (conservative, speculative)
    ticker lists.
    """
    valid = vol_row.dropna().index.intersection(mom_row.dropna().index)
    if len(valid) < 10:
        # Too few names with enough history to rank meaningfully.
        return [], []

    vol_s, mom_s = vol_row.loc[valid], mom_row.loc[valid]

    n_low = max(1, round(len(valid) * low_vol_pct))
    ranked_by_vol = vol_s.sort_values()
    low_vol_pool = ranked_by_vol.index[:n_low]
    high_vol_pool = ranked_by_vol.index[n_low:]

    n_top = max(1, round(len(low_vol_pool) * top_pct))
    conservative = mom_s.loc[low_vol_pool].sort_values(ascending=False).index[:n_top].tolist()

    speculative: list[str] = []
    if len(high_vol_pool) > 0:
        n_bottom = max(1, round(len(high_vol_pool) * top_pct))
        speculative = mom_s.loc[high_vol_pool].sort_values(ascending=True).index[:n_bottom].tolist()

    return conservative, speculative


def build_portfolio_returns(
    monthly_prices: pd.DataFrame,
    vol_df: pd.DataFrame,
    mom_df: pd.DataFrame,
    freq: str = config.REBALANCE_FREQ,
) -> tuple[pd.DataFrame, dict]:
    """Builds monthly equal-weight return series for the Conservative and
    Speculative portfolios, rebalancing at each quarter-end.

    Holdings are picked once per quarter (matching the paper's quarterly
    rebalance) and equal-weighted each month within the quarter using that
    month's realized returns — a standard buy-and-hold-then-rebalance
    approximation, not a monthly re-equal-weighting.

    Returns (returns_df, holdings) where holdings maps rebalance date ->
    {"conservative": [...], "speculative": [...]} for inspection/debugging.
    """
    monthly_returns = monthly_prices.pct_change(fill_method=None)
    dates = monthly_prices.index

    quarter_periods = pd.PeriodIndex(dates, freq=freq)
    # NOTE: .tolist() (not .values) — for a tz-aware DatetimeIndex, .values
    # returns UTC-normalized numpy.datetime64 that compare unequal (by hash)
    # to the tz-aware pandas.Timestamp objects yielded by iterating `dates`.
    rebalance_dates = set(pd.Series(dates, index=quarter_periods).groupby(level=0).last().tolist())

    holdings: dict = {}
    conservative_tickers: list[str] = []
    speculative_tickers: list[str] = []
    records = []

    for i, dt in enumerate(dates):
        if dt in rebalance_dates and dt in vol_df.index and dt in mom_df.index:
            conservative_tickers, speculative_tickers = select_portfolios(vol_df.loc[dt], mom_df.loc[dt])
            holdings[dt] = {"conservative": conservative_tickers, "speculative": speculative_tickers}

        if i + 1 >= len(dates):
            break
        next_dt = dates[i + 1]
        next_returns = monthly_returns.loc[next_dt]

        cons_ret = next_returns.reindex(conservative_tickers).mean() if conservative_tickers else float("nan")
        spec_ret = next_returns.reindex(speculative_tickers).mean() if speculative_tickers else float("nan")
        records.append({"date": next_dt, "conservative": cons_ret, "speculative": spec_ret})

    returns_df = pd.DataFrame.from_records(records).set_index("date") if records else pd.DataFrame(
        columns=["conservative", "speculative"]
    )
    return returns_df, holdings
