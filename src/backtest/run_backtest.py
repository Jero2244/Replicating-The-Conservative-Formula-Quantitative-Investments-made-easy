"""End-to-end pipeline: pull PPI history for the universe, build the
Conservative/Speculative portfolios, and convert the resulting ARS return
series to USD-implied returns via the implied CCL rate (src/data_sources/fx.py).

With data/manual/dividends.csv present, both versions are built: the full
3-factor formula (Low-Vol + Momentum + NPY; columns `conservative_*`,
`speculative_*`) and the 2-factor one without NPY (`*_no_npy_*`), so the
effect of NPY can be compared directly. Without it, only the 2-factor
version is built, under the plain `conservative_*` / `speculative_*` names.

Usage:
    python -m src.backtest.run_backtest --start 2010-01-01 --end 2026-07-01

Writes:
    data/processed/portfolio_returns.csv   (date, conservative, speculative, merval — ARS & USD)
    data/processed/holdings.json           (rebalance date -> selected tickers per portfolio, for inspection)
"""
from __future__ import annotations

import argparse
import json
from datetime import date

import pandas as pd

from src import config
from src.data_sources.benchmark import fetch_merval_index
from src.data_sources.fx import ccl_series
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


def fetch_universe_prices(client: PPIClient, tickers: list[str], date_from, date_to) -> dict[str, pd.DataFrame]:
    prices = {}
    for ticker in tickers:
        try:
            df = client.historical(ticker, date_from, date_to)
        except Exception as exc:
            print(f"  [warn] {ticker}: {exc}, skipping")
            continue
        if df.empty:
            print(f"  [warn] no data for {ticker}, skipping")
            continue
        prices[ticker] = df
    return prices


def run(date_from, date_to) -> pd.DataFrame:
    client = PPIClient()
    universe = load_universe()

    print(f"Fetching PPI history for {len(universe)} tickers ({date_from} -> {date_to})...")
    prices_by_ticker = fetch_universe_prices(client, universe["ticker"].tolist(), date_from, date_to)
    print(f"  got data for {len(prices_by_ticker)}/{len(universe)} tickers")

    monthly_prices = build_price_panel(prices_by_ticker)
    vol_df = trailing_volatility(monthly_prices)
    mom_df = momentum_12_1(monthly_prices)

    npy_df = net_payout_yield(monthly_prices, load_dividends(), load_shares_outstanding())
    if npy_df is None:
        print(f"  {config.DIVIDENDS_CSV} not found — ranking on momentum only (2-factor version).")
    else:
        print("  ranking on momentum + NPY (3-factor version).")

    returns_ars, holdings = build_portfolio_returns(monthly_prices, vol_df, mom_df, npy_df)
    if npy_df is not None:
        print("  also building the 2-factor version (no NPY) for comparison.")
        returns_no_npy, holdings_no_npy = build_portfolio_returns(monthly_prices, vol_df, mom_df)
        returns_ars = pd.concat([returns_ars, returns_no_npy.add_suffix("_no_npy")], axis=1)
        for dt, picks in holdings_no_npy.items():
            holdings.setdefault(dt, {}).update({f"{k}_no_npy": v for k, v in picks.items()})

    print("Building implied CCL series (bond pairs, extended back with ADR pairs)...")
    fx_series = ccl_series(client, date_from, date_to)
    monthly_fx = fx_series.resample("ME").last().reindex(returns_ars.index, method="ffill")
    fx_returns = monthly_fx.pct_change(fill_method=None)

    # USD-implied return ~= ARS return - FX depreciation, in log-return terms;
    # using simple returns: (1+r_ars)/(1+fx_change) - 1
    returns_usd = returns_ars.apply(lambda col: (1 + col) / (1 + fx_returns) - 1)
    returns_usd = returns_usd.add_suffix("_usd")
    returns_ars = returns_ars.add_suffix("_ars")

    print("Fetching Merval index benchmark...")
    merval = fetch_merval_index(date_from, date_to)
    merval_monthly = merval.set_index("date")["close"].resample("ME").last()
    merval_ars_ret = merval_monthly.pct_change(fill_method=None).reindex(returns_ars.index).rename("merval_ars")
    merval_usd_ret = ((1 + merval_ars_ret) / (1 + fx_returns) - 1).rename("merval_usd")

    combined = pd.concat([returns_ars, returns_usd, merval_ars_ret, merval_usd_ret], axis=1)

    out_path = config.DATA_PROCESSED / "portfolio_returns.csv"
    combined.to_csv(out_path)
    print(f"Wrote {out_path}")

    holdings_serializable = {dt.strftime("%Y-%m-%d"): v for dt, v in holdings.items()}
    holdings_path = config.DATA_PROCESSED / "holdings.json"
    holdings_path.write_text(json.dumps(holdings_serializable, indent=2, ensure_ascii=False))
    print(f"Wrote {holdings_path}")

    return combined


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2010-01-01", help="Start date, YYYY-MM-DD")
    parser.add_argument("--end", default=date.today().isoformat(), help="End date, YYYY-MM-DD")
    args = parser.parse_args()
    run(args.start, args.end)


if __name__ == "__main__":
    main()
