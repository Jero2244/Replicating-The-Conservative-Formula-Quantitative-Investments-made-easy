"""Cash dividend history for the universe, from Yahoo Finance's public chart
API (`<TICKER>.BA`, no API key), written to data/manual/dividends.csv.

PPI has no dividends endpoint, so this is the dividend input for the NPY
factor (see src/formula/factors.py::net_payout_yield). Each row also stores
Yahoo's close on the trading day *before* the ex-date (`price_before_ex`), so
the per-event yield is computed on Yahoo's own split-adjustment basis and
never mixes Yahoo dividends with PPI prices. Under Argentine inflation this
also matters: a dividend is measured against the price when it was paid, not
against a price up to 12 months later.

Yahoo reports Argentine stock dividends ("dividendos en acciones") as splits;
those are not cash payouts and are ignored here, same as the paper's NPY.

Coverage is decent from ~2017 onward and thin before that. Tickers with no
Yahoo dividend records are treated as zero-dividend, which is right for most
of them but can't be distinguished from missing coverage — rows can be added
or corrected by hand (source = "manual"); manual rows are kept on re-fetch.

Usage:
    python -m src.data_sources.dividends
"""
from __future__ import annotations

import time

import pandas as pd
import requests

from src import config
from src.data_sources.benchmark import _to_unix
from src.data_sources.universe import load_universe

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
COLUMNS = ["ticker", "ex_date", "dividend_per_share", "currency", "source", "price_before_ex"]


def fetch_yahoo_dividends(ticker: str, date_from="1990-01-01", date_to=None) -> pd.DataFrame:
    """Cash dividends for one BYMA ticker, with the prior trading day's close."""
    date_to = date_to or pd.Timestamp.today().strftime("%Y-%m-%d")
    resp = requests.get(
        YAHOO_CHART_URL.format(symbol=f"{ticker}.BA"),
        params={"period1": _to_unix(date_from), "period2": _to_unix(date_to), "interval": "1d", "events": "div"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    if resp.status_code == 404:
        return pd.DataFrame(columns=COLUMNS)
    resp.raise_for_status()
    result = (resp.json().get("chart") or {}).get("result") or []
    if not result:
        return pd.DataFrame(columns=COLUMNS)
    result = result[0]

    divs = (result.get("events") or {}).get("dividends") or {}
    if not divs or not result.get("timestamp"):
        return pd.DataFrame(columns=COLUMNS)

    closes = pd.Series(
        result["indicators"]["quote"][0]["close"],
        index=pd.to_datetime(result["timestamp"], unit="s").normalize(),
    ).dropna()
    currency = (result.get("meta") or {}).get("currency") or "ARS"

    rows = []
    for d in divs.values():
        ex_date = pd.to_datetime(d["date"], unit="s").normalize()
        prior = closes.loc[closes.index < ex_date]
        rows.append(
            {
                "ticker": ticker,
                "ex_date": ex_date.date().isoformat(),
                "dividend_per_share": float(d["amount"]),
                "currency": currency,
                "source": "yahoo",
                "price_before_ex": float(prior.iloc[-1]) if not prior.empty else float("nan"),
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS).sort_values("ex_date")


def build_dividends_csv(request_delay: float = 0.3) -> pd.DataFrame:
    """Re-fetches Yahoo dividends for the whole universe into DIVIDENDS_CSV,
    keeping any existing non-Yahoo (hand-entered) rows."""
    frames = []
    if config.DIVIDENDS_CSV.exists():
        existing = pd.read_csv(config.DIVIDENDS_CSV)
        frames.append(existing[existing["source"] != "yahoo"])

    for ticker in load_universe()["ticker"]:
        try:
            df = fetch_yahoo_dividends(ticker)
        except Exception as exc:
            print(f"  [warn] {ticker}: {exc}, skipping")
            continue
        print(f"  {ticker}: {len(df)} dividends")
        if not df.empty:
            frames.append(df)
        time.sleep(request_delay)

    out = pd.concat(frames, ignore_index=True)[COLUMNS].sort_values(["ticker", "ex_date"])
    out.to_csv(config.DIVIDENDS_CSV, index=False)
    print(f"Wrote {len(out)} rows to {config.DIVIDENDS_CSV}")
    return out


if __name__ == "__main__":
    build_dividends_csv()
