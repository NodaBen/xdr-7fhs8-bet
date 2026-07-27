# Daily Diamond — Composite Signal Diagnostic

**Date:** 2026-07-27 · **Repo HEAD:** `9bd9d2a` ("run 2026-07-27 09:05 EDT [grade]")
**Sample:** 50 composite-bearing games (07-23 → 07-26), one row per game.
**Cost:** zero Odds API credits. Read-only against committed artifacts.
**Status:** DIAGNOSTIC ONLY. **Nothing here authorizes a code change.** Every item
below alters `composite`, which is the λ regressor; changing it before the Item 6
gate (~2026-08-03) voids the 50 games already accrued and resets the clock.

This file exists because these numbers will otherwise be re-derived from scratch in
August. It is a reference artifact, not a work plan.

---

## 0. Why this was run

Benjamin asked, on 07-27, what could be adjusted in the model code to improve
results — explicitly as an evaluation, not as a change request. The honest answer
required separating two things that get conflated:

- **Defects provable by inspection.** Wrong on their own terms. n=50 cannot refute
  them and no outcome data is needed to justify fixing them.
- **Changes that require outcome evidence.** Cannot be evaluated at n=50. The
  pre-registered Item 6 rule exists precisely to stop these being made on a look.

Everything in §1 is the first kind. Everything in §2 is the second.

---

## 1. Defects provable by inspection

### 1.1 `sit_score` is a constant. It carries zero information and consumes 7% of nominal weight.

`model.py: sit_score()` returns `56.0 if is_home else 44.0`. Measured across all 50
games, the home-minus-away difference took **exactly one value**:

```
cat    nomW    mean      sd     min     max  distinct   share of spread
sit      7%  +12.00    0.00   +12.0   +12.0         1             0.0%
```

Consequences:

- It contributes a fixed **+0.84** to `composite_diff` on every game (12.0 × 0.07).
  It cannot rank, separate, or discriminate anything.
- It dilutes every other category by 7% for nothing.
- **At λ > 0 it would be a correctness bug, not dead weight:** it adds home-field
  advantage on top of a market prior that already prices home-field. Double
  counting by construction.

Previously filed as "sit_score 56/44 constant doing nothing." This is the
measurement behind that sentence.

### 1.2 The locked weights are not the weights.

`model.py` docstring: *"locked weights 40/25/15/10/7/3."* Measured share of
`composite_diff`'s spread (`weight × sd`, normalized), n=50 games:

| cat | nominal | **effective** | mean diff | sd of diff | min | max | distinct |
|---|---|---|---|---|---|---|---|
| sp  | 40% | **52.7%** | +11.50 | 29.85 | −57.8 | +70.7 | 50 |
| off | 25% | 24.7% | +0.53 | 22.34 | −53.4 | +37.5 | 49 |
| pen | 15% | 15.2% | +0.17 | 23.01 | −37.8 | +61.5 | 49 |
| mkt | 10% | **6.3%** | +9.81 | 14.17 | −16.4 | +49.4 | 41 |
| sit | 7%  | **0.0%** | +12.00 | 0.00 | +12.0 | +12.0 | 1 |
| mu  | 3%  | **1.2%** | +0.67 | 8.79 | −24.2 | +21.9 | 45 |

**The real allocation is 53 / 25 / 15 / 6 / 0 / 1.**

Any past discussion of this model's weights was a discussion of numbers that do not
exist in its behaviour. This is the "incompatible units" problem named in the v8.0
comment block, now quantified.

`composite_diff` itself: mean **+6.61**, sd **15.73**.

### 1.3 `mkt_score` is the market verbatim, inside a regressor whose offset is the market.

```
corr(mkt_diff,               logit(market_novig)) = +0.999
corr(composite_diff,         logit(market_novig)) = +0.713
corr(composite_diff EX-mkt,  logit(market_novig)) = +0.664
```

`mkt_score` returns `novig * 100` — it *is* the prior, re-entered as a candidate
feature. Stripping it only moves the collinearity from +0.713 to +0.664, because
sp/off/pen naturally correlate with price (good teams are priced as good teams).

**A hypothesis was tested here and it FAILED. Record it so it is not re-proposed.**
The expectation was that decontaminating the regressor would tighten λ's standard
error and buy statistical power at the August gate. It does not:

```
[1] as deployed                              LAMBDA -0.0069  SE 0.0171
[4] mkt echo removed, constant sit removed,
    centered, free intercept                 LAMBDA -0.0040  SE 0.0196
```

**SE got wider, not tighter.** The reason is structural: an offset has no estimated
coefficient, so collinearity between a regressor and a *fixed* offset cannot inflate
variance the way collinearity between two fitted terms would.

**Therefore: the mkt echo is a conceptual defect (λ partly re-scales the market
rather than adding to it), NOT a measurement-power defect.** Do not argue in August
that cleaning it would have sharpened the decision. It would not have.

### 1.4 SP is the loudest, noisiest, and least-regularized category simultaneously.

- sd of the diff is **29.85** — roughly double `off` (22.34) and `pen` (23.01).
- It holds **52.7%** of effective weight.
- It runs on the least-shrunk inputs in the system (`qual=10`, `pit30 qual=0`).

Likely mechanism, consistent with the filed `pct()` defect: percentile
normalization converts a real run-value gap into a rank against a ~30-team
population, so two starters separated by 0.01 of xFIP can land 20 percentile points
apart. That inflates spread without adding information.

