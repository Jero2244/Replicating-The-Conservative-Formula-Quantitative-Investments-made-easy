"""Performance ratios for periodic (e.g. monthly) simple-return series.

Pure numpy, no external dependencies. Previously report.py imported these
from a `backtesting` skill installed outside the repo, which broke the report
on any machine without that skill; they now live here.
"""
from __future__ import annotations

import numpy as np


def cumulative_returns(returns: np.ndarray) -> np.ndarray:
    """Compounded cumulative return after each period: cum[i] = prod(1 + r[:i+1]) - 1."""
    return np.cumprod(1.0 + np.asarray(returns, dtype=float)) - 1.0


def cagr(total_return: float, years: float) -> float:
    """Compound annual growth rate from a total (not 1+) return over `years`."""
    if years <= 0:
        return np.nan
    return (1.0 + total_return) ** (1.0 / years) - 1.0


def annualized_vol(returns: np.ndarray, periods: int = 12) -> float:
    """Sample standard deviation of periodic returns, scaled by sqrt(periods)."""
    return float(np.std(returns, ddof=1) * np.sqrt(periods))


def sharpe_ratio(returns: np.ndarray, periods: int = 12, risk_free: float = 0.0) -> float:
    """Annualized Sharpe ratio. `risk_free` is the per-period rate (default 0)."""
    excess = np.asarray(returns, dtype=float) - risk_free
    std = np.std(excess, ddof=1)
    if std == 0:
        return np.nan
    return float(np.mean(excess) / std * np.sqrt(periods))


def max_drawdown(prices: np.ndarray) -> float:
    """Largest peak-to-trough decline of a price/wealth series, as a negative fraction."""
    prices = np.asarray(prices, dtype=float)
    running_peak = np.maximum.accumulate(prices)
    return float(np.min(prices / running_peak - 1.0))
