# The Conservative Formula — Argentina (BYMA)

Tests whether ["The Conservative Formula" (Van Vliet & Blitz, 2018)](ssrn-3145152.pdf)
holds on the Argentine equity market, using the
[Portfolio Personal de Inversiones (PPI) API](https://itatppi.github.io/ppi-official-api-docs/)
for market data.

## Key findings

All figures: Apr 2011 – Sep 2026 (186 months), in nominal ARS and in USD at
the implied CCL rate.

1. **Adding Net Payout Yield (NPY) lowers returns in Argentina.** The paper
   ranks on three factors; here, the version *without* NPY (Low-Vol +
   Momentum) earns clearly more than the full formula *with* NPY, in both
   currencies:

   | Conservative portfolio | ARS CAGR | ARS total return | USD CAGR | USD total return |
   |---|---|---|---|---|
   | **Without NPY** (2-factor) | **58.3%** | **~1,237x** | **7.7%** | **~3.2x** |
   | With NPY (3-factor, as in the paper) | 47.8% | ~426x | 0.5% | ~1.09x |
   | Difference from adding NPY | **-10.5 pp / yr** | ~2.9x less | **-7.2 pp / yr** | ~2.9x less |

   NPY also lowers the Sharpe ratio (ARS 1.26 → 1.18, USD 0.39 → 0.22). It
   does cut volatility a little (ARS 44.3% → 40.1%, USD 43.5% → 39.9%), but
   not by enough to make up for the lost return.
2. **Only the version without NPY beats the market.** The Merval returned
   54.2% a year in ARS (Sharpe 1.15) and 4.9% in USD (Sharpe 0.34, ~2.1x).
   Without NPY the formula beats it in both (58.3% / 7.7%, Sharpe 1.26 /
   0.39); with NPY it falls behind in both (47.8% / 0.5%). In the charts
   below, that's the dashed blue line (without NPY) running above the green
   Merval line, and the solid blue one (with NPY) below it.
3. **The low-risk effect replicates, with a limit.** Conservative beats its
   Speculative opposite in both currencies and in both versions, with lower
   volatility. In ARS its worst drawdown is much smaller (-43% vs -58%). But
   in USD every portfolio, the Merval included, lost ~85% in the 2018–2020
   crisis: low volatility didn't protect against a collapse of the currency
   itself.
4. **Why NPY hurts: dividends weren't rewarded in Argentina.** Tested on its
   own, NPY has no premium here. Stocks that paid no dividend returned
   14.6% per quarter on average, versus 12.8% for the highest-yielding
   payers, which won in only 46% of quarters. Payers fell furthest behind in
   2011–15 and 2020–23, the capital-control and high-inflation years when
   the central bank (BCRA) restricted dividends. High payers did lead in
   2016–19 and 2024–26.

Caveats: this NPY is dividends only (no buyback data); the universe is just
64 stocks with portfolios of ~8–10 names; and before Sep 2020 the USD
figures use an ADR-implied exchange rate (see below). Details are in
[Results](#results-20112026-backtest-64-byma-stocks) and
[Net Payout Yield](#net-payout-yield-npy).

## What the paper says

Select the top 100 of the largest 1,000 US stocks based on: low 3-year return
volatility, high Net Payout Yield (dividend yield + net buyback yield), and
strong 12-1 month price momentum. Equal-weight, rebalance quarterly. The
paper finds this beats the market by a wide margin, with lower risk, in the
US, Europe, Japan, and Emerging Markets.

## What this project does differently, and why

PPI's API is missing three things the original methodology needs:

- **No bulk instrument-listing endpoint** — only search-by-ticker. So the
  Argentine universe (`config/universe.csv`, ~65 BYMA-listed common stocks —
  Panel Líder + Panel General) is a curated static list, not pulled live.
- **No dividends/buybacks/corporate-actions endpoint** — so dividends come
  from Yahoo Finance instead (see [Net Payout Yield](#net-payout-yield-npy)
  below), and the buyback half of NPY is left out for lack of a
  shares-outstanding history.
- **No historical FX endpoint** — the ARS/USD (CCL) rate is implied from
  securities that trade in both currencies. From Sep 2020 it comes from
  ARS-vs-USD-settled bond pairs (`AL30`/`AL30D`, `GD30`/`GD30D`). Those bonds
  didn't exist before the 2020 restructuring, so earlier months use the
  ADR-implied rate: Buenos Aires price × shares per ADR ÷ New York ADR price
  for GGAL, PAM and BMA (median, from Yahoo Finance), rescaled to meet the
  bond rate. The ADR rate runs ~3% above the bond rate where both exist and
  their monthly changes correlate at ~0.95. Results are reported in both nominal ARS and
  USD-implied terms, since Argentina's inflation/devaluation history makes
  nominal ARS returns hard to compare with the paper's US/Europe/Japan/EM
  figures (all reported in USD).

## Net Payout Yield (NPY)

The paper's NPY is dividend yield + net buyback yield (latest shares
outstanding vs. their 24-month average). Within each volatility half, a
stock's momentum rank and NPY rank are averaged; Conservative takes the best
combined score from the low-vol half, Speculative the worst from the
high-vol half. This project implements it as:

- **Dividend yield** — trailing 12-month cash dividends from Yahoo Finance
  (`<TICKER>.BA`), stored in [`data/manual/dividends.csv`](data/manual/dividends.csv)
  (rebuild with `python -m src.data_sources.dividends`). Each dividend is
  divided by Yahoo's close the day before its ex-date and the 12 months of
  per-event yields are summed — so every payout is measured against the
  price when it was paid, which matters under Argentine inflation, and
  Yahoo's dividends are never mixed with PPI's differently-adjusted prices.
- **Data cleaning** — any single dividend above 25% of the prior close is
  treated as a Yahoo data error and dropped (`MAX_EVENT_DIVIDEND_YIELD` in
  `src/config.py`). That catches stale prices and unadjusted amounts like
  HAVA's 2024 "dividend" at ~30x the share price; 25 of ~810 events are
  dropped. Stock dividends ("dividendos en acciones", which Yahoo reports as
  splits) aren't cash payouts and are ignored, as in the paper.
- **Buyback yield** — not included: Yahoo only has the last few years of
  share counts. If you source a split-adjusted history, put it in
  `data/manual/shares_outstanding.csv` (`ticker,date,shares_outstanding`)
  and it's added to NPY automatically.
- **Coverage** — stocks with no Yahoo dividend records count as
  zero-yield. Roughly 40–50% of the universe pays a dividend in a typical
  year, dipping to 20–30% in 2020–21 (BCRA dividend restrictions). Rows can
  be corrected or added by hand with `source = manual`; re-fetching keeps
  them.

When `data/manual/dividends.csv` exists, the backtest builds both versions
(with and without NPY) so they can be compared; without it, only the
2-factor (Low-Vol + Momentum) version is built.

## Universe

The full investable universe is [`config/universe.csv`](config/universe.csv) —
65 curated BYMA-listed common stocks (Panel Líder + Panel General), seeded
from the local `data912` skill's static ticker catalog. `name`/`sector` are
left blank (`—`) where not confidently known rather than guessed; edit the
CSV directly to fill gaps or add/remove tickers.

`python -m src.data_sources.universe` flags any ticker that doesn't resolve
via PPI's `SearchInstrument`, so it's worth re-running after editing the list.
Known cases:

- `MTR` (Matba Rofex) merged with MAE and has traded as **`A3`** (A3 Mercados)
  since 2025-03-05; the list now uses `A3`. PPI carries the old MTR price
  history under `A3`, back to 2020-09.
- `DYCA` (Dycasa) is still on BYMA's Panel General list but didn't resolve
  via PPI on the last check; the backtest just skips it if it returns no data.
- `HSAT`'s company couldn't be confirmed, so its name/sector stay blank.

### Panel Líder (21 stocks)

| Ticker | Name | Sector |
|---|---|---|
| ALUA | Aluar Aluminio Argentino | Materials |
| BBAR | Banco BBVA Argentina | Financials |
| BMA | Banco Macro | Financials |
| BYMA | Bolsas y Mercados Argentinos | Financials |
| CEPU | Central Puerto | Utilities |
| COME | Sociedad Comercial del Plata | Holding |
| CRES | Cresud | RealEstate |
| CVH | Cablevision Holding | Telecom |
| EDN | Edenor | Utilities |
| GGAL | Grupo Financiero Galicia | Financials |
| LOMA | Loma Negra | Materials |
| MIRG | Mirgor | Industrials |
| PAMP | Pampa Energia | Energy |
| SUPV | Grupo Supervielle | Financials |
| TECO2 | Telecom Argentina | Telecom |
| TGNO4 | Transportadora de Gas del Norte | Utilities |
| TGSU2 | Transportadora de Gas del Sur | Utilities |
| TRAN | Transener | Utilities |
| TXAR | Ternium Argentina | Materials |
| VALO | Grupo Financiero Valores | Financials |
| YPFD | YPF | Energy |

<details>
<summary><b>Panel General (44 stocks)</b> — click to expand</summary>

| Ticker | Name | Sector |
|---|---|---|
| A3 | A3 Mercados (ex Matba Rofex) | Financials |
| AGRO | Agrometal | Industrials |
| AUSO | Autopistas del Sol | Industrials |
| BHIP | Banco Hipotecario | Financials |
| BOLT | Boldt | ConsumerDiscretionary |
| BPAT | Banco Patagonia | Financials |
| CADO | Carlos Casado | RealEstate |
| CAPX | Capex | Energy |
| CARC | Carboclor | Materials |
| CECO2 | Central Costanera | Utilities |
| CELU | Celulosa Argentina | Materials |
| CGPA2 | Camuzzi Gas Pampeana | Utilities |
| CTIO | Consultatio | RealEstate |
| DGCU2 | Distribuidora de Gas Cuyana | Utilities |
| DOME | Domec | ConsumerDiscretionary |
| DYCA | Dycasa | Industrials |
| FERR | Ferrum | Industrials |
| FIPL | Fiplasto | Materials |
| GAMI | B-Gaming (Boldt Gaming) | ConsumerDiscretionary |
| GARO | Garovaglio y Zorraquin | Holding |
| GBAN | Naturgy BAN (Gas Natural BAN) | Utilities |
| GCDI | GCDI (ex TGLT) | Industrials |
| GCLA | Grupo Clarin | Telecom |
| GRIM | Grimoldi | ConsumerDiscretionary |
| HARG | Holcim Argentina | Materials |
| HAVA | Havanna Holding | ConsumerStaples |
| HSAT | — | — |
| INTR | Compania Introductora de Buenos Aires | ConsumerStaples |
| INVJ | Inversora Juramento | ConsumerStaples |
| IRSA | IRSA Inversiones y Representaciones | RealEstate |
| LEDE | Ledesma | ConsumerStaples |
| LONG | Longvie | ConsumerDiscretionary |
| METR | Metrogas | Utilities |
| MOLA | Molinos Agro | ConsumerStaples |
| MOLI | Molinos Rio de la Plata | ConsumerStaples |
| MORI | Morixe | ConsumerStaples |
| OEST | Oeste | Industrials |
| PATA | Importadora y Exportadora de la Patagonia | ConsumerDiscretionary |
| POLL | Polledo | ConsumerStaples |
| RICH | Laboratorios Richmond | HealthCare |
| RIGO | Rigolleau | Materials |
| ROSE | Instituto Rosenbusch | HealthCare |
| SAMI | San Miguel | ConsumerStaples |
| SEMI | Molinos Juan Semino | ConsumerStaples |

</details>

## Results (2011–2026 backtest, 64 BYMA stocks)

Live run against PPI (data to 2026-09-30), quarterly rebalance. Both
versions are shown: the full formula **with NPY** (Low-Vol + Momentum + NPY,
as in the paper) and the 2-factor version **without NPY** (Low-Vol +
Momentum). **Conservative** = low-vol half of the universe, best ~30% by
momentum (averaged with NPY rank, in the with-NPY version). **Speculative**
= high-vol half, worst ~30% — the paper's long-short comparison portfolio,
not something to actually hold. The Merval is measured over the same
months. Full numbers in
[`reports/performance_summary.csv`](reports/performance_summary.csv).

### Nominal ARS (Apr 2011 – Sep 2026, 186 months)

| Portfolio | CAGR | Ann. Vol | Sharpe | Max Drawdown | Total return |
|---|---|---|---|---|---|
| **Conservative, without NPY** | **58.3%** | 44.3% | **1.26** | -43.0% | ~1,237x |
| Conservative, with NPY | 47.8% | 40.1% | 1.18 | -43.0% | ~426x |
| Speculative, without NPY | 28.8% | 50.3% | 0.73 | -60.4% | ~50x |
| Speculative, with NPY | 39.9% | 55.0% | 0.86 | -58.3% | ~182x |
| Merval | 54.2% | 47.2% | 1.15 | -42.0% | ~821x |

![Equity curve, ARS nominal](reports/equity_curve_ars.png)

### USD-implied via CCL (Apr 2011 – Sep 2026, 186 months)

| Portfolio | CAGR | Ann. Vol | Sharpe | Max Drawdown | Total return |
|---|---|---|---|---|---|
| **Conservative, without NPY** | **7.7%** | 43.5% | **0.39** | -85.3% | ~3.2x |
| Conservative, with NPY | 0.5% | 39.9% | 0.22 | -85.6% | ~1.09x |
| Speculative, without NPY | -12.4% | 47.1% | -0.04 | -93.0% | ~0.13x |
| Speculative, with NPY | -4.8% | 51.5% | 0.15 | -91.5% | ~0.47x |
| Merval | 4.9% | 46.8% | 0.34 | -84.5% | ~2.1x |

![Equity curve, USD implied](reports/equity_curve_usd.png)

Solid lines are the with-NPY versions, dashed lines the without-NPY ones.
See [Key findings](#key-findings) for what these numbers say.

**Caveats before reading too much into this:**
- NPY here is dividend yield only (no buyback data, see above), from Yahoo
  data that needed cleaning — a noisier signal than the paper's.
- Before Sep 2020 the USD figures rest on the ADR-implied CCL rather than
  the bond-implied one (see above). Over just Oct 2020 – Sep 2026, where
  the bond rate exists, the version without NPY slightly trailed the Merval
  in USD (34.0% vs 34.8% a year); its USD edge comes from the earlier years.
- 64 stocks (many illiquid "Panel General" small-caps) is a much thinner
  and noisier universe than the paper's 1,000 large-cap US stocks, and the
  portfolios hold only ~8–10 names — treat this as a suggestive first look,
  not a robust replication.

Regenerate these with `python -m src.backtest.run_backtest --start 2010-01-01 --end 2026-09-30`
then `python -m src.backtest.report` (see below), and copy the outputs from
`data/processed/` into `reports/`.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# then edit .env with your real PPI_PUBLIC_KEY / PPI_PRIVATE_KEY
# (PPI account -> "Gestiones" -> activate API service)
```

`.env` is gitignored — real credentials never get committed.

## Running the pipeline

```bash
# 1. Sanity-check the universe resolves against PPI
python -m src.data_sources.universe

# 2. (Optional) refresh dividends from Yahoo Finance for the NPY factor
python -m src.data_sources.dividends

# 3. Pull history, build the Conservative/Speculative portfolios, compute
#    ARS + USD-implied return series
python -m src.backtest.run_backtest --start 2010-01-01

# 4. Performance summary (CAGR, Sharpe, max drawdown, vol) + equity-curve plots,
#    for Conservative vs Speculative vs Merval, in both currencies
python -m src.backtest.report
```

Outputs land in `data/processed/` (gitignored — regenerate anytime by
re-running the pipeline): `portfolio_returns.csv`, `holdings.json`,
`performance_summary.csv`, `equity_curve_ars.png`, `equity_curve_usd.png`.

## Tests

```bash
pytest tests/
```

Unit tests run on synthetic data only — no PPI credentials required.

## Project layout

```
config/universe.csv           # curated Argentine stock universe (ticker, name, panel, sector)
reports/                      # committed snapshot backing the Results section above
  performance_summary.csv, equity_curve_ars.png, equity_curve_usd.png
data/
  raw/                        # gitignored — cached PPI historical pulls
  processed/                  # gitignored — factor scores, returns, reports, plots
  manual/dividends.csv          # cash dividends from Yahoo (+ any manual rows), for NPY
  manual/dividends_template.csv # column layout for dividends.csv
src/
  config.py                   # paths, PPI credentials (.env), formula parameters
  data_sources/
    ppi_client.py             # PPI SDK wrapper (auth, historical search, caching)
    universe.py                # loads + validates config/universe.csv against PPI
    fx.py                      # implied CCL: bond pairs, extended back with ADR pairs
    benchmark.py                # S&P Merval index history (Yahoo ^MERV, BYMA fallback)
    dividends.py                # cash dividend history (Yahoo .BA) -> data/manual/dividends.csv
  formula/
    factors.py                 # trailing volatility, 12-1 momentum, net payout yield
    portfolio.py                # low-vol split + momentum/NPY ranking -> Conservative/Speculative
  backtest/
    run_backtest.py             # end-to-end pipeline
    ratios.py                   # CAGR, vol, Sharpe, max drawdown
    report.py                   # performance metrics + plots
tests/                         # unit tests on synthetic data
```
