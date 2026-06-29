# Improvement Plan — VIX>40 "Buy the Fear" Strategy

A step-by-step plan to address the weaknesses identified in the report (section 七).
Work **top to bottom**; each step has a **goal**, **actions**, **success criteria**, and a
**decision gate**. Do not move leverage/size/exit changes to real money until Tier 1
(out-of-sample validation) passes.

## Ground rules (read first)
- **One change at a time**, then re-validate. Never tune multiple knobs against the same history.
- **Out-of-sample is king.** A change is only "good" if it survives the long-history test (Step 1), not just the pretty 2010–2026 curve.
- **More rules = more overfitting.** Keep a change only if it clearly helps; otherwise discard it.
- Keep the current strategy as the **baseline** to beat. Log every variant's metrics in `summary.md`.
- Reuse existing code: `src/backtest.py` (engine), `src/download_data.py`, `src/plot_trades.py`.

---

## Phase 0 — Baseline & harness
**Step 0.1 — Lock the baseline**
- Goal: a frozen reference to compare every change against.
- Actions: record current metrics (final equity, CAGR, MaxDD, Sharpe, # trades, win rate, per-trade max DD from buy) in a new `results/variants.csv` with row label `baseline`.
- ✅ Success: `baseline` row exists; numbers match current `summary.md`.

**Step 0.2 — Make the engine parameterizable**
- Goal: run variants without copy-pasting code.
- Actions: refactor `backtest.py` so VIX threshold, RSI threshold, RSI method (SMA/Wilder), entry delay, min-hold, exit MA, instrument, and leverage are function arguments (not module constants).
- ✅ Success: calling the engine with the current defaults reproduces the `baseline` row exactly.

---

## Phase 1 — Tier 1 (highest impact). **Gate: must pass before trading anything.**

### Step 1 — Out-of-sample validation (the make-or-break test)
- **Fixes:** "10 trades, 100% win, overfit on the 2010s bull."
- **Goal:** find out if the edge is real or an artifact of the post-2010 tech bull.
- **Actions:**
  1. Run the **same entry/exit logic on the S&P 500 index** (`data/sp500_index_data.csv`, history to 1927; use 1990→2026) at **1×**.
     - Note: `vix_data.csv` only starts 2010, so for the long test rely on the **RSI<35** leg (computable from the index alone); treat VIX>40 as a bonus only where VIX exists.
  2. Repeat with a **synthetic 3×** daily-rebalanced series (approximate TQQQ: `3 × daily return − fee/decay drag ~1%/yr`) to see how leverage behaves over the full history.
  3. Optionally repeat on QQQ and SPY where available.
  4. Produce: trade list, win rate, CAGR, MaxDD, and a histogram of per-trade returns for the long sample.
- **✅ Success criteria:** ≥ 30 trades; report win rate and CAGR for 1990–2010 *separately* from 2010–2026.
- **🚦 Decision gate:**
  - **PASS** if the signal is still profitable with a sane win rate (~60–75%) and survivable drawdowns in **1990–2010** → continue to Step 2.
  - **FAIL** if it only works post-2010 or win rate collapses → the strategy is a curve fit; **stop here** and treat it as a study, not a tradable system.

### Step 2 — Re-engineer the exit
- **Fixes:** loose/late exit; the −46% to −58% intra-trade drawdowns.
- **Goal:** cut intra-trade drawdown without giving up most of the upside.
- **Actions (test each as a separate variant, compare in `variants.csv`):**
  - 2a. ATR-based or fixed **%-trailing stop** on TQQQ (e.g., trail 25/30/35% from peak).
  - 2b. **Faster trend exit** after the 1-yr lock: S&P < MA50 or MA200 instead of MA100.
  - 2c. **Partial scale-out** (e.g., sell ⅓ at +100%, ⅓ at +200%, trail the rest).
- **✅ Success:** a variant that reduces average and worst per-trade max-DD-from-buy by a meaningful margin while keeping CAGR within ~15% of baseline — **and** still passes Step 1's long-history test.
- **🚦 Gate:** keep the best exit; fold it into the working strategy.

### Step 3 — Size for survival (not all-in)
- **Fixes:** ruin risk, concentration, entry-timing luck.
- **Goal:** survive the worst case; remove the single-point entry bet.
- **Actions:**
  - 3a. **Scale in** over 2–3 tranches (e.g., days 0 / 5 / 10 after signal, or as VIX/RSI stay extreme) instead of one lump at day 9.
  - 3b. **Fractional sizing:** cap exposure to a target max drawdown (e.g., size so a −80% TQQQ move costs ≤ X% of portfolio); compare full-capital vs 50% vs vol-targeted.
  - 3c. Compare **2× (QLD)** vs **3× (TQQQ)** on risk-adjusted return.
- **✅ Success:** a sizing rule with clearly better MaxDD/return trade-off (higher Sharpe/Calmar) than full-capital 3×.
- **🚦 Gate:** adopt the best size + leverage choice.

---

## Phase 2 — Tier 2 (robustness & protection)

### Step 4 — Catastrophe rule
- **Fixes:** the tail a backtest can't show (e.g., −66% in a day).
- **Actions:** add a hard de-leverage/exit trigger on an extreme single-day move (e.g., QQQ ≤ −10% intraday/close); measure the cost to normal-case returns.
- **✅ Success:** negligible drag in normal markets; meaningful protection in the worst historical days.

### Step 5 — Robustness / sensitivity analysis
- **Fixes:** overfitting confidence.
- **Actions:**
  - 5a. Parameter heatmaps: VIX {35,40,45} × RSI {30,35,40} × hold {6,9,12,18 mo} × delay {0,5,9,15 d}. (You already have `data/threshold_cooldown_results.csv` as a start.)
  - 5b. **Bootstrap** the trade sequence (resample trades) → distribution of CAGR and MaxDD, not one path.
- **✅ Success:** result sits on a **plateau** (neighboring params give similar results), and the bootstrap median is acceptable — not a lucky knife-edge.

### Step 6 — Portfolio framing
- **Fixes:** concentration.
- **Actions:** model the strategy as a **15–25% satellite sleeve** alongside a diversified core; report blended return/drawdown.
- **✅ Success:** blended portfolio has a drawdown you can actually live with.

---

## Phase 3 — Decide & document
**Step 7 — Final write-up**
- Update `summary.md` and `report.html` with the out-of-sample results and the chosen variant.
- Write an honest verdict: trade it (and at what size), paper-trade it, or shelve it.
- **🚦 Final gate:** only consider real money if Steps 1–5 passed **and** you can pre-commit to the worst-case drawdown of the final sized strategy.

---

## Suggested order & quick reference
| # | Step | Fixes | Output |
|---|------|-------|--------|
| 0 | Baseline + parameterize engine | reproducibility | `results/variants.csv` |
| 1 | **Out-of-sample (1990→)** | small sample / overfit | long-history trade stats |
| 2 | Re-engineer exit | late exit, drawdowns | best exit variant |
| 3 | Size for survival | ruin, concentration, luck | sizing/leverage choice |
| 4 | Catastrophe rule | tail risk | de-leverage trigger |
| 5 | Sensitivity + bootstrap | overfitting | heatmaps, DD distribution |
| 6 | Satellite sleeve | concentration | blended portfolio |
| 7 | Decide & document | — | updated report + verdict |

**Start with Step 0 → Step 1.** If Step 1 fails, stop — everything else is moot.
