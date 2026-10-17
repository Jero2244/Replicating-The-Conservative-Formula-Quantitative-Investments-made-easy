"""Central configuration: paths, PPI credentials, and formula parameters.

Credentials are read from a local `.env` file (gitignored) via python-dotenv.
Never hardcode real keys here.
"""
from pathlib import Path

from dotenv import load_dotenv
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# --- PPI credentials -------------------------------------------------------
PPI_PUBLIC_KEY = os.getenv("PPI_PUBLIC_KEY", "")
PPI_PRIVATE_KEY = os.getenv("PPI_PRIVATE_KEY", "")
PPI_SANDBOX = os.getenv("PPI_SANDBOX", "false").strip().lower() == "true"

# --- Paths -------------------------------------------------------------
CONFIG_DIR = PROJECT_ROOT / "config"
UNIVERSE_CSV = CONFIG_DIR / "universe.csv"

DATA_DIR = PROJECT_ROOT / "data"
DATA_RAW = DATA_DIR / "raw"
DATA_PROCESSED = DATA_DIR / "processed"
DATA_MANUAL = DATA_DIR / "manual"
DIVIDENDS_CSV = DATA_MANUAL / "dividends.csv"  # built by `python -m src.data_sources.dividends`
SHARES_OUTSTANDING_CSV = DATA_MANUAL / "shares_outstanding.csv"  # optional, for buyback yield

for _dir in (DATA_RAW, DATA_PROCESSED, DATA_MANUAL):
    _dir.mkdir(parents=True, exist_ok=True)

# --- Conservative Formula parameters (see ssrn-3145152.pdf methodology) ----
VOL_WINDOW_MONTHS = 36          # trailing volatility window (paper: 3-year)
MOMENTUM_LOOKBACK_MONTHS = 12   # 12-1 month momentum
MOMENTUM_SKIP_MONTHS = 1
REBALANCE_FREQ = "Q"            # quarterly, same as the paper

NPY_DIVIDEND_WINDOW_MONTHS = 12 # trailing dividend yield window
NPY_SHARES_WINDOW_MONTHS = 24   # buyback yield: latest shares vs 24-month average (paper)
MAX_EVENT_DIVIDEND_YIELD = 0.25 # single dividends above this fraction of the prior close
                                 # are treated as Yahoo data errors and dropped (stale prices,
                                 # unadjusted amounts — e.g. HAVA 2024 at ~30x the price)

LOW_VOL_PCT = 0.50              # bottom half by volatility is the eligible pool
TOP_PCT = 0.30                  # fraction of the low-vol pool selected as "Conservative"
                                 # (paper: 100/500 = 20% of the 1000-stock universe;
                                 # bumped up here because Argentina's investable universe
                                 # is far smaller, so a 20% cut leaves too few names)

# --- Argentine market specifics --------------------------------------------
MARKET = "BYMA"
INSTRUMENT_TYPE = "ACCIONES"
SETTLEMENT = "A-24HS"

# FX bond pairs used to derive an implied historical CCL/MEP rate
# (ARS-settled ticker, USD-settled ticker)
FX_BOND_PAIRS = [
    ("AL30", "AL30D"),
    ("GD30", "GD30D"),
]

# ADR pairs used to extend the implied CCL back before the AL30/GD30 bonds
# existed (Sep 2020): (BYMA ticker, US ADR ticker, local shares per ADR).
# YPF is left out: Yahoo rescales YPFD.BA's whole history for a 2026 split,
# so its local/ADR ratio is off by 10x.
FX_ADR_PAIRS = [
    ("GGAL", "GGAL", 10),
    ("PAMP", "PAM", 25),
    ("BMA", "BMA", 10),
]
