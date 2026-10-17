"""S&P Merval index history, used as the market benchmark.

PPI's `MarketData/Search` is scoped to tradeable instrument types (acciones,
bonos, etc.) and does not expose index series, so the index comes from
outside PPI:

1. Yahoo Finance's public chart API (`^MERV`, no API key) — primary source.
   History goes back to 1996, so it covers the full backtest window.
2. BYMA's free market-data API — fallback only. It silently caps history at
   roughly the last 2 years regardless of the requested `date_from`, which is
   why it's no longer the primary source. BYMA's SSL chain doesn't verify
   against the standard `certifi` bundle, so `verify=False` is used there —
   the connection is still TLS-encrypted, just without chain validation.
"""
from __future__ import annotations

import urllib3
from datetime import date, datetime

import pandas as pd
import requests

# verify=False below is intentional (see module docstring); silence the
# resulting per-request warning instead of letting it spam stdout.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EMERV"
BYMA_BASE_URL = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free"

_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


def _to_unix(d) -> int:
    if isinstance(d, str):
        d = datetime.strptime(d, "%Y-%m-%d")
    if isinstance(d, date) and not isinstance(d, datetime):
        d = datetime(d.year, d.month, d.day)
    return int(d.timestamp())


def _fetch_yahoo(date_from, date_to) -> pd.DataFrame:
    resp = requests.get(
        YAHOO_CHART_URL,
        params={"period1": _to_unix(date_from), "period2": _to_unix(date_to), "interval": "1d"},
        # Yahoo rejects requests without a browser-like User-Agent.
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    resp.raise_for_status()
    result = (resp.json().get("chart") or {}).get("result") or []
    if not result or not result[0].get("timestamp"):
        return pd.DataFrame(columns=_COLUMNS)

    quote = result[0]["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(result[0]["timestamp"], unit="s"),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
            "volume": quote.get("volume"),
        }
    )
    # Yahoo returns null rows for holidays/missing sessions.
    df = df.dropna(subset=["close"])
    df["volume"] = df["volume"].fillna(0)
    return df.sort_values("date").reset_index(drop=True)


def _fetch_byma(date_from, date_to, resolution: str = "D") -> pd.DataFrame:
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
        return pd.DataFrame(columns=_COLUMNS)

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


def fetch_merval_index(date_from, date_to) -> pd.DataFrame:
    """Daily OHLC for the S&P Merval index between date_from/date_to.

    Tries Yahoo Finance first (full history); falls back to BYMA (~2 years
    only) if Yahoo fails or returns nothing.
    """
    try:
        df = _fetch_yahoo(date_from, date_to)
        if not df.empty:
            return df
        print("  [warn] Yahoo returned no Merval data, falling back to BYMA (~2y history only)")
    except Exception as exc:
        print(f"  [warn] Yahoo Merval fetch failed ({exc}), falling back to BYMA (~2y history only)")
    return _fetch_byma(date_from, date_to)
