"""Implied historical CCL (ARS/USD) rate.

PPI (and the free byma/data912 fallbacks) have no dedicated historical FX
endpoint, so the rate is implied from securities that trade in both pesos
and dollars:

1. Bond pairs (primary, Sep 2020 onward): the ARS-settled price of a bond
   divided by the USD-settled price of the *same* bond (AL30 vs AL30D,
   GD30 vs GD30D). These bonds only exist since the 2020 restructuring.
2. ADR pairs (before Sep 2020): a stock's Buenos Aires price times the
   local-shares-per-ADR ratio, divided by its New York ADR price (GGAL, PAM,
   BMA, via Yahoo Finance), median across pairs. This is the classic
   "contado con liqui" calculation and goes back to the 2000s. It runs ~3%
   above the bond rate where both exist (monthly changes correlate ~0.95),
   so it's rescaled to meet the bond series without a jump.

Used by src/backtest/run_backtest.py to convert ARS portfolio returns to
USD-implied returns, mirroring how the paper reports every region in USD.
"""
from __future__ import annotations

import pandas as pd
import requests

from src import config
from src.data_sources.benchmark import _to_unix
from src.data_sources.ppi_client import PPIClient

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SPLICE_OVERLAP_DAYS = 20  # bond/ADR ratio is measured over the first N shared days


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


def _yahoo_daily_close(symbol: str, date_from, date_to) -> pd.Series:
    resp = requests.get(
        YAHOO_CHART_URL.format(symbol=symbol),
        params={"period1": _to_unix(date_from), "period2": _to_unix(date_to), "interval": "1d"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    return pd.Series(
        result["indicators"]["quote"][0]["close"],
        index=pd.to_datetime(result["timestamp"], unit="s").normalize(),
    ).dropna()


def adr_implied_fx_series(date_from, date_to, adr_pairs=None) -> pd.Series:
    """Daily ARS/USD rate implied by local stock vs. US ADR prices (median
    across pairs), from Yahoo Finance."""
    adr_pairs = adr_pairs or config.FX_ADR_PAIRS
    rates = {}
    for local_ticker, adr_ticker, shares_per_adr in adr_pairs:
        try:
            local = _yahoo_daily_close(f"{local_ticker}.BA", date_from, date_to)
            adr = _yahoo_daily_close(adr_ticker, date_from, date_to)
        except Exception as exc:
            print(f"  [warn] ADR FX pair {local_ticker}/{adr_ticker}: {exc}, skipping")
            continue
        both = pd.concat([local, adr], axis=1, keys=["local", "adr"]).dropna()
        both = both[both["adr"] > 0]
        rates[local_ticker] = both["local"] * shares_per_adr / both["adr"]

    if not rates:
        raise RuntimeError(f"Could not build an ADR-implied FX series from any pair ({adr_pairs}).")
    return pd.concat(rates, axis=1).median(axis=1).sort_index().rename("adr_implied_ccl")


def ccl_series(client: PPIClient, date_from, date_to) -> pd.Series:
    """Daily implied CCL: bond-pair rate where available, ADR-implied rate
    (rescaled to meet the bond rate) before the bonds existed."""
    bond = implied_fx_series(client, date_from, date_to)
    bond.index = pd.DatetimeIndex(bond.index).normalize()
    bond = bond.groupby(level=0).last()
    try:
        adr = adr_implied_fx_series(date_from, date_to)
    except RuntimeError as exc:
        print(f"  [warn] {exc} USD series will start when the bond pairs do.")
        return bond.rename("implied_ccl")

    overlap = bond.index.intersection(adr.index)[:SPLICE_OVERLAP_DAYS]
    if overlap.empty:
        print("  [warn] bond and ADR FX series don't overlap; not extending USD history.")
        return bond.rename("implied_ccl")
    scale = (bond.loc[overlap] / adr.loc[overlap]).median()

    early = adr.loc[adr.index < bond.index.min()] * scale
    return pd.concat([early, bond]).sort_index().rename("implied_ccl")
