"""S&P Merval index history, used as the market benchmark.

PPI's `MarketData/Search` is scoped to tradeable instrument types (acciones,
bonos, etc.) and does not expose index series, so this pulls directly from
BYMA's public market-data API instead (same endpoint used by the local
`byma` skill, no API key required). BYMA's SSL chain doesn't verify against
the standard `certifi` bundle, so `verify=False` is used here too — the
connection is still TLS-encrypted, just without chain validation.

Known limitation: this endpoint silently caps history at roughly the last
2 years regardless of the requested `date_from` — a request for 2022-2026
comes back starting mid-2024. There's no documented way around this on the
free endpoint, so the Merval benchmark series in reports will be shorter
than the Conservative/Speculative portfolio series for long backtest windows.
"""
from __future__ import annotations

import urllib3
from datetime import date, datetime

import pandas as pd
import requests

# verify=False below is intentional (see module docstring); silence the
# resulting per-request warning instead of letting it spam stdout.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BYMA_BASE_URL = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free"


def _to_unix(d) -> int:
    if isinstance(d, str):
        d = datetime.strptime(d, "%Y-%m-%d")
    if isinstance(d, date) and not isinstance(d, datetime):
        d = datetime(d.year, d.month, d.day)
    return int(d.timestamp())


def fetch_merval_index(date_from, date_to, resolution: str = "D") -> pd.DataFrame:
    """Daily OHLC for the S&P Merval index (symbol "M") between date_from/date_to."""
    params = {
        "symbol": "M",
        "resolution": resolution,
        "from": _to_unix(date_from),
        "to": _to_unix(date_to),
    }
    resp = requests.get(
        f"{BYMA_BASE_URL}/chart/index-historical-series/history",
        params=params,
        verify=False,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()

    if payload.get("s") != "ok" or not payload.get("t"):
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    n = len(payload["t"])
    volume = payload.get("v") or []
    if len(volume) != n:
        # Index series routinely report an empty volume array.
        volume = [0] * n

    df = pd.DataFrame(
        {
            "date": pd.to_datetime(payload["t"], unit="s"),
            "open": payload["o"],
            "high": payload["h"],
            "low": payload["l"],
            "close": payload["c"],
            "volume": volume,
        }
    )
    return df.sort_values("date").reset_index(drop=True)
