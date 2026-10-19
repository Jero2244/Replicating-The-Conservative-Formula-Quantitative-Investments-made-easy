"""Re-runs the backtest with more names per portfolio.

The base run holds ~8-10 stocks (the best 30% of the low-vol half). This
holds a fixed N instead (10, 15, 20, 25, ...) to see how the results change
as the portfolio gets more diversified.

Prices and the CCL come from PPI, as in run_backtest.py; `--source yahoo`
uses Yahoo Finance prices and the ADR-implied CCL instead, so it runs
without credentials. A `base` row (the usual 30% rule) is run on the same
data as a reference.

Usage:
    python -m src.backtest.run_holdings_sensitivity --sizes 10 15 20 25

Writes data/processed/holdings_sensitivity.csv.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from src import config
from src.backtest.report import summarize
from src.data_sources.benchmark import fetch_merval_index
from src.backtest.run_backtest import fetch_universe_prices
from src.data_sources.fx import adr_implied_fx_series, ccl_series, _yahoo_daily_close
from src.data_sources.ppi_client import PPIClient
from src.data_sources.universe import load_universe
from src.formula.factors import (
    build_price_panel,
    load_dividends,
    load_shares_outstanding,
    momentum_12_1,
    net_payout_yield,
    trailing_volatility,
)
from src.formula.portfolio import build_portfolio_returns


def fetch_yahoo_prices(tickers: list[str], date_from, date_to) -> dict[str, pd.DataFrame]:
    cache = config.DATA_RAW / f"yahoo_{date_from}_{date_to}"
    cache.mkdir(parents=True, exist_ok=True)
    prices = {}
    for ticker in tickers:
        f = cache / f"{ticker}.csv"
        if f.exists():
            df = pd.read_csv(f, parse_dates=["date"])
        else:
            try:
                s = _yahoo_daily_close(f"{ticker}.BA", date_from, date_to)
            except Exception as exc:
                print(f"  [warn] {ticker}: {exc}, skipping")
                continue
            df = s.rename("price").rename_axis("date").reset_index()
            df.to_csv(f, index=False)
        if df.empty:
            print(f"  [warn] no data for {ticker}, skipping")
            continue
        prices[ticker] = df
    return prices


def avg_holdings(holdings: dict, key: str) -> float:
    return float(np.mean([len(v[key]) for v in holdings.values() if v[key]]))


def run(sizes: list[int], date_from, date_to, source: str = "ppi") -> pd.DataFrame:
    tickers = load_universe()["ticker"].tolist()
    print(f"Fetching {source} history for {len(tickers)} tickers...")
    client = PPIClient() if source == "ppi" else None
    if client:
        prices = fetch_universe_prices(client, tickers, date_from, date_to)
    else:
        prices = fetch_yahoo_prices(tickers, date_from, date_to)
    print(f"  got data for {len(prices)}/{len(tickers)} tickers")

    monthly = build_price_panel(prices)
    vol_df, mom_df = trailing_volatility(monthly), momentum_12_1(monthly)
    npy_df = net_payout_yield(monthly, load_dividends(), load_shares_outstanding())

    fx = ccl_series(client, date_from, date_to) if client else adr_implied_fx_series(date_from, date_to)
    merval = fetch_merval_index(date_from, date_to).set_index("date")["close"].resample("ME").last()

    rows = []
    for label, n in [("base (30%)", None)] + [(str(s), s) for s in sizes]:
        for version, npy in [("without NPY", None), ("with NPY", npy_df)]:
            ret, holds = build_portfolio_returns(monthly, vol_df, mom_df, npy, n_holdings=n)
            fx_ret = fx.resample("ME").last().reindex(ret.index, method="ffill").pct_change(fill_method=None)
            for ccy, r in [("ARS", ret), ("USD", (1 + ret).div(1 + fx_ret, axis=0) - 1)]:
                for pf in ["conservative", "speculative"]:
                    rows.append({
                        "holdings": label, "version": version, "ccy": ccy, "portfolio": pf,
                        "avg_names": avg_holdings(holds, pf), **summarize(r[pf]),
                    })
        m_ars = merval.pct_change(fill_method=None).reindex(ret.index)
        if label == "base (30%)":
            for ccy, r in [("ARS", m_ars), ("USD", (1 + m_ars) / (1 + fx_ret) - 1)]:
                rows.append({"holdings": "Merval", "version": "-", "ccy": ccy, "portfolio": "merval",
                             "avg_names": np.nan, **summarize(r)})
    out = pd.DataFrame(rows)
    path = config.DATA_PROCESSED / "holdings_sensitivity.csv"
    out.to_csv(path, index=False)
    print(f"Wrote {path}")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[10, 15, 20, 25])
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end", default="2026-09-30")
    parser.add_argument("--source", choices=["ppi", "yahoo"], default="ppi")
    args = parser.parse_args()
    out = run(args.sizes, args.start, args.end, args.source)
    pd.set_option("display.width", 200)
    cols = ["holdings", "version", "avg_names", "cagr", "ann_vol", "sharpe", "max_drawdown", "total_return"]
    for ccy in ["ARS", "USD"]:
        for pf in ["conservative", "speculative", "merval"]:
            sub = out[(out.ccy == ccy) & (out.portfolio == pf)][cols]
            print(f"\n== {ccy} / {pf} ==\n{sub.round(3).to_string(index=False)}")


if __name__ == "__main__":
    main()
