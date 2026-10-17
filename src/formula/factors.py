"""The Conservative Formula's factors, computed on monthly prices: trailing
volatility, 12-1 month momentum, and net payout yield (NPY).

NPY = trailing 12-month cash dividend yield + net buyback yield. Dividends
come from data/manual/dividends.csv (built by src/data_sources/dividends.py);
buyback yield needs a shares-outstanding history that no available source
has for the backtest window, so it reads data/manual/shares_outstanding.csv
if present and is zero otherwise. With no dividends CSV at all, NPY is None
and the ranking falls back to the 2-factor (Low-Vol + Momentum) version.
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


def _month_periods(index: pd.DatetimeIndex) -> pd.PeriodIndex:
    # Drop tz first: PPI prices are tz-aware, and to_period() on a tz-aware
    # index warns. Month-end dates are the same month either way.
    return (index.tz_localize(None) if index.tz is not None else index).to_period("M")


def load_dividends(path=config.DIVIDENDS_CSV) -> pd.DataFrame | None:
    """data/manual/dividends.csv as a DataFrame, or None if it doesn't exist."""
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["ex_date"])


def load_shares_outstanding(path=config.SHARES_OUTSTANDING_CSV) -> pd.DataFrame | None:
    """Optional (ticker, date, shares_outstanding) history, or None."""
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["date"])


def dividend_yield(
    monthly_prices: pd.DataFrame,
    dividends: pd.DataFrame,
    window: int = config.NPY_DIVIDEND_WINDOW_MONTHS,
    max_event_yield: float = config.MAX_EVENT_DIVIDEND_YIELD,
) -> pd.DataFrame:
    """Trailing `window`-month cash dividend yield, per ticker (dates x tickers).

    Each dividend is divided by the price just before its ex-date
    (`price_before_ex`, falling back to the previous month-end price in
    `monthly_prices`) and the per-event yields in the window are summed.
    Measuring each payout against the price when it was paid keeps the yield
    meaningful under Argentine inflation. Events above `max_event_yield` are
    dropped as data errors. Tickers with no dividends get 0.
    """
    periods = _month_periods(monthly_prices.index)
    divs = dividends[dividends["ticker"].isin(monthly_prices.columns)].copy()
    divs["period"] = divs["ex_date"].dt.to_period("M")

    price = divs["price_before_ex"] if "price_before_ex" in divs else pd.Series(float("nan"), index=divs.index)
    prev_month_price = monthly_prices.set_axis(periods).shift(1).stack()
    fallback = pd.Series(list(zip(divs["period"], divs["ticker"])), index=divs.index).map(prev_month_price)
    divs["event_yield"] = divs["dividend_per_share"] / price.fillna(fallback)
    divs = divs[divs["event_yield"] <= max_event_yield]

    monthly_yield = (
        divs.pivot_table(index="period", columns="ticker", values="event_yield", aggfunc="sum")
        .reindex(index=periods, columns=monthly_prices.columns)
        .fillna(0.0)
    )
    trailing = monthly_yield.rolling(window=window, min_periods=window).sum()
    return trailing.set_axis(monthly_prices.index).where(monthly_prices.notna())


def net_buyback_yield(
    monthly_prices: pd.DataFrame,
    shares: pd.DataFrame,
    window: int = config.NPY_SHARES_WINDOW_MONTHS,
) -> pd.DataFrame:
    """1 - latest shares outstanding / trailing `window`-month average shares.

    Positive when the share count shrank (net buybacks), negative for net
    issuance. Shares must be split/stock-dividend adjusted, otherwise a stock
    dividend shows up as dilution. Tickers/dates without data get 0.
    """
    periods = _month_periods(monthly_prices.index)
    shares = shares.assign(period=shares["date"].dt.to_period("M"))
    monthly_shares = (
        shares.pivot_table(index="period", columns="ticker", values="shares_outstanding", aggfunc="last")
        .reindex(index=periods, columns=monthly_prices.columns)
        .ffill()
    )
    avg = monthly_shares.rolling(window=window, min_periods=window).mean()
    return (1.0 - monthly_shares / avg).fillna(0.0).set_axis(monthly_prices.index)


def net_payout_yield(
    monthly_prices: pd.DataFrame,
    dividends: pd.DataFrame | None,
    shares: pd.DataFrame | None = None,
) -> pd.DataFrame | None:
    """NPY = dividend yield + net buyback yield (dates x tickers).

    Returns None when there's no dividend data, which tells the portfolio
    step to rank on momentum alone (2-factor version).
    """
    if dividends is None:
        return None
    npy = dividend_yield(monthly_prices, dividends)
    if shares is not None:
        npy = npy + net_buyback_yield(monthly_prices, shares)
    return npy
