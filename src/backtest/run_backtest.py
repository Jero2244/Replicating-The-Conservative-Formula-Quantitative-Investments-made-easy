"""End-to-end pipeline: pull PPI history for the universe, build the 2-factor
(Low-Vol + Momentum) Conservative/Speculative portfolios, and convert the
resulting ARS return series to USD-implied returns via the bond-pair FX proxy.

Usage:
    python -m src.backtest.run_backtest --start 2010-01-01 --end 2026-07-01

Writes:
    data/processed/portfolio_returns.csv   (date, conservative, speculative, merval — ARS & USD)
    data/processed/holdings.json           (rebalance date -> selected tickers, for inspection)
"""
from __future__ import annotations

import argparse
import json
from datetime import date

import pandas as pd

from src import config
from src.data_sources.benchmark import fetch_merval_index
from src.data_sources.fx import implied_fx_series
from src.data_sources.ppi_client import PPIClient
from src.data_sources.universe import load_universe
from src.formula.factors import build_price_panel, momentum_12_1, trailing_volatility
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

    returns_ars, holdings = build_portfolio_returns(monthly_prices, vol_df, mom_df)

    print("Building implied CCL/MEP FX series from bond pairs...")
    fx_series = implied_fx_series(client, date_from, date_to)
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
