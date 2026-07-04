# Backtest Summary — VIX > 40 "Buy the Fear" (TQQQ)

> ## 🚦 Final verdict (IMPROVEMENT_PLAN complete, Steps 1–7)
> **Cautiously tradable as a 30% satellite — not shelved, and not "full-size per the backtest."** The edge is real: the same signal survived out-of-sample on the S&P 1970–2025 (32 trades, 65–74% pre-2010 win rate) and robustness testing (144/144 parameter configs profitable; 98% of bootstrap paths positive). But the headline 43–46% CAGR and 100%/10 win rate are **not** the number to trade on.
> **Deploy as:** 3× strategy sized at **30% of assets** · 70% **diversified core with bond/cash ballast** · **annual rebalance** · **MA50** trend exit · **−40% single-day circuit-breaker**.
> **Expect:** ~30% strategy-level CAGR (grid median, not 45.7%) → **~20–25% blended CAGR** at **−25% to −35% normal drawdown**. Worst case (2000–08 repeat, all-equity core) blends to **−70%** — hence the ballast and the 30% cap.
> **Before real money:** pre-commit to that worst-case drawdown, and paper/small-size one full cycle first. Full reasoning in the step sections below. Reports: [`report_en.html`](report_en.html) (English) · [`report.html`](report.html) (中文), §8.

## ⭐ The Adopted Strategy (final spec)

The best/adopted configuration, distilled from all 7 improvement-plan steps:

| Component | Rule |
|---|---|
| **Signal** | VIX close > 40 **OR** S&P 500 weekly RSI(14) < 35 *(RSI uses a simple MA of gains/losses, not Wilder)* |
| **Entry** | Buy the close **9 trading days** after the signal (the delay repeatedly buys lower) |
| **Exit** | Hold **≥ 1 year**, then sell on the first S&P close below its **MA50** *(the Step-2 upgrade from MA100)* |
| **Instrument** | TQQQ (3× Nasdaq-100), full capital within the sleeve |
| **Catastrophe stop** | Sell all if TQQQ drops **≥ 40% in one day** (≈ QQQ −13%) — zero-cost tail insurance |
| **Position (portfolio)** | The 3× sleeve is **30% of total assets**; other **70% = diversified core with bond/cash ballast**; **rebalance annually** |
| **One position at a time** | New signals ignored while invested |

**Backtested performance (strategy sleeve, full 3× TQQQ, MA50 exit, 2010–2026):** final equity **$4.73M**, CAGR **45.7%**, MaxDD **−58%**, Sharpe **1.01**, 10/10 wins.
**Realistic sized expectation (30% sleeve + 70% ballasted core, annual rebalance):** **~20–25% blended CAGR** at **−25% to −35%** normal drawdown; plan for **~30%** strategy-level CAGR (parameter median), not 45.7%.

**Window:** 2010-02-11 → 2026-06-26  ·  **Start capital:** $10,000  ·  **Trades:** 10 (100% win rate)

