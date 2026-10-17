"""Thin wrapper around the `ppi_client` package (PPI's official Python SDK).

Confirmed against ppi-client==1.2.4 source (ppi_client/api/marketdata.py,
ppi_client/api/accounts.py):

    PPI(sandbox=bool)
    ppi.account.login_api(api_key, api_secret)
    ppi.marketdata.search_instrument(ticker, instrument_name, market, instrument_type)
    ppi.marketdata.search(ticker, instrument_type, settlement, date_from, date_to)
    ppi.marketdata.current(ticker, instrument_type, settlement)

PPI has no endpoint to list "all instruments in a market" and no
dividends/corporate-actions endpoint — see src/data_sources/universe.py and
src/data_sources/dividends.py (Yahoo Finance) for how those gaps are handled.

Historical pulls are cached to disk (data/raw/) since PPI documents no rate
limit but a conservative delay is applied anyway, matching the pattern used
by the byma/data912 skills.
"""
from __future__ import annotations

import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from ppi_client.ppi import PPI

from src import config


def _fmt_date(d) -> str:
    if isinstance(d, (date, datetime)):
        return d.strftime("%Y-%m-%d")
    return str(d)


class PPIClient:
    """Authenticated, caching wrapper over the PPI Python SDK."""

    def __init__(
        self,
        public_key: str | None = None,
        private_key: str | None = None,
        sandbox: bool | None = None,
        cache_dir: Path | None = None,
        request_delay: float = 0.3,
    ):
        self.public_key = public_key or config.PPI_PUBLIC_KEY
        self.private_key = private_key or config.PPI_PRIVATE_KEY
        self.sandbox = config.PPI_SANDBOX if sandbox is None else sandbox
        self.cache_dir = Path(cache_dir or config.DATA_RAW)
        self.request_delay = request_delay
        self._client: PPI | None = None

    def _ensure_login(self) -> PPI:
        if self._client is not None:
            return self._client
        if not self.public_key or not self.private_key:
            raise RuntimeError(
                "PPI credentials are missing. Copy .env.example to .env and fill in "
                "PPI_PUBLIC_KEY / PPI_PRIVATE_KEY."
            )
        client = PPI(sandbox=self.sandbox)
        client.account.login_api(self.public_key, self.private_key)
        self._client = client
        return client

    def _throttle(self):
        time.sleep(self.request_delay)

    def search_instrument(
        self,
        ticker: str,
        instrument_name: str = "",
        market: str = config.MARKET,
        instrument_type: str = config.INSTRUMENT_TYPE,
    ):
        """Look up an instrument by ticker (PPI's only instrument-discovery endpoint)."""
        client = self._ensure_login()
        self._throttle()
        return client.marketdata.search_instrument(
            ticker=ticker,
            instrument_name=instrument_name,
            market=market,
            instrument_type=instrument_type,
        )

    def historical(
        self,
        ticker: str,
        date_from,
        date_to,
        instrument_type: str = config.INSTRUMENT_TYPE,
        settlement: str = config.SETTLEMENT,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Daily historical OHLC-ish series for `ticker` between date_from/date_to.

        Cached to data/raw/{ticker}_{date_from}_{date_to}.csv so repeat runs
        (e.g. re-running the backtest with the same window) don't re-hit the API.
        """
        date_from_s, date_to_s = _fmt_date(date_from), _fmt_date(date_to)
        cache_file = self.cache_dir / f"{ticker}_{date_from_s}_{date_to_s}.csv"

        if use_cache and cache_file.exists():
            df = pd.read_csv(cache_file)
            if not df.empty:
                df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
            return df

        client = self._ensure_login()
        self._throttle()
        raw = client.marketdata.search(
            ticker=ticker,
            instrument_type=instrument_type,
            settlement=settlement,
            date_from=date_from_s,
            date_to=date_to_s,
        )
        df = pd.DataFrame(raw)
        if not df.empty and "date" in df.columns:
            # PPI returns tz-aware timestamps (America/Argentina/Buenos_Aires),
            # and offsets are inconsistent across decades (Argentina's DST
            # rules changed over time), so pd.to_datetime without utc=True can
            # produce a mixed-offset object dtype rather than datetime64. Parse
            # as UTC first, then drop the tz — downstream monthly resampling
            # only needs date-level alignment, not the offset.
            df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
            df = df.sort_values("date").reset_index(drop=True)

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_file, index=False)
        return df

    def current(
        self,
        ticker: str,
        instrument_type: str = config.INSTRUMENT_TYPE,
        settlement: str = config.SETTLEMENT,
    ):
        client = self._ensure_login()
        self._throttle()
        return client.marketdata.current(
            ticker=ticker, instrument_type=instrument_type, settlement=settlement
        )