**If one item in §1 is load-bearing rather than cosmetic, it is this one** — because
`pct()` is the plausible root cause of SP's inflated spread, and SP is over half the
signal. That is a hypothesis about *why* there is no measured edge, not a fix that
produces one.

---

## 2. What the outcome data hints at — and why it cannot be acted on

Each category entered alone, centered, with a free intercept, offset =
`logit(pt_novig)`, n=50 games:

```
sp    beta -0.0045  SE 0.0096   z -0.47
off   beta +0.0185  SE 0.0137   z +1.35
pen   beta -0.0190  SE 0.0129   z -1.48
mu    beta +0.0251  SE 0.0348   z +0.72
```

- **Every |z| is below 1.5.** Nothing is significant. Four looks at the same 50
  games is four chances to fool yourself, and this file is one of them.
- The suggestive pattern, offered as mechanism and not as evidence: **`sp` and `pen`
  both lean the wrong way and together hold 68% of effective weight**, while `off`
  — the only positive lean — holds 25%. That is a coherent story for why pooled λ
  sits slightly negative. It is not a finding.
- **Do not reweight on this.** It is exactly the move the locked "do not tune
  weights against outcomes" rule forbids, and every per-category correlation with
  wins remains within ~1.5σ of zero.

### 2.1 An old finding does not reproduce — stop citing it

The v8.0 comment block records *"a reproduced +0.11 intercept (~2.8 pts of
uncredited home field)"* from the v7.x era. Fitting a free intercept on the
v8.0-era sample:

```
intercept (home)  -0.1840  SE 0.3090   CI [-0.7897, +0.4218]
```

**Negative point estimate, CI enormous.** The uncredited-home-field finding does not
reproduce here. This does **not** flip the conclusion — the interval spans almost a
point and a half of logit — but the old number should stop being quoted as
established. It was measured on a retired model.

### 2.2 λ trajectory at the time of this diagnostic

```
[fit_lambda] 50 usable games (30 excluded pre-v7.7 no-composite, 0 no pt_novig)
  composite_diff: mean +6.61  sd 15.73
  LAMBDA = -0.0069  SE 0.0171  Wald CI [-0.0404, +0.0266]
  LR vs LAMBDA=0: 0.16 (bar 3.84)   bootstrap CI [-0.0400, +0.0317]
  P(LAMBDA>0) = 0.347            mkt-stripped -0.0072
  per-date:      07-23 -0.006 | 07-24 -0.039 | 07-25 +0.003 | 07-26 +0.018
  leave-one-out: without 07-24 = +0.005   <- first positive LOO fit
```

Pooled λ moved −0.0148 (n=35) → **−0.0069** (n=50); P(λ>0) 24% → **35%**.
**07-26 is the second consecutive positive per-date fit and the largest yet**, and
07-24 (−0.039) is now single-handedly carrying the negative pooled estimate.

**This is not a trigger and must not be read as one.** The 07-26 queue entry
pre-registered a note against exactly this pattern and it fired the next day. Only
the Item 6 rule moves λ: CI excluding zero on the positive side, at ~150 games,
with the full output in front of Benjamin.

---

## 3. Evaluation — what would actually help

- **Nothing in §1 would plausibly turn r ≈ 0 into an edge.** Deleting `sit`,
  re-normalizing weights, stripping the mkt echo, swapping percentiles for z-scores
  or run values — that is hygiene. It makes the model *honest*, not *predictive*.
  The standing rule that adding inputs to a model with r ≈ 0 makes it more expensive
  rather than better applies with equal force to re-weighting the same inputs.
- **The only change with a real mechanism behind it is the one already in the
  queue: F5 markets.** It is the sole option that changes the *information set*
  rather than rearranging it — SP is 40% nominal / 53% effective, and F5 isolates
  exactly that while removing the bullpen noise currently leaning negative at 15%.
- **The uncomfortable framing, stated plainly:** the most likely explanation for
  everything above is that a five-category percentile composite built from public
  season-to-date statistics does not beat a nine-book consensus, and no reweighting
  of it will. The instrument was built to establish that cheaply, on paper, with no
  money at risk. **That result is the system working, not failing.**

---

## 4. Sequencing — binding

1. **Change nothing before the Item 6 gate (~2026-08-03).** Every §1 item alters
   `composite`. Touching it mid-accrual voids the 50 banked games.
2. **After the gate, if the CI still straddles zero with a negative point
   estimate:** §1 becomes largely irrelevant. Do not clean up a signal just
   established to carry no information. Go to F5, or stop. Both are legitimate.
3. **After the gate, if λ comes off zero:** §1.1 (`sit`) and §1.3 (mkt echo) are
   promoted from hygiene to **correctness bugs in a live stake** and must ship
   before the first published pick — alongside the existing go-live blockers
   (exposure/Kelly cap, Edge Score ceiling, P-C divergence gate) and Item 7's
   model-era stamp.

---

## 5. Reproduction

All figures above come from `shadow_archive.jsonl` at HEAD `9bd9d2a`, one row per
game, joined on `(date, gamePk)`, restricted to games where both sides carry
`composite` (v7.7 onward). Offset is `logit(pt_novig)`. Fits are Newton/BFGS
logistic with the offset fixed; SEs are Wald from the inverse observed information.
`fit_lambda.py` at HEAD reproduces §2.2 exactly. Nothing in this analysis wrote to
any archive; both archives were `md5sum`-verified unchanged.

---

*All outputs are expected value, never predictions. No outcome is guaranteed.
System remains paper-only; nothing in this document supports going live.*
