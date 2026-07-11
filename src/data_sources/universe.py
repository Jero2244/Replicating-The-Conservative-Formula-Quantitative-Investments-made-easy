"""Defines the Argentine stock universe and validates it against PPI.

PPI has no endpoint that lists "all instruments in a market", so the universe
itself comes from config/universe.csv (curated from BYMA's Panel Lider +
Panel General, seeded from the data912 skill's static ticker catalog). This
module just resolves each ticker via PPI's SearchInstrument so we fail fast
on typos or tickers PPI doesn't recognize, rather than silently getting empty
historical series later.

Run directly to sanity-check the universe:

    python -m src.data_sources.universe
"""
from __future__ import annotations

import pandas as pd

from src import config
from src.data_sources.ppi_client import PPIClient


def load_universe() -> pd.DataFrame:
    """Loads config/universe.csv as-is (ticker, name, panel, sector)."""
    return pd.read_csv(config.UNIVERSE_CSV)


def validate_universe(client: PPIClient | None = None) -> pd.DataFrame:
    """Resolves every ticker in the universe via PPI SearchInstrument.

    Returns the universe DataFrame with an added `ppi_found` bool column so
    callers can flag/drop tickers PPI doesn't recognize (delisted, renamed,
    wrong instrument type, etc.) before running the backtest.
    """
    client = client or PPIClient()
    universe = load_universe()

    found = []
    for ticker in universe["ticker"]:
        try:
            result = client.search_instrument(ticker=ticker)
            found.append(bool(result))
        except Exception:
            found.append(False)

    universe = universe.copy()
    universe["ppi_found"] = found
    return universe


if __name__ == "__main__":
    result = validate_universe()
    missing = result[~result["ppi_found"]]
    print(f"{len(result)} tickers in universe, {len(missing)} not found via PPI SearchInstrument.")
    if not missing.empty:
        print(missing[["ticker", "name", "panel"]].to_string(index=False))