Data refreshed from Yahoo Finance (split/dividend-adjusted) through 2026-06-26. RSI(14) uses a **simple moving average** of gains/losses (not Wilder's smoothing).

## Performance vs Benchmarks

Ordered by final equity. Alpha/Beta measured against Buy & Hold TQQQ.

| Strategy | Final Equity | Return % | CAGR % | Max DD % | Sharpe | Alpha | Beta |
|---|---:|---:|---:|---:|---:|---:|---:|
| **VIX40 Strategy — MA50 exit (adopted)** | **$4,733,454** | **47,234.5** | **45.69** | **-58.23** | **1.01** | **0.14** | **0.66** |
| VIX40 Strategy — MA100 exit (baseline) | $3,623,260 | 36,132.6 | 43.33 | -61.57 | 0.97 | 0.11 | 0.69 |
| Buy & Hold TQQQ | $3,485,958 | 34,759.6 | 42.99 | -81.66 | 0.90 | -0.00 | 1.00 |

### Takeaways
- With the **SMA-based RSI** and the **adopted MA50 exit**, the strategy **beats** buy-&-hold TQQQ on every axis: higher final equity (**$4.73M vs $3.49M**), higher CAGR (45.7% vs 43.0%), much smaller max drawdown (**-58% vs -82%**), and a higher Sharpe (1.01 vs 0.90) — all at a beta of 0.66 with positive alpha. The MA100 baseline (2nd row) also beats B&H; MA50 just exits the cracked uptrend sooner. The **risk-adjusted edge is intact**.
- The less-smoothed SMA RSI is **more sensitive** than Wilder's, firing on more capitulation events.
- Every one of the 10 entries was profitable.
- **The 9-trading-day entry delay helps**: waiting ~2 weeks after the panic signal repeatedly bought lower (e.g. COVID at $5.34 vs $9.49 on the signal day).

## Out-of-Sample Validation (IMPROVEMENT_PLAN Phase 1, Step 1)

**The make-or-break test:** is the edge real, or just a curve fit to the post-2010 tech bull? We ran the **same RSI(14, weekly) < 35 entry / MA100 exit logic** on the long S&P 500 history (**1970→2025**, 32 trades) — the VIX leg is dropped because VIX data only starts in 2010, so this leans on the RSI capitulation leg alone. Traded at 1× (the index) and at a synthetic **3×** (3× daily return − 1%/yr drag). Signals/exits are computed on the 1× index. Engine is now fully parameterized in `src/backtest.py`; runner is `src/out_of_sample.py`.

| Variant | Window | Trades | Win % | CAGR % | Max DD % | Sharpe | Pre-2010 (win / CAGR) | Post-2010 (win / CAGR) |
|---|---|---:|---:|---:|---:|---:|---|---|
| baseline (TQQQ) | 2010–2026 | 10 | 100.0 | 43.33 | -61.57 | 0.97 | — | 100% / 43.3% |
| **S&P 1×** | 1970–2025 | 32 | 81.2 | 7.36 | **-47.26** | 0.58 | **73.9% / 5.56%** | 100% / 11.95% |
| **S&P 3×** | 1970–2025 | 32 | 75.0 | 15.80 | **-92.38** | 0.56 | **65.2% / 9.78%** | 100% / 32.09% |
| *B&H S&P 1× (ref)* | 1970–2025 | — | — | 7.95 | -56.78 | — | — | — |

### 🚦 Decision gate: **PASS (with a hard leverage caveat)**
- **The edge is real out-of-sample.** In the true out-of-sample window (**pre-2010**, which the strategy was never tuned on) the signal is profitable with a **sane 74% (1×) / 65% (3×) win rate** — squarely in the plan's 60–75% target band — and positive CAGR. It is **not** solely a post-2010 artifact.
- **But 1× timing barely matches buy & hold on return** (7.36% vs 7.95% CAGR): the strategy sits in cash much of the time, so its value at 1× is *lower drawdown* (−47% vs −57%), not higher return. The return edge only compounds meaningfully under leverage.
- **3× all-in is not survivable as-is:** −92% max drawdown. The signal is directionally right at 3×, but naive full-capital leverage courts ruin. **This is exactly why Steps 2 (exit) and 3 (sizing) are mandatory before trading any leverage.**
- **Conclusion:** the strategy is a *real, tradable signal* — proceed to Step 2. Do **not** deploy 3× all-in until the exit/sizing work caps that −92% tail.

Artifacts: `results/variants.csv`, `results/oos_spx_{1x,3x}_trades.csv`, `plots/oos_equity.png`, `plots/oos_trade_histogram.png`.

## Re-engineering the Exit (IMPROVEMENT_PLAN Phase 1, Step 2)

**Goal:** cut the −46% intra-trade drawdown (worst dip below entry) without giving up most of the upside. Each exit rule tested as a separate variant on the tradable strategy (real TQQQ, 2010–2026). Runner: `src/exit_variants.py`; detail in `results/exit_variants.csv`. "DD-from-buy" = worst close-to-entry dip while holding (same definition as the per-trade charts).

| Exit variant | Trades | Win % | CAGR % | Port MaxDD % | Sharpe | Avg DD-from-buy % | Worst DD-from-buy % |
|---|--:|--:|--:|--:|--:|--:|--:|
| baseline (MA100) | 10 | 100 | 43.33 | −61.6 | 0.97 | −20.0 | −46.4 |
| **2b MA50** | 10 | 100 | **45.69** | **−58.2** | **1.01** | −20.0 | −46.4 |
| 2b MA200 | 9 | 100 | 38.18 | −65.7 | 0.88 | −21.6 | −46.4 |
| 2a trail 25% | 17 | 58.8 | 22.95 | −54.2 | 0.74 | −11.0 | −34.0 |
| 2a trail 30% | 15 | 66.7 | 24.39 | −60.6 | 0.74 | −9.9 | −34.0 |
| 2a trail 35% | 15 | 66.7 | 35.54 | −60.6 | 0.87 | −10.8 | −37.6 |
| 2c scale-out (⅓@+100/+200, trail rest) | 15 | 66.7 | 26.61 | **−50.7** | 0.84 | −10.3 | −34.0 |
| hybrid MA100 + 30% trail | 15 | 66.7 | 26.08 | −58.3 | 0.79 | −10.3 | −34.0 |

### 🚦 Decision gate: strict goal **not achievable** → adopt MA50, defer DD-control to sizing
- **No exit rule cuts intra-trade DD cheaply.** Every trailing stop that trims the worst dip (−46%→−34/−38%) also **sells into the panic and misses the recovery** — CAGR collapses 43%→23–36% and the 100% win rate falls to 59–67%. *The dip below entry is where the edge is*: you buy fear and must endure more fear to catch the rebound. Trailing stops fail the strict "CAGR within −15%" bar.
- **Trailing stops also fail out-of-sample:** re-validated on S&P 1970–2025, the 35% trail gives only **4 trades on the 1× index** (the index rarely falls 35% from peak) — statistically degenerate, well under the ≥30 bar.
- **Adopt MA50 as the working exit** — a *free* upgrade: same 10 trades and identical DD-from-buy profile, but higher CAGR (**45.7% vs 43.3%**), smaller portfolio MaxDD (**−58% vs −62%**), higher Sharpe (**1.01 vs 0.97**). It passes Step 1 cleanly (S&P 1970–2025: 32 trades, 78% win, CAGR 7.30%, no regime break). Logged as `step2_2b_ma50_tqqq` in `variants.csv`. *(The module default stays MA100 to keep the locked baseline reproducible; downstream steps use `ma_period=50`.)*
  > **The rule is otherwise unchanged — it only ==swaps MA100 → MA50 (faster trend exit after the same 1-year lock)==.** The 365-day minimum hold and the "S&P closes below its MA" trigger both stay; the exit just references the 50-day average instead of the 100-day, so it fires sooner once the uptrend cracks.
- **Hand-off to Step 3:** MA50 improves the *portfolio* drawdown but **cannot reduce the intra-trade dip** — that is structural. The right lever for a tolerable −46% dip is **position sizing** (hold less than 100% of the leveraged ETF), not stopping out of it. That is exactly Step 3.

## Size for Survival (IMPROVEMENT_PLAN Phase 1, Step 3)

**Goal:** survive the worst case and remove the all-in ruin risk. Same MA50 strategy, varying only sizing: scale-in tranches (3a), fractional capital (3b), and 1×/2×/3× leverage (3c). Runner: `src/sizing.py`. **The key methodological point:** the 2010–2026 window is a near-uninterrupted bull, so *in-sample metrics reward maximum leverage* — the exact overfit trap Step 1 flagged. Sizing must be judged on the **long history (S&P 1970–2025)**, where the crashes live.

**In-sample 2010–2026 (the trap):** Sharpe/Calmar *rise* with leverage — 3× QQQ Calmar 0.86 > 2× 0.82 > 1× 0.76; fractional/scale-in only lower return. This window never saw a 3×-killing crash, so it can't inform survival.

**Long survival test (S&P 1970–2025), by effective exposure:**

| Sizing | Exposure | CAGR % | Port MaxDD % | Worst-case (pre-2010) DD % | Sharpe | Calmar |
|---|---|--:|--:|--:|--:|--:|
| 1× | 1.0× | 7.30 | −47.3 | −47.3 | 0.579 | 0.154 |
| **3× at 50% cap** | **1.5×** | 10.54 | **−57.1** | **−57.1** | **0.597** | **0.185** |
| 2× | 2.0× | 12.24 | −78.6 | −78.6 | 0.556 | 0.156 |
| 3× at 75% cap | 2.25× | 13.75 | −78.2 | −78.2 | 0.583 | 0.176 |
| 3× full (reference) | 3.0× | 15.17 | **−94.0** ☠ | **−88.3** ☠ | 0.548 | 0.161 |

### 🚦 Decision gate: **adopt ≈1.5× effective exposure (3× ETF at 50% capital / cash buffer)**
- **Full 3× is ruinous.** Over the long history it draws down **−94%** (−88% inside a single trade) — effectively wiped out. Its gaudy 45.7% in-sample CAGR is a bull-market artifact; **reject full-3× for real capital.**
- **≈1.5× effective is the survival-optimal choice** — worst-case portfolio DD **−57%** (survivable, ≈ plain S&P buy & hold's −57%) with the **best long-run Calmar (0.185) and Sharpe (0.597)** — *both beat full-3×* (0.161 / 0.548). It satisfies the gate: a clearly better risk/return trade-off than full-capital 3×.
- **The mechanism:** deploying only half the capital in the 3× ETF means the *instrument* can still crater −88% in a crash, but the *portfolio* only feels ~−57% because the other half sits in cash (a dry-powder buffer). You cap ruin without stopping out of the recovery — the lever Step 2 said to pull here.
- **2× (−78% DD) is the aggressive bound;** 1.5× (−57%) is the sane default. Implement as **TQQQ at 50% capital**, or **a 2× ETF (QLD) at ~75%** — both ≈1.5× net.
- **Scale-in (3a) not adopted:** buying a tranche on the signal day forgoes the 9-day-delay discount, so it slightly *lowers* CAGR (45.7%→44.0% in-sample) with no risk-adjusted gain; it only smooths entry-timing luck. Keep the single delayed lump.
- Logged as `step3_3x_frac_50_longOOS` in `variants.csv`. Chart: `plots/sizing_risk_return.png`.

**Phase 1 (Tier 1) complete** — the signal is real (Step 1), the exit is tuned (MA50, Step 2). On sizing (Step 3), the in-model finding was ≈1.5×, but **Adam sizes at the portfolio level** (only 30–40% of total assets go into this 3× sleeve), so within the backtest we **keep full 3× TQQQ**. A 3× −90% crash then costs ~30–36% of net worth — ruin capped at the portfolio layer, not inside the strategy.

## Catastrophe Rule (IMPROVEMENT_PLAN Phase 2, Step 4)

**Goal:** a hard de-risk trigger for an extreme single-day move — exit the 3× position at the close of any held day whose 3× daily return ≤ threshold (−30% ≈ a −10% day in the 1× underlying), optional cooldown after. Runner: `src/catastrophe.py`. Success bar: *negligible drag in normal markets AND meaningful protection in the worst days.*

**In-sample (full 3× TQQQ, MA50, 2010–2026) — the cost:**

| Threshold (3× / ~underlying) | Cat exits | CAGR % | MaxDD % | Sharpe | Calmar |
|---|--:|--:|--:|--:|--:|
| baseline (off) | 0 | 45.69 | −58.23 | 1.009 | 0.785 |
| −25% / −8.3% | 1 | 43.27 | −58.23 | 0.985 | 0.743 |
| −30% / −10% | 1 | 43.27 | −58.23 | 0.985 | 0.743 |
| −35% / −11.7% | 0 | 45.69 | −58.23 | 1.009 | 0.785 |
| −40% / −13.3% | 0 | 45.69 | −58.23 | 1.009 | 0.785 |
| −30% + 60-day cooldown | 1 | 39.83 | −58.23 | 0.946 | 0.684 |

**Long history (synthetic 3× S&P, 1970–2025) — the protection:** at −30% the rule fires **zero times**; MaxDD stays −94.0%, worst single portfolio day −27.1%, unchanged.

### 🚦 Decision gate: strict criterion **not met** — adopt only a loose −40% circuit-breaker as untriggered tail insurance
- **A single-day rule is the wrong tool for this strategy's real risk.** The drawdowns that threaten it are **multi-week grinds** (2000–02, 2008 → −94%), not one-day gaps — so the rule leaves MaxDD *completely unchanged* in both windows.
- **Tight thresholds (−25/−30%) tax the V-recovery:** the only in-sample trigger was COVID-2020, where exiting near the bottom and re-buying higher cost ~2.4pp CAGR and lowered Sharpe/Calmar — for **no** drawdown benefit. Cooldowns make it strictly worse (−6pp CAGR at 60 days).
- **On 55 years it never fired** — the worst single day *while holding* was −34.5% (COVID TQQQ); the biggest index crashes (1987 −20%) happened while the strategy was flat.
- **What to actually do:** set a **loose −40% (≈ −13% underlying) circuit-breaker**. It never triggered in 55 years → **literally zero drag**, yet forces an exit before a genuinely *fund-ending* single-day gap — a >−33% underlying move takes a 3× ETF toward −100% (the "tail a backtest can't show"). Adopt it as cheap insurance, **not** as a return feature. Real de-risking of this strategy's drawdowns stays with the trend exit (Step 2) and portfolio-level sizing (Step 3).

#### Why −40%, in detail
- **The lethal mechanism it insures against.** A 3× daily-reset ETF rebuilds 3× leverage every morning, which makes a *single* day mathematically fatal: `3 × −33.3% = −100%`. If QQQ ever falls ~33% in one session, TQQQ goes to ~**zero** — a *permanent* wipeout with no recovery to wait for (the fund would likely be liquidated). That is categorically different from the −60%…−94% *drawdowns* elsewhere here, which recover.
- **Why the threshold is −40% on the 3× (≈ −13.3% on QQQ).** It must sit in the gap between "worst normal panic" and "fund-threatening":
  - Worst single day the strategy ever *held* = **−34.5%** (COVID, 2020-03-16).
  - Tight −25/−30% thresholds sit *inside* normal-panic range → they fired on COVID, sold near the bottom, cost ~2.4pp CAGR for zero DD benefit.
  - −35% is only 0.5% below the worst historical day — too close; a marginally worse panic trips it.
  - **−40%** clears −34.5% with a buffer, so it fires only on a move **worse than anything in 55 years** — a genuinely catastrophic day.
- **"Zero historical drag."** No held day in 1970–2025 (or real TQQQ 2010–2026) ever reached −40%, so the rule changes *none* of the historical trades — CAGR, Sharpe and MaxDD are identical to baseline. You pay nothing for it.
- **"The tail a backtest can't show."** The sample never produced a −33% underlying day, so the backtest gives false comfort — but it is *possible* (1987 was −20.5%; an extreme gap-down or multi-halt day could approach the lethal zone). Insurance covers the disaster history hasn't dealt yet.
- **"Insurance, not a return feature."** It exists solely to cap the one outcome that *permanently* ends the strategy, not to raise returns (it is return-neutral). Honest caveat: a real wipeout often gaps at the *open* or locks limit-down, so a close-based exit is imperfect — it helps most in a slower multi-halt grind (sell into the −40% close), less in an instantaneous gap.

#### The actionable rule (real trading)
> **Sell all TQQQ when TQQQ itself drops ~40% in a day (≈ QQQ −13%).** That's the actionable line — while there's still something to protect and before a possible next-day continuation toward wipeout.

- **Trigger on TQQQ −40%, not QQQ −40%.** The threshold is on the 3× fund (≈ a −13% day in QQQ). If you waited for *QQQ* to fall 40%, TQQQ would already be gone (`3 × −40% = −120%` → −100%) — nothing left to sell.
- **Hold through the −30%s; only bail past −40%.** The edge is enduring severe panic: TQQQ fell −34.5% in a day at the COVID bottom (2020-03-16) and holding caught a +456% recovery. −40% is drawn just past that worst-ever survived panic, so it fires only on something worse than anything in 55 years.
- **Practical limits.** US market-wide circuit breakers halt all trading for the day at S&P −20%, so a lethal −33% QQQ *close* is largely prevented intraday — the realistic catastrophe is an overnight/weekend gap-down (1987's −20.5% ≈ −61% for a 3× fund). A close-based sell can be outrun by an open gap; it protects best in a slower multi-halt decline.

## Robustness & Sensitivity (IMPROVEMENT_PLAN Phase 2, Step 5)

Runner: `src/sensitivity.py`. Tests whether the edge is a plateau (robust) or a lucky knife-edge.

**5a — Parameter sweep (144 configs: VIX {35,40,45} × RSI {30,35,40} × hold {180,270,365,540 d} × delay {0,5,9,15 d}) on the full-3× MA50 strategy.**

| | CAGR % across the 144 configs |
|---|---|
| min / median / max | **20.1 / 30.0 / 51.1** |
| share profitable | **100%** (every config CAGR > 20%) |
| adopted (VIX40/RSI35/hold365/delay9) | 45.7 — the **95th percentile** of the grid |

- **It's a plateau, not a knife-edge** — *every* one of 144 parameter combinations is profitable (CAGR 20–51%); the heatmaps are smooth. VIX threshold barely matters (the RSI leg dominates the signal); entry delay and hold have mild, gradual effects. The edge does not hinge on a fragile parameter choice. ✅
- **Honesty caveat:** the adopted config sits at the **95th percentile** of the grid (45.7% vs 30% median), on a visible `hold=365` ridge. It was favorably placed, so **haircut return expectations toward the grid median (~30% CAGR)**, not the headline 45.7%. Chart: `plots/sensitivity_heatmaps.png`.

**5b — Trade-sequence bootstrap (10,000 resamples, each trade carrying its own intra-trade dip):**

<details><summary><b>What "bootstrap the trade sequence" means (click to expand)</b></summary>

It answers: *was the 45.7% CAGR a repeatable edge, or luck in the order/selection of trades I happened to get?* A backtest is **one** path through history (10 trades, one order, dominated by the +393% COVID trade). The bootstrap manufactures thousands of alternate histories out of the real trades to see the *distribution* of outcomes, not the single one that happened.

- **Resample with replacement.** Treat the realized trades as a bag of chips, each stamped with one trade's result (`+93, +91, +25, +130, +70, +393, +31, +130, +25, +42`). To build one alternate history, draw N chips at random **putting each back after reading it** — so some trades appear twice, others not at all. One draw might include the +393% monster twice (great outcome); another excludes it (mediocre). "With replacement" is what creates the variety and probes *how much the result hinges on that one COVID trade*.
- **Recipe (`bootstrap()` in `src/sensitivity.py`):** for each of 10,000 iterations — (1) draw N trades at random with replacement (N = original count); (2) compound them into an equity path, applying each drawn trade's own worst intra-trade dip (`MaxDD_From_Buy`) so drawdown is realistic; (3) record that path's CAGR and MaxDD. The 5th–95th spread is the answer: narrow band around a positive median = robust; only-positive-by-one-lucky-draw = fragile.
- **Caveat 1 — it can only draw outcomes you observed.** The in-sample set is 10 winners, 0 losers → every resample wins (P>0 = 100%), *overstating* confidence. That's why the honest run uses the 32-trade long-OOS sample (which contains losers).
- **Caveat 2 — it assumes trades are independent (iid);** reshuffling ignores regime clustering/autocorrelation, so treat it as a sequencing/selection-risk gauge, not gospel.

*Analogy: instead of judging a card player from the one hand they were dealt, reshuffle their actual cards and re-deal thousands of times to see the range of hands that edge could produce.*
</details>

| Sample | Median CAGR (5th–95th) | Median MaxDD (5th–95th) | P(CAGR>0) | P(DD worse than −80%) |
|---|---|---|--:|--:|
| in-sample 10 trades | 45.8% (30 – 68) | −46% (−46 – −38) | 100% | 0% |
| **long-OOS 32 trades (3×, honest)** | **15.6% (3.5 – 27)** | **−90% (−99 – −68)** | **98%** | **76%** |

- **The return edge is robust** — on the honest 32-trade sample (which contains losers) **98% of resampled paths are profitable**, median CAGR 15.6%. Not a lucky single path.
- **But at full 3× the drawdown is reliably catastrophic** — median bootstrap MaxDD **−90%**, and **76% of paths breach −80%**. Ruin-level drawdown is the *norm* at full leverage, not a tail. This re-confirms Steps 1/3 and is exactly why the sleeve is sized at **30–40% of assets** (a −90% strategy DD → ~−30–36% of net worth — survivable).
- **The in-sample bootstrap is over-optimistic:** all 10 in-sample trades are winners, so every resample wins (P>0 = 100%) and the MaxDD only reflects the worst *intra-trade* dip (−46%). The 32-trade OOS bootstrap is the trustworthy one. Chart: `plots/sensitivity_bootstrap.png`.

### 🚦 Decision gate: **PASS** — robust plateau, positive bootstrap median
The edge survives parameter perturbation (100% of 144 configs profitable) and trade resampling (98% of paths positive) — it is **not overfit**. Two honest adjustments carry forward: (1) expect ~30% CAGR (grid median), not 45.7%; (2) full-3× drawdown is reliably −80/−90%, so the 30–40% portfolio-level sizing is **mandatory, not optional**. Next: Step 6 (portfolio framing) → Phase 3 write-up.

## Portfolio Framing (IMPROVEMENT_PLAN Phase 2, Step 6)

Sleeve size is already fixed (**30% of assets** in the 3× strategy), so we skip the size sweep and compute the one thing that remained: the **blended drawdown of 30% strategy + 70% core**. Runner: `src/portfolio.py`. The naive "30% × −90% ≈ −27%" is wrong two ways: (1) the core and the 3× sleeve **crash together** (2000–02, 2008), and (2) **rebalancing policy** matters — set-and-forget lets the sleeve balloon to dominate (−84% long-run DD), daily-rebal feeds the crash; **annual rebalancing** is the realistic middle. S&P core is price-only (dividends omitted → core return ~2%/yr conservative).

**Blended 30/70, annual rebalance:**

| Window | Core (the other 70%) | Blended CAGR % | Blended MaxDD % | vs core-alone DD |
|---|---|--:|--:|--:|
| 2010–2026 | 100% S&P | 25.1 | −34.5 | (S&P −33.9) |
| 2010–2026 | 60/40 | 23.2 | −26.4 | (60/40 −21.3) |
| 2010–2026 | 100% cash @4% | 20.0 | **−22.3** | (cash 0) |
| 1970–2025 | 100% S&P | 11.4 | **−70.0** | (S&P −56.8) |
| 1970–2025 | 60/40 | 10.9 | −54.1 | (60/40 −36.7) |
| 1970–2025 | 100% cash @4% | 9.6 | **−33.9** | (cash 0) |

### 🚦 Decision gate: livable **if the core carries non-equity ballast** — hold bonds/cash in the 70%, rebalance annually
- **In a normal regime the sleeve is nearly "free" drawdown:** over 2010–2026, 30% strategy + 70% S&P draws down **−34.5%**, barely worse than owning the S&P alone (−33.9%), yet **doubles** the return (25.1% vs 12.4% CAGR). At 30% sizing the leveraged sleeve adds a lot of return and little to a drawdown the equity core already has.
- **The tail risk is a correlated crash.** In a 2000–02 + 2008 repeat, an **all-equity** 70% core blends to **−70%** (both halves crash at once) — *not* livable. A **60/40** core caps it at −54%; a **cash/bond buffer** caps it at **−34%**. So the answer to "can I live with it?" is **yes, provided the other 70% isn't all stocks.**
- **Standout result:** 30% strategy + 70% **cash** beats **100% S&P on *both* axes** — higher return (9.6% vs 8.0% long; 20.0% vs 12.4% modern) **and** shallower drawdown (−34% vs −57% long; −22% vs −34% modern). A small leveraged sleeve on a safe base dominates an all-equity portfolio.
- **Operational rules:** (1) **rebalance annually** — set-and-forget lets the 3× sleeve balloon to −84% DD over decades; daily-rebal needlessly feeds crashes; annual is the sweet spot. (2) **Keep ballast** (bonds/T-bills) in the core so a correlated bear stays near −35%, not −70%. (3) Trim the sleeve back toward 30% when it runs (that *is* the annual rebalance). Chart: `plots/portfolio_blend.png`.

**Phase 2 (Tier 2) complete.** Remaining: Phase 3 — final write-up & verdict.

## Trade Log (all 10 trades)

Signal Date = day the condition fired (on close). Entry Date = the close **9 trading days later**, where the position is actually bought. Trigger shows the condition and its value on the signal day.

### VIX40 Strategy — MA50 exit (adopted)

The working strategy: same entries, but exits on the first S&P close < **MA50** after the 1-year lock. It exits cracked uptrends sooner than MA100 — note trade 6 (COVID) is banked 2021-06-18 (+393%) instead of riding to 2021-09-30, and trades 4/5/8 exit earlier at different prices. Final equity **$4,733,454** (CAGR 45.69%, MaxDD −58.23%).

| # | Signal Date | Entry Date | Trigger | Entry $ | Exit Date | Exit $ | Return % | Hold Days | Capital After |
|---|---|---|---|---:|---|---:|---:|---:|---:|
| 1 | 2010-05-07 | 2010-05-20 | VIX 41.0 > 40 | 0.21 | 2011-05-23 | 0.41 | +93.0 | 368 | $19,303 |
| 2 | 2011-08-05 | 2011-08-18 | RSI 28.0 < 35 | 0.28 | 2012-10-19 | 0.53 | +90.7 | 428 | $36,818 |
| 3 | 2015-08-21 | 2015-09-03 | RSI 29.4 < 35 | 1.82 | 2016-09-09 | 2.27 | +24.7 | 372 | $45,924 |
| 4 | 2016-11-04 | 2016-11-17 | RSI 30.7 < 35 | 2.47 | 2018-02-05 | 5.70 | +130.4 | 445 | $105,802 |
| 5 | 2018-10-26 | 2018-11-08 | RSI 34.9 < 35 | 6.73 | 2020-02-24 | 11.42 | +69.7 | 473 | $179,573 |
| 6 | 2020-02-28 | 2020-03-12 | VIX 40.1 > 40 | 5.34 | 2021-06-18 | 26.36 | +393.3 | 463 | $885,749 |
| 7 | 2022-05-13 | 2022-05-26 | RSI 30.6 < 35 | 14.48 | 2023-08-15 | 18.96 | +31.0 | 446 | $1,159,999 |
| 8 | 2023-10-20 | 2023-11-02 | RSI 32.6 < 35 | 17.64 | 2024-12-18 | 40.51 | +129.6 | 412 | $2,662,943 |
| 9 | 2025-03-14 | 2025-03-27 | RSI 32.0 < 35 | 30.93 | 2026-03-27 | 38.78 | +25.4 | 365 | $3,338,393 |
| 10 | 2026-03-30 | 2026-04-13 | RSI 28.2 < 35 | 50.66 | *open* 2026-06-26 | 71.83 | +41.8 | 74 | $4,733,454 |

*Trade 10 is still open (held 74 days < 365-day minimum); marked-to-market at the final close.*

### VIX40 Strategy — MA100 exit (baseline)

| # | Signal Date | Entry Date | Trigger | Entry $ | Exit Date | Exit $ | Return % | Hold Days | Capital After |
|---|---|---|---|---:|---|---:|---:|---:|---:|
| 1 | 2010-05-07 | 2010-05-20 | VIX 41.0 > 40 | 0.21 | 2011-06-01 | 0.41 | +94.3 | 377 | $19,427 |
| 2 | 2011-08-05 | 2011-08-18 | RSI 28.0 < 35 | 0.28 | 2012-11-07 | 0.49 | +77.2 | 447 | $34,429 |
| 3 | 2015-08-21 | 2015-09-03 | RSI 29.4 < 35 | 1.82 | 2016-10-11 | 2.48 | +35.9 | 404 | $46,804 |
| 4 | 2016-11-04 | 2016-11-17 | RSI 30.7 < 35 | 2.47 | 2018-02-08 | 5.16 | +108.8 | 448 | $97,727 |
| 5 | 2018-10-26 | 2018-11-08 | RSI 34.9 < 35 | 6.73 | 2020-02-25 | 10.50 | +56.0 | 474 | $152,450 |
| 6 | 2020-02-28 | 2020-03-12 | VIX 40.1 > 40 | 5.34 | 2021-09-30 | 29.75 | +456.6 | 567 | $848,556 |
| 7 | 2022-05-13 | 2022-05-26 | RSI 30.6 < 35 | 14.48 | 2023-09-21 | 17.30 | +19.5 | 483 | $1,014,081 |
| 8 | 2023-10-20 | 2023-11-02 | RSI 32.6 < 35 | 17.64 | 2025-02-27 | 35.47 | +101.0 | 483 | $2,038,371 |
| 9 | 2025-03-14 | 2025-03-27 | RSI 32.0 < 35 | 30.93 | 2026-03-27 | 38.78 | +25.4 | 365 | $2,555,399 |
| 10 | 2026-03-30 | 2026-04-13 | RSI 28.2 < 35 | 50.66 | *open* 2026-06-26 | 71.83 | +41.8 | 74 | $3,623,260 |

*Trade 10 is still open at the end of the window — held 74 days (< 365-day minimum), so the exit condition cannot yet trigger; it is marked-to-market at the final close.*

### Notes on signal timing
- Most entries are **RSI-driven** under the SMA method; only the May-2010 and Mar-2020 (COVID) panics tripped the VIX>40 condition.
- The refreshed data **closed trade 9**: held exactly 365 days from the Mar-2025 entry, then S&P closed below MA100 on 2026-03-27, triggering the exit (+25.4%).
- A **new trade 10** opened on the late-Mar-2026 capitulation (SMA RSI 28.2), entering 2026-04-13 at $50.66; up +41.8% and still held at the data cutoff.
- The ≥1-year hold + "S&P below MA100" exit keeps each position through the full recovery rather than selling early, which is the main source of the large per-trade returns on the leveraged ETF.

## Synthetic pre-2010 TQQQ
TQQQ launched 2010-02-11, so history before that is back-filled from QQQ via
`src/make_synthetic_tqqq.py`: `tqqq_ret = 3 × qqq_adj_daily_ret − 2.0%/252`, using
**dividend-adjusted** QQQ returns and a 2.0%/yr drag (0.95% expense ratio + ~1%
financing/borrow proxy for the 2x levered exposure). Chained backward from the real
inception close so the series joins with no discontinuity. These assumptions match
an externally supplied synthetic series (`data/synthetic_tqqq.csv`) — daily-return
correlation 0.9996, normalized-growth ratio 0.997.
- `data/qqq_adj_data.csv` — dividend-adjusted QQQ used for return calc
- `data/tqqq_synthetic_pre2010.csv` — synthetic only, 1999-03-11 → 2010-02-10 (Volume=0 flag)
- `data/tqqq_synthetic_full.csv` — synthetic + real combined, 1999 → present
- Reality check: 3x leverage through the dot-com + 2008 crashes is a near-total
  wipeout — synthetic drew down **~−99.9%** to the Mar-2009 bottom.

## Files
- `results/tqqq_vix40_trades.csv` — full trade detail
- `results/performance_summary.csv` — metrics table
- `plots/equity_curve.png` — equity curves (log scale)
