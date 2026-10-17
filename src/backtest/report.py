"""Performance report for the Conservative/Speculative/Merval return series
produced by run_backtest.py.

Sharpe/CAGR/max-drawdown math lives in src/backtest/ratios.py.

Usage:
    python -m src.backtest.report
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.backtest.ratios import annualized_vol, cagr, cumulative_returns, max_drawdown, sharpe_ratio

PERIODS_PER_YEAR = 12  # monthly return series


def summarize(returns: pd.Series) -> dict:
    r = returns.dropna().to_numpy()
    if len(r) < 2:
        return {"n_obs": len(r), "cagr": np.nan, "ann_vol": np.nan, "sharpe": np.nan, "max_drawdown": np.nan, "total_return": np.nan}

    cum = cumulative_returns(r)
    prices = np.concatenate(([1.0], 1.0 + cum))
    years = len(r) / PERIODS_PER_YEAR

    return {
        "n_obs": len(r),
        "cagr": cagr(cum[-1], years),
        "ann_vol": annualized_vol(r, periods=PERIODS_PER_YEAR),
        "sharpe": sharpe_ratio(r, periods=PERIODS_PER_YEAR),
        "max_drawdown": max_drawdown(prices),
        "total_return": cum[-1],
    }


def build_report(returns_df: pd.DataFrame) -> pd.DataFrame:
    rows = {col: summarize(returns_df[col]) for col in returns_df.columns}
    return pd.DataFrame(rows).T


def plot_equity_curves(returns_df: pd.DataFrame, columns: list[str], title: str, out_path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))
    for col in columns:
        if col not in returns_df.columns:
            continue
        r = returns_df[col].dropna()
        if r.empty:
            continue
        wealth = (1 + r).cumprod()
        ax.plot(wealth.index, wealth.values, label=col)

    ax.set_title(title)
    ax.set_ylabel("Wealth index (start = 1.0)")
    ax.set_yscale("log")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    returns_path = config.DATA_PROCESSED / "portfolio_returns.csv"
    if not returns_path.exists():
        raise SystemExit(f"{returns_path} not found — run `python -m src.backtest.run_backtest` first.")

    returns_df = pd.read_csv(returns_path, index_col=0, parse_dates=True)

    report = build_report(returns_df)
    print("\n=== Performance summary (monthly series) ===")
    print(report.to_string(float_format=lambda x: f"{x:.4f}"))

    report_path = config.DATA_PROCESSED / "performance_summary.csv"
    report.to_csv(report_path)
    print(f"\nWrote {report_path}")

    ars_cols = [c for c in returns_df.columns if c.endswith("_ars")]
    usd_cols = [c for c in returns_df.columns if c.endswith("_usd")]

    plot_equity_curves(returns_df, ars_cols, "Conservative Formula (2-factor) — ARS nominal", config.DATA_PROCESSED / "equity_curve_ars.png")
    plot_equity_curves(returns_df, usd_cols, "Conservative Formula (2-factor) — USD implied (CCL)", config.DATA_PROCESSED / "equity_curve_usd.png")
    print(f"Wrote equity curve plots to {config.DATA_PROCESSED}")


if __name__ == "__main__":
    main()
