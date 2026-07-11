"""The two factors used by the (v1, NPY-less) Conservative Formula:
trailing volatility and 12-1 month momentum, computed on monthly prices.

NPY (net payout yield) is stubbed out — see `compute_npy` — because PPI has
no dividends/buybacks endpoint. Once data/manual/dividends.csv exists (see
data/manual/dividends_template.csv for the expected columns), compute_npy
will pick it up automatically and src/formula/portfolio.py's ranking will
blend it in without needing changes elsewhere.
"""
from __future__ import annotations

import pandas as pd

from src import config


def to_monthly(daily_prices: pd.DataFrame, price_col: str = "price") -> pd.Series:
    """Daily (date, price) history -> month-end price series."""
    s = daily_prices.set_index("date")[price_col].sort_index()
    return s.resample("ME").last().dropna()


def build_price_panel(price_by_ticker: dict[str, pd.DataFrame], price_col: str = "price") -> pd.DataFrame:
    """{ticker: daily OHLC df} -> wide month-end price panel (dates x tickers)."""
    monthly = {ticker: to_monthly(df, price_col) for ticker, df in price_by_ticker.items() if not df.empty}
    return pd.DataFrame(monthly).sort_index()


def trailing_volatility(
    monthly_prices: pd.DataFrame,
    window: int = config.VOL_WINDOW_MONTHS,
    min_periods: int = 12,
) -> pd.DataFrame:
    """Annualized trailing volatility of monthly returns, per ticker.

    Falls back to a shorter window (min_periods) for names with less history
    than the paper's full 36 months, since Argentina's listing history is
    much shorter for many names.
    """
    monthly_returns = monthly_prices.pct_change(fill_method=None)
    return monthly_returns.rolling(window=window, min_periods=min_periods).std() * (12 ** 0.5)


def momentum_12_1(monthly_prices: pd.DataFrame) -> pd.DataFrame:
    """12-1 month momentum: return from t-12 to t-1 (skips the most recent month)."""
    lookback = config.MOMENTUM_LOOKBACK_MONTHS
    skip = config.MOMENTUM_SKIP_MONTHS
    return monthly_prices.shift(skip) / monthly_prices.shift(lookback) - 1.0


def compute_npy(ticker: str, as_of_date) -> float | None:
    """Net Payout Yield stub.

    Returns None (factor excluded from ranking) until data/manual/dividends.csv
    is populated. Expected columns: ticker, ex_date, dividend_per_share,
    currency, source (see data/manual/dividends_template.csv). Once present,
    this should compute trailing (e.g. 12-month) dividends-per-share divided
    by price as of `as_of_date`, optionally netted against any available
    shares-outstanding change (buybacks/issuance) if that data is ever sourced.
    """
    if not config.DIVIDENDS_CSV.exists():
        return None
    # TODO: implement once data/manual/dividends.csv exists — trailing dividend
    # yield as of as_of_date, keyed by ticker. Left unimplemented on purpose:
    # the paper's NPY also nets buyback/issuance yield, which still has no
    # data source here (see plan notes on Refinitiv/CNV as candidates).
    raise NotImplementedError(
        "data/manual/dividends.csv found but compute_npy() is not implemented yet."
    )
