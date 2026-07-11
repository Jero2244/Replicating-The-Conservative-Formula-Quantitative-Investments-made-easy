"""Implied historical CCL/MEP (ARS/USD) rate from dollar-linked bond pairs.

PPI (and the free byma/data912 fallbacks) have no dedicated historical FX
endpoint. The standard workaround used across Argentine markets is to divide
the ARS-settled price of a bond by the USD-settled price of the *same* bond
(e.g. AL30 vs AL30D, or GD30 vs GD30D) — that ratio is the implied CCL/MEP
exchange rate on that date.

Used by src/backtest/run_backtest.py to convert ARS portfolio returns to
USD-implied returns, mirroring how the paper reports every region in USD.
"""
from __future__ import annotations

import pandas as pd

from src import config
from src.data_sources.ppi_client import PPIClient


def implied_fx_series(
    client: PPIClient,
    date_from,
    date_to,
    bond_pairs=None,
    instrument_type: str = "BONOS",
    settlement: str = config.SETTLEMENT,
) -> pd.Series:
    """Daily implied ARS/USD rate, averaged across available bond pairs.

    Returns a pandas Series indexed by date. Missing days are forward-filled
    by the caller (see run_backtest.py) since bond quotes can be sparse on
    illiquid days.
    """
    bond_pairs = bond_pairs or config.FX_BOND_PAIRS
    implied_rates = []

    for ars_ticker, usd_ticker in bond_pairs:
        ars = client.historical(ars_ticker, date_from, date_to, instrument_type=instrument_type, settlement=settlement)
        usd = client.historical(usd_ticker, date_from, date_to, instrument_type=instrument_type, settlement=settlement)
        if ars.empty or usd.empty or "price" not in ars.columns or "price" not in usd.columns:
            continue

        merged = pd.merge(
            ars[["date", "price"]].rename(columns={"price": "price_ars"}),
            usd[["date", "price"]].rename(columns={"price": "price_usd"}),
            on="date",
            how="inner",
        )
        merged = merged[merged["price_usd"] > 0]
        if merged.empty:
            continue

        rate = (merged["price_ars"] / merged["price_usd"]).rename(f"{ars_ticker}_implied_fx")
        rate.index = merged["date"]
        implied_rates.append(rate)

    if not implied_rates:
        raise RuntimeError(
            "Could not build an implied FX series from any bond pair "
            f"({bond_pairs}). Check ticker availability/date range."
        )

    combined = pd.concat(implied_rates, axis=1)
    return combined.mean(axis=1).sort_index().rename("implied_ccl")
