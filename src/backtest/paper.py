"""Paper-style PDF write-up of the backtest, in the format of Van Vliet & Blitz
(2018), built from the return series produced by run_backtest.py.

The prose cites the current results; re-read it after a re-run with new data.

Usage:
    python -m src.backtest.paper
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from src import config

AUTHOR = "Jeronimo Juarez Pacheco"
OUT = config.DATA_PROCESSED / "conservative_formula_argentina.pdf"
TMP = Path(tempfile.mkdtemp())

r = pd.read_csv(config.DATA_PROCESSED / "portfolio_returns.csv",
                parse_dates=["date"], index_col="date").dropna()
N = len(r)

PORTS = [("conservative_no_npy", "Conservative, without NPY"),
         ("conservative", "Conservative, with NPY"),
         ("speculative_no_npy", "Speculative, without NPY"),
         ("speculative", "Speculative, with NPY"),
         ("merval", "S&P Merval")]


def stats(x):
    w = (1 + x).cumprod()
    return dict(cagr=w.iloc[-1] ** (12 / len(x)) - 1,
                vol=x.std() * np.sqrt(12),
                sharpe=x.mean() / x.std() * np.sqrt(12),
                mdd=(w / np.maximum(w.cummax(), 1) - 1).min(),
                mult=w.iloc[-1])


def capm(y, m):
    X = np.column_stack([np.ones(len(m)), m])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ b
    se = np.sqrt(res.var(ddof=2) * np.linalg.inv(X.T @ X)[0, 0])
    return (1 + b[0]) ** 12 - 1, b[0] / se, b[1]


def pct(v, d=1):
    return f"{v * 100:.{d}f}%"


# ---------------------------------------------------------------- figures
plt.rcParams.update({"font.family": "serif", "font.size": 9,
                     "axes.spines.top": False, "axes.spines.right": False})
STYLE = {"conservative_no_npy": ("#1f4e79", "--"), "conservative": ("#1f4e79", "-"),
         "speculative_no_npy": ("#b03a2e", "--"), "speculative": ("#b03a2e", "-"),
         "merval": ("#2e7d32", "-")}


def equity_fig(ccy, path):
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    for key, label in PORTS:
        c, ls = STYLE[key]
        ax.plot((1 + r[f"{key}_{ccy}"]).cumprod(), color=c, ls=ls, lw=1.2, label=label)
    ax.set_yscale("log")
    ax.set_ylabel(f"Growth of 1 {'ARS' if ccy == 'ars' else 'USD'} (log scale)")
    ax.grid(axis="y", color="#ddd", lw=0.5)
    ax.legend(frameon=False, fontsize=7.5, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def bar_fig(path):
    cal = (1 + r).groupby(r.index.year).prod() - 1
    fig, ax = plt.subplots(figsize=(6.6, 2.8))
    yrs = cal.index.values
    w = 0.27
    for i, (key, label, c) in enumerate([("conservative_no_npy_usd", "Conservative, without NPY", "#1f4e79"),
                                          ("conservative_usd", "Conservative, with NPY", "#8fb3d9"),
                                          ("merval_usd", "S&P Merval", "#2e7d32")]):
        ax.bar(yrs + (i - 1) * w, cal[key] * 100, w, color=c, label=label)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylabel("Calendar-year return, USD (%)")
    ax.set_xticks(yrs)
    ax.set_xticklabels([str(y) if y not in (2011, 2026) else f"{y}*" for y in yrs], fontsize=7)
    ax.legend(frameon=False, fontsize=7.5)
    ax.grid(axis="y", color="#ddd", lw=0.5)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


equity_fig("ars", TMP / "fig_ars.png")
equity_fig("usd", TMP / "fig_usd.png")
bar_fig(TMP / "fig_years.png")

# ---------------------------------------------------------------- styles
BASE = dict(fontName="Times-Roman", fontSize=10.5, leading=14.5)
body = ParagraphStyle("body", alignment=TA_JUSTIFY, spaceAfter=7, **BASE)
title = ParagraphStyle("title", fontName="Times-Bold", fontSize=18, leading=23, alignment=TA_CENTER)
center = ParagraphStyle("center", alignment=TA_CENTER, **BASE)
abstract = ParagraphStyle("abs", parent=body, leftIndent=1.2 * cm, rightIndent=1.2 * cm)
h1 = ParagraphStyle("h1", fontName="Times-Bold", fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=6, keepWithNext=1)
caption = ParagraphStyle("cap", fontName="Times-Bold", fontSize=10, leading=13, spaceBefore=6, spaceAfter=3)
note = ParagraphStyle("note", fontName="Times-Italic", fontSize=8.5, leading=11, alignment=TA_JUSTIFY, spaceAfter=10)
cell = ParagraphStyle("cell", fontName="Times-Roman", fontSize=9, leading=11)
foot = ParagraphStyle("foot", fontName="Times-Roman", fontSize=8.5, leading=11)

P = lambda t, s=body: Paragraph(t, s)


def table(header, rows, widths, bold_rows=()):
    data = [[Paragraph(f"<b>{h}</b>", cell) for h in header]]
    for i, row in enumerate(rows):
        fmt = "<b>{}</b>" if i in bold_rows else "{}"
        data.append([Paragraph(fmt.format(c.replace("&", "&amp;")), cell) for c in row])
    t = Table(data, colWidths=widths, hAlign="CENTER")
    t.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.9, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 0.9, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def perf_rows(ccy):
    out = []
    for key, label in PORTS:
        s = stats(r[f"{key}_{ccy}"])
        out.append([label, pct(s["cagr"]), pct(s["vol"]), f"{s['sharpe']:.2f}",
                    pct(s["mdd"]), f"{s['mult']:,.2f}x" if s["mult"] < 10 else f"{s['mult']:,.0f}x"])
    return out


def capm_rows():
    out = []
    for key, label in PORTS[:4]:
        row = [label]
        for ccy in ("ars", "usd"):
            a, t, b = capm(r[f"{key}_{ccy}"].values, r[f"merval_{ccy}"].values)
            row += [pct(a), f"{t:.2f}", f"{b:.2f}"]
        out.append(row)
    for v, label in (("_no_npy", "Cons. minus Spec., without NPY"), ("", "Cons. minus Spec., with NPY")):
        row = [label]
        for ccy in ("ars", "usd"):
            s = r[f"conservative{v}_{ccy}"] - r[f"speculative{v}_{ccy}"]
            row += [pct(s.mean() * 12), f"{s.mean() / s.std() * np.sqrt(len(s)):.2f}", "–"]
        out.append(row)
    return out


def period_rows():
    out = []
    for a, b, lbl in [("2011", "2015", "Apr 2011 – Dec 2015"), ("2016", "2019", "2016 – 2019"),
                      ("2020", "2023", "2020 – 2023"), ("2024", "2026", "2024 – Sep 2026")]:
        s = r.loc[a:b]
        out.append([lbl] + [pct(stats(s[f"{k}_usd"])["cagr"]) for k, _ in PORTS])
    s = r.loc["2020-10":]
    out.append(["Oct 2020 – Sep 2026†"] + [pct(stats(s[f"{k}_usd"])["cagr"]) for k, _ in PORTS])
    return out


S = {k: {c: stats(r[f"{k}_{c}"]) for c in ("ars", "usd")} for k, _ in PORTS}
cs = r["conservative_no_npy_usd"] - r["speculative_no_npy_usd"]
cs_t = cs.mean() / cs.std() * np.sqrt(N)

# ---------------------------------------------------------------- content
story = []
story += [Spacer(1, 1.5 * cm),
          P("The Conservative Formula in Argentina:<br/>Does Quantitative Investing Made Easy Travel to BYMA?", title),
          Spacer(1, 0.6 * cm),
          P(AUTHOR, center),
          P("October 2026", center),
          Spacer(1, 0.8 * cm)]

story.append(P(
    f"We replicate the Conservative Formula of Van Vliet and Blitz (2018), which selects stocks on low "
    f"return volatility, high net payout yield (NPY) and strong 12-1 month price momentum, on a universe "
    f"of 64 stocks listed on Bolsas y Mercados Argentinos (BYMA) from April 2011 to September 2026 "
    f"({N} months). Returns are measured both in nominal pesos and in US dollars at the implied "
    f"<i>contado con liquidación</i> (CCL) exchange rate. The low-risk side of the formula replicates: a "
    f"two-factor version based on volatility and momentum alone compounds at "
    f"{pct(S['conservative_no_npy']['ars']['cagr'])} per year in pesos and "
    f"{pct(S['conservative_no_npy']['usd']['cagr'])} in dollars, ahead of the S&amp;P Merval "
    f"({pct(S['merval']['ars']['cagr'])} and {pct(S['merval']['usd']['cagr'])}), and beats its speculative "
    f"counterpart by about 19 percent per year (t = {cs_t:.2f}). Adding NPY, as the original formula "
    f"prescribes, <i>lowers</i> the return by roughly 10.5 percentage points per year in pesos and 7.2 in "
    f"dollars, leaving the full formula behind the market. We trace this to the absence of a dividend "
    f"premium in Argentina during years of capital controls and central-bank dividend restrictions. Low "
    f"volatility did not protect dollar-based investors against the 2018–2020 currency collapse, when "
    f"every portfolio lost about 85 percent.", abstract))
story.append(Spacer(1, 0.3 * cm))
story.append(P("<b>Keywords:</b> low volatility, momentum, net payout yield, emerging markets, Argentina", abstract))
story.append(P("<b>JEL classification:</b> G11, G12, G15", abstract))
story.append(Spacer(1, 1.2 * cm))
story.append(P(
    "This is an independent, non-peer-reviewed replication. Market data from the Portfolio Personal de "
    "Inversiones (PPI) API; dividends and ADR prices from Yahoo Finance. Code and data snapshot: the "
    "<i>Replicating-The-Conservative-Formula</i> repository. Nothing here is investment advice.", foot))
story.append(PageBreak())

# 1. Introduction
story.append(P("1. Introduction", h1))
story.append(P(
    "Van Vliet and Blitz (2018) propose a deliberately simple investment rule. From the 1,000 largest US "
    "stocks, keep the 500 with the lowest three-year return volatility, then rank them on the average of "
    "their net payout yield and 12-1 month momentum ranks and buy the top 100, equally weighted and "
    "rebalanced quarterly. Using price and dividend data back to 1929, they report a compounded return of "
    "15.1 percent per year, a 12.8 percent annual spread over a speculative portfolio with the opposite "
    "characteristics, and similar results in Europe, Japan and emerging markets. Because the formula needs "
    "no accounting data and has only three inputs, it is a natural candidate for out-of-sample testing."))
story.append(P(
    "Argentina is a demanding test case. Over our sample the peso lost more than 99 percent of its value "
    "against the dollar, inflation ran in double and at times triple digits, the country went through a "
    "sovereign default and debt restructuring, and capital controls (the <i>cepo</i>) were in place for "
    "much of the period, including restrictions by the central bank (BCRA) on dividend payments. The "
    "listed market is also small: our universe has 64 stocks, many of them thinly traded. If the formula's "
    "factor premiums are universal, they should show up here too; if they depend on institutional "
    "conditions, Argentina is where that should be visible."))
story.append(P(
    "We find a split answer. The low-risk and momentum components replicate: the conservative portfolio "
    "beats both its speculative mirror image and, without NPY, the market index. The payout component "
    "does not. Over the full sample, adding NPY to the ranking reduces returns substantially in both "
    "currencies, and on its own NPY carries no premium. Section 2 describes the data and the adjustments "
    "the Argentine setting requires, Section 3 presents the main results, Section 4 looks at performance "
    "through time, Section 5 examines why NPY fails, Section 6 discusses limitations, and Section 7 "
    "concludes."))

# 2. Data
story.append(P("2. Data and methodology", h1))
story.append(P(
    "<b>Universe.</b> PPI's API has no bulk instrument listing, so the universe is a curated static list "
    "of 65 BYMA common stocks: the 21 members of the Panel Líder and 44 from the Panel General. One "
    "ticker (DYCA) returns no data, leaving 64. The list is fixed through time, so stocks that delisted "
    "before 2026 are absent, which introduces some survivorship bias."))
story.append(P(
    "<b>Prices and exchange rate.</b> Daily prices come from PPI and are converted to month-end returns. "
    "Because PPI offers no historical FX series, we imply the CCL rate from securities traded in both "
    "currencies. From September 2020 we use ARS- and USD-settled pairs of the AL30 and GD30 sovereign "
    "bonds. These bonds were issued in the 2020 restructuring, so for earlier months we use the "
    "ADR-implied rate (Buenos Aires price × shares per ADR ÷ New York ADR price) for GGAL, PAM and BMA, "
    "taking the median and rescaling it to meet the bond rate. Where both exist, the ADR rate runs about "
    "3 percent above the bond rate and their monthly changes correlate at roughly 0.95."))
story.append(P(
    "<b>Factors.</b> Following the paper, volatility is the standard deviation of the trailing 36 monthly "
    "returns and momentum is the cumulative return from month <i>t</i>−12 to <i>t</i>−1. NPY in the "
    "original is dividend yield plus net buyback yield. PPI has no corporate-actions data, so we build "
    "trailing 12-month cash dividend yields from Yahoo Finance: each dividend is divided by the close on "
    "the day before its ex-date and the yields are summed, which keeps every payout measured against a "
    "contemporaneous price under high inflation. Single dividends above 25 percent of the prior close "
    "are treated as data errors and dropped (25 of about 810 events). Stock dividends are ignored. No "
    "split-adjusted share-count history is available, so the buyback leg is omitted; stocks without "
    "dividend records count as zero-yield."))
story.append(P(
    "<b>Portfolio construction.</b> At each quarter-end the universe is split at the median volatility. "
    "The <i>Conservative</i> portfolio takes the best 30 percent of the low-volatility half ranked on the "
    "average of the momentum and NPY ranks; the <i>Speculative</i> portfolio takes the worst 30 percent of "
    "the high-volatility half. The paper's cut is 20 percent (100 of 500); we raise it to 30 percent "
    "because a 20 percent cut of a 64-stock universe would leave only five or six names. Even so, the "
    "conservative portfolio holds 7 to 10 stocks (8.5 on average). Portfolios are equal-weighted at each "
    "rebalance and held for the quarter. We build two versions: the full three-factor formula "
    "(<i>with NPY</i>) and a two-factor version ranking on momentum alone within each volatility half "
    "(<i>without NPY</i>). The benchmark is the S&amp;P Merval index over the same months. Sharpe ratios "
    "use a zero risk-free rate, since no consistent peso or dollar risk-free series is available for the "
    "whole period. The first holdings are formed in March 2011, once 36 months of data are available, so "
    "the evaluation period is April 2011 to September 2026."))

# 3. Results
story.append(P("3. Main results", h1))
story.append(P(
    f"Table 1 reports performance in both currencies. In pesos the two-factor conservative portfolio "
    f"compounds at {pct(S['conservative_no_npy']['ars']['cagr'])} per year with a Sharpe ratio of "
    f"{S['conservative_no_npy']['ars']['sharpe']:.2f}, against {pct(S['merval']['ars']['cagr'])} and "
    f"{S['merval']['ars']['sharpe']:.2f} for the Merval, and with lower volatility "
    f"({pct(S['conservative_no_npy']['ars']['vol'])} versus {pct(S['merval']['ars']['vol'])}). The full "
    f"formula with NPY earns {pct(S['conservative']['ars']['cagr'])}, behind the index. Nominal peso "
    f"figures are inflated by depreciation and inflation and are not comparable with the paper's dollar "
    f"results, so Panel B is the more relevant comparison. In dollars the two-factor portfolio returns "
    f"{pct(S['conservative_no_npy']['usd']['cagr'])} per year against {pct(S['merval']['usd']['cagr'])} "
    f"for the Merval, while the version with NPY barely breaks even at "
    f"{pct(S['conservative']['usd']['cagr'])}."))

story.append(KeepTogether([
    P("Table 1: Performance of the Conservative Formula in Argentina, April 2011 – September 2026", caption),
    P("<i>Panel A: Nominal ARS</i>", cell), Spacer(1, 2),
    table(["Portfolio", "CAGR", "Ann. vol.", "Sharpe", "Max DD", "Growth of 1"], perf_rows("ars"),
          [5.2 * cm, 2 * cm, 2 * cm, 1.7 * cm, 2 * cm, 2.3 * cm], bold_rows=(0,)),
    Spacer(1, 6),
    P("<i>Panel B: USD at implied CCL</i>", cell), Spacer(1, 2),
    table(["Portfolio", "CAGR", "Ann. vol.", "Sharpe", "Max DD", "Growth of 1"], perf_rows("usd"),
          [5.2 * cm, 2 * cm, 2 * cm, 1.7 * cm, 2 * cm, 2.3 * cm], bold_rows=(0,)),
    P(f"Monthly returns, {N} months. Equal-weighted portfolios rebalanced quarterly. <i>With NPY</i> ranks "
      "on momentum and dividend yield within each volatility half; <i>without NPY</i> on momentum only. "
      "Sharpe ratios use a zero risk-free rate. Max DD is the largest peak-to-trough decline.", note)]))

story.append(P(
    "Figures 1 and 2 show the cumulative paths. In pesos the dashed two-factor line pulls ahead of the "
    "Merval from 2015 onwards. In dollars the picture is dominated by the 2018–2020 crisis: the peso "
    "devaluations of 2018 and 2019 and the reinstatement of capital controls took every portfolio down by "
    "roughly 85 percent. The conservative portfolios fell slightly less than the speculative ones but "
    "about as much as the index. Low stock-level volatility measured in pesos offers little protection "
    "when the risk being realized is the currency itself."))

story.append(KeepTogether([Image(str(TMP / "fig_ars.png"), width=16 * cm, height=8.7 * cm),
                           P("Figure 1: Cumulative return in nominal ARS (log scale). Solid lines include "
                             "NPY in the ranking, dashed lines do not.", note)]))
story.append(KeepTogether([Image(str(TMP / "fig_usd.png"), width=16 * cm, height=8.7 * cm),
                           P("Figure 2: Cumulative return in USD at the implied CCL rate (log scale). "
                             "Before September 2020 the rate is ADR-implied.", note)]))

story.append(P(
    "Table 2 measures risk-adjusted performance against the Merval with a single-factor CAPM regression "
    "and reports the conservative-minus-speculative spread, the paper's long-short test of the formula. "
    "The conservative portfolios have betas of 0.73 to 0.82, consistent with the low-risk tilt. The "
    "two-factor version earns an alpha of 11.6 percent per year in pesos (t = 1.90) and 4.0 percent in "
    "dollars (t = 0.74), positive but not statistically significant at conventional levels given the "
    "noise in a portfolio of eight or nine stocks. The spread is where the results are clearest: without "
    f"NPY, conservative beats speculative by about 19 percent per year in both currencies (t = 2.47 in "
    f"pesos, {cs_t:.2f} in dollars). With NPY the average spread is close to zero. The full formula's "
    "conservative portfolio still compounds faster than its speculative counterpart, because it has lower "
    "volatility, but the arithmetic return advantage disappears. This is the first sign that NPY works "
    "against the other two factors in this market."))

story.append(KeepTogether([
    P("Table 2: CAPM regressions on the S&amp;P Merval and long-short spreads", caption),
    table(["Portfolio", "α ARS", "t", "β", "α USD", "t", "β"], capm_rows(),
          [5.4 * cm, 1.8 * cm, 1.3 * cm, 1.2 * cm, 1.8 * cm, 1.3 * cm, 1.2 * cm]),
    P("Monthly regressions of portfolio returns on Merval returns (no risk-free rate), alphas annualized "
      "by compounding. For the conservative-minus-speculative rows, α is the annualized mean monthly "
      "spread and t its t-statistic.", note)]))

# 4. Through time
story.append(P("4. Results through time", h1))
story.append(P(
    "Van Vliet and Blitz stress that the conservative formula delivered positive returns in every decade. "
    "Our sample is too short for that test, so Table 3 splits it into four regimes that broadly follow "
    "Argentine policy: the first cepo period (2011–2015), the liberalization and subsequent crisis "
    "(2016–2019), renewed controls and high inflation (2020–2023), and the post-2023 stabilization."))
story.append(KeepTogether([
    P("Table 3: Annualized USD returns by sub-period", caption),
    table(["Period", "Cons. ex-NPY", "Cons. NPY", "Spec. ex-NPY", "Spec. NPY", "Merval"], period_rows(),
          [4.2 * cm, 2.3 * cm, 2.1 * cm, 2.3 * cm, 2.1 * cm, 2 * cm]),
    P("Compounded annual growth rates in USD at the implied CCL. † The bond-implied CCL exists only from "
      "September 2020; this row avoids the ADR-implied rate entirely.", note)]))
story.append(P(
    "The two-factor portfolio beats the Merval in three of the four regimes, with its largest edge in "
    "2020–2023 (21.1 versus 11.8 percent per year). It lags in 2024–2026, when the post-election rally "
    "favoured the index, whose largest weights are high-volatility bank and energy stocks. The full formula trails the "
    "two-factor version in every sub-period, and in 2011–2015 it loses money while the "
    "two-factor version gains. One robustness point matters here: over October 2020 to September 2026, "
    "where the more reliable bond-implied rate is available, the two-factor portfolio slightly trails the "
    "Merval in dollars (34.0 versus 34.8 percent per year). Its full-sample dollar advantage comes from "
    "the earlier years, which rest on the ADR-implied rate. Figure 3 shows calendar-year dollar returns."))
story.append(KeepTogether([Image(str(TMP / "fig_years.png"), width=16 * cm, height=6.8 * cm),
                           P("Figure 3: Calendar-year returns in USD. * 2011 covers April–December and 2026 "
                             "covers January–September.", note)]))

# 5. NPY
story.append(P("5. Why net payout yield fails in Argentina", h1))
story.append(P(
    "In the original study NPY is a robust source of return, linked to the value and shareholder-yield "
    "premiums. To see why it hurts here, we sort stocks each quarter on trailing dividend yield alone. "
    "Stocks that paid no dividend returned 14.6 percent per quarter on average in nominal pesos, against "
    "12.8 percent for the highest-yielding payers, and the high payers outperformed the non-payers in "
    "only 46 percent of quarters. On its own, NPY carries no premium in this market."))
story.append(P(
    "The shortfall is concentrated in two periods, 2011–2015 and 2020–2023. Both were years of capital "
    "controls and high inflation in which the BCRA restricted dividend payments, particularly for "
    "companies needing access to the official exchange market to remit them. In those conditions, a "
    "trailing dividend yield is a poor signal. It partly reflects regulatory permission rather than "
    "corporate policy, and it is measured on a stale price that inflation quickly erodes. A plausible further channel, "
    "not tested here, is that firms able to pay belonged mostly to regulated, low-growth sectors that "
    "lagged firms with dollar revenues or real assets during devaluations. When controls eased, in 2016–2019 and "
    "again from 2024, high payers led, consistent with the factor having value only in a functioning "
    "capital market."))
story.append(P(
    "Two data limitations also weaken the signal relative to the paper. The buyback leg is missing, and "
    "buybacks may have substituted for dividends at some firms while dividends were restricted. "
    "And the Yahoo dividend data needed substantial cleaning. Both point to our NPY being a noisier "
    "measure than Van Vliet and Blitz's. Still, the size and consistency of the gap, over 10 percentage "
    "points per year in pesos, make it unlikely that better data alone would reverse the sign."))

# 6. Limitations
story.append(P("6. Limitations", h1))
story.append(P(
    "These results should be read as a suggestive first look rather than a definitive replication. "
    "(i) The universe is 64 stocks, many of them illiquid Panel General small-caps, against 1,000 US "
    "large-caps in the paper, and the conservative portfolio holds only 8–10 names, so idiosyncratic "
    "risk is large. (ii) The universe is a static list of currently listed stocks, which creates "
    "survivorship bias. (iii) Trading costs and liquidity constraints are ignored, which matters more "
    "for thinly traded small-caps than for the paper's universe. (iv) NPY is dividend yield only. (v) "
    "Dollar returns before September 2020 depend on an ADR-implied exchange rate, and the dollar "
    "outperformance of the two-factor portfolio does not hold in the bond-implied subsample. (vi) "
    "Sharpe ratios and alphas use a zero risk-free rate, which overstates peso Sharpe ratios given "
    "Argentine interest rates."))

# 7. Conclusion
story.append(P("7. Conclusion", h1))
story.append(P(
    "We take the Conservative Formula of Van Vliet and Blitz (2018) to the Argentine stock market, one "
    "of the most volatile environments available. The low-risk anomaly replicates: low-volatility stocks "
    "with strong momentum beat high-volatility stocks with weak momentum by about 19 percent per year, "
    "with lower volatility and smaller drawdowns, and in nominal and dollar terms they beat the S&amp;P "
    "Merval over the full sample. The payout leg of the formula does not replicate. Under capital "
    "controls and central-bank restrictions on dividends, dividend yield carried no premium, and adding "
    "it to the formula cost 7 to 10 percentage points per year. Finally, the 2018–2020 crisis shows a "
    "limit of the low-risk approach in a dollarized emerging market. Stock-level volatility measured in "
    "local currency does not capture currency risk, and in dollars the conservative portfolios fell as "
    "far as the index. For Argentine investors, a two-factor version of the formula seems the more "
    "promising starting point, with the caveat that the sample is small and the evidence statistically "
    "modest."))

story.append(P("References", h1))
for ref in [
    "Fama, E.F., and French, K.R. (2015). A five-factor asset pricing model. <i>Journal of Financial "
    "Economics</i>, 116(1), 1–22.",
    "Harvey, C.R., Liu, Y., and Zhu, H. (2016). … and the cross-section of expected returns. <i>Review of "
    "Financial Studies</i>, 29(1), 5–68.",
    "Hou, K., Xue, C., and Zhang, L. (2017). Replicating anomalies. NBER Working Paper No. 23394.",
    "Van Vliet, P., and Blitz, D. (2018). The Conservative Formula: Quantitative investing made easy. "
    "<i>Journal of Portfolio Management</i>, 44(7), 24–38. SSRN: 3145152.",
    "Van Vliet, P., and de Koning, J. (2017). <i>High Returns from Low Risk: A Remarkable Stock Market "
    "Paradox</i>. Wiley.",
]:
    story.append(P(ref, ParagraphStyle("ref", parent=body, leftIndent=0.6 * cm, firstLineIndent=-0.6 * cm)))


def on_page(canvas, doc):
    if doc.page == 1:
        return
    canvas.saveState()
    canvas.setFont("Times-Roman", 9)
    canvas.drawCentredString(A4[0] / 2, 1.2 * cm, str(doc.page))
    canvas.restoreState()


doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=2.5 * cm, rightMargin=2.5 * cm,
                        topMargin=2.3 * cm, bottomMargin=2.2 * cm,
                        title="The Conservative Formula in Argentina", author=AUTHOR)
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print(OUT)
