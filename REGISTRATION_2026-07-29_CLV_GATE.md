# PRE-REGISTRATION — The CLV Gate (queue Item H1)

**Date:** 2026-07-29 · **Registered by:** Benjamin, explicitly, in session
**Repo HEAD at registration:** `5c54956` · **Model:** `v8.11`, `LAMBDA = 0.0`
**Status:** paper-only. Nothing in this file supports going live.

> **This is a locked pre-registration. It is not a work item.**
> Do not edit it to reflect later developments — supersede it with a new dated
> record instead. Its executable half lives in `fit_lambda.py` (`GATE`,
> `GATE_BLOCK`, `gate()`). **If this file and that code ever disagree, STOP.**
> Do not resolve the disagreement in favour of either one.

**Written before its data existed.** The first game this gate reads is
2026-07-29, snapshotted at 11:05 ET on the day of registration and graded
2026-07-30. Every figure this project has produced to date is on a retired
model and is excluded **by era**, not by preference.

---

## 1. The question

> Which market — full-game moneyline or F5 — shows that the composite
> anticipates the closing line, and does either clear the bar?

Note what changed from the suspended Item 6 gate, which asked *"is there an
edge?"* against outcomes. This asks a narrower question that a sample this
project can actually reach.

## 2. Primary endpoint — closing-line movement

For each eligible game, one row, home side:

```
y = logit(close_novig) − logit(pt_novig)        market movement, in logits
x = composite_diff                              home composite − away composite

y = alpha + beta * x
```

`beta > 0` means the market moved toward the side the composite preferred,
between our 11:05 ET snapshot and the close.

**Non-stale closers only.** A snapshot taken after first pitch is not a closing
price; `MAX_CLOSER_AGE_MIN` exists to say so, and a gate that read stale
closers would be measuring the in-play market.

### 2.1 Why not outcomes — the measurement that forced this

Measured on the pre-gate sample (n=62 games, `composite_diff` sd 16.70):

`SE(lambda_pt) ≈ 2 / (sd · √n)`

| n | SE(λ_pt) | λ needed to clear | probability edge on a 1-sd game |
|---|---|---|---|
| 150 | 0.0098 | 0.0219 | **9.1 pts** |
| 300 | 0.0069 | 0.0155 | 6.4 pts |
| 500 | 0.0054 | 0.0120 | 5.0 pts |
| 1000 | 0.0038 | 0.0085 | 3.5 pts |

A public-stats composite that genuinely beat a nine-book consensus by ~2 points
on a 1-sd game is λ ≈ 0.005. Detecting that at 80% power under the correction
registered in §5 requires **n ≈ 5,400 games — roughly 2.2 MLB seasons.**

Registering an outcome gate at n=150 would be registering a null result: its
answer is knowable before it runs. The movement endpoint's residual sd is
~38× smaller at the same n, which is what makes a reachable gate possible.

**The outcome endpoint is not discarded.** `lambda_pt` is fitted and printed on
every run as a descriptive secondary, read by no rule. It remains the only
endpoint that measures *profit*.

### 2.2 The honest limits of this endpoint — recorded before the result

1. **CLV is a proxy for edge, not edge.** Beating the close converts to money
   only if the 11:05 price is actually available, in size, at a book that will
   keep taking the action.
2. **Predicting movement is not the same as having an edge.** A model that
   merely tracks steam or public money anticipates the close and earns nothing.
   This is why §7 makes clearing authorize *staking under constraint*, not
   *validation*.
3. **The endpoint was chosen after looking at data.** See §8. This is the most
   serious caveat and it is why the sample is prospective.

## 3. Sample definition

**PRIMARY:**

- `MODEL_VERSION == 'v8.11'` **exactly** — one model era, no pooling.
- Archive-composite games. One row per game (the two sides of a game are
  complementary with anti-correlated outcomes; using both halves every SE).
- **Excluding any game with a `DEGRADED` or `BLOCKED` side.**
- Non-stale closer present.
- First eligible date **2026-07-29**.

**`BLOCKED` is new to this definition and the omission was a real hole.** The
v8.7 definition named only `DEGRADED` because it predates the severity split.
`BLOCKED` means `sp_score()` could not resolve the starter and returned a
neutral 50.0 into 44% of the composite — the model has *no opinion* on that
side, and `picks.py` already refuses to stake it. The fit had no matching
exclusion. On the 2026-07-29 board this is 4 of 32 sides, so it starts biting
on the gate's very first date.

**SECONDARIES** (+backfill, +DEGRADED, +pooled-era) are fitted and printed
every run and **read by no rule**. They exist so a disagreement with the
primary is visible, not so a better-looking number can be adopted afterward.
They are **not** additional tests and do not enter the family in §5.

### 3.1 Era homogeneity — enforced by fixture, not by trust

An era boundary is **any change that alters the value of `composite`**. Data-
client changes are not boundaries (the v8.9.1 Savant-retry precedent).

`fit_lambda.py` computes a SHA-256 digest over the AST of the composite-
determining surface of `model.py` — `CAT_WEIGHTS`, `COMPOSITE_EXCLUDE`,
`SCORE_SPREAD`, `SCORE_CLAMP`, `SP_STATS`, `SP_K`, `SP_SHRINK_K`,
`SP_TBD_SCORE`, the velocity constants, `OFF_STATS`, `OFF_WINDOWS`,
`SIT_SPREAD`, `SIT_CLAMP`, and the functions `composite_weights`, `to_score`,
`zmean`, `zindex`, `_row_z`, `sp_score`, `off_score`, `pen_scores`,
`matchup_score`, `sit_score`, `mkt_score`, `run_slate`.

Registered digest: **`7192aa6724f20b69`** at `MODEL_VERSION = v8.11`.

Verified by execution 2026-07-29 that the digest **changes** on a category
weight edit, a `SP_SHRINK_K` edit, and an in-function stat weight edit, and
**does not change** on comment or whitespace edits.

**This is a tripwire, not a proof.** A behaviour change introduced under a
*new* name would not be listed and would not be caught. It exists to make the
common failure — edit a weight, forget the version bump — loud.

### 3.2 Accrual freeze

**No composite-altering change ships between this registration and the gate.**
Breaking the freeze resets the era, voids the accrual, and falls under §6.

Known work deliberately held behind it: queue **Item J** (offense-input
reliability), and any reweighting arising from `pen` / `mu` / `sit` reliability
measurement. Those measurements may be *run* during accrual — they are free and
change no code — but nothing ships until the gate resolves.

## 4. n and the number of looks

- **n = 150 primary games.**
- **ONE LOOK.** No interim analysis. No extension.
- An extension would cost alpha and **is not registered.** Accruing past 150 and
  re-testing is optional stopping and is forbidden here in advance.

At the accrual rate measured over 2026-07-23…07-28 (≈12 primary games/date,
before the new `BLOCKED` exclusion), n=150 is expected around **2026-08-09**.
The gate fires on **n, not on the date.** The date is an estimate; it carries no
authority and must not be used to hurry or delay the look.

## 5. Test and multiplicity

- **One-sided, positive direction.** A significant *negative* beta authorizes
  nothing — fading our own model is a different strategy and needs its own
  registration.
- **Family-wise alpha = 0.05, Holm–Bonferroni step-down**, over **m = 2**
  markets: `ml_full`, `f5`.
- Holm rather than plain Bonferroni: same FWER control, uniformly more
  powerful, so plain Bonferroni is strictly dominated. FWER rather than FDR:
  one false positive here means real money on noise, which is not a rate to be
  tolerated in expectation.
- **The family is every market EVALUATED, reported or not.** A market dropped
  after the fact because its result was inconvenient is the precise leak the
  correction exists to prevent. `f5` is held in the family whether or not Item F
  instruments it in time; an untested market simply cannot reject.
- **Standard errors are date-clustered (CR1)**, inference on **t with G−1 df**.
  The shock is the day, not the game — a slate moves together on weather, news,
  or a syndicate hitting the board — so treating 15 games from one evening as 15
  independent observations understates the SE. With G ≈ 12 at the gate this is
  conservative and noisy, which is the correct direction to err.

**Recorded because it cuts against the endpoint:** applying this exact method
to the n=62 exploratory sample gives beta +0.000819, CR1 SE 0.000417, t +1.97,
df 5, one-sided p **0.0533** — **which does not clear even the un-corrected
0.05**, let alone Holm's 0.025. The naive unclustered SE that made the
exploratory look promising was 0.000396 with p ≈ 0.019. The registered method
kills the signal that motivated it. That is on record before the real data.

## 6. Blinding

**The primary statistic is not computed or printed until n = 150.**

`fit_lambda.py` runs daily on the grade job. That is continuous looking, and a
human who has watched a number climb toward a threshold cannot un-see it. The
tool prints sample health, era composition, accrual rate, and the outcome
secondaries; it refuses to print the registered statistic below n.

**Stated limitation, not solved:** the outcome secondaries still print, and they
are weakly related to the primary endpoint. Blinding here is partial. It was
chosen over full blackout because losing daily pipeline monitoring reintroduces
the λ=0 failure mode — a stale card and a fresh card look identical.

**Do not peek by re-implementing this fit elsewhere.** That is the same act.

## 7. What clearing authorizes — and what it does not

Clearing authorizes **staking, and nothing else**, and only after **both**
go-live blockers ship:

- [ ] Exposure / Kelly cap
- [ ] Edge Score ceiling

Further binding conditions:

- **Kelly fraction sized on HALF the point estimate**, because the endpoint is
  a proxy for edge rather than a measurement of it.
- **Units key to EDGE** (model probability − price-implied probability), never
  to raw win probability. A heavy favorite can be 0U; an underdog can be 3U.
- The 4U–5U rule is unchanged: ≥7% edge **and** sharp confirmation **and** FULL
  data.
- **Outcome ROI remains unproven for ~2 seasons** and no result from this gate
  changes that. Going live on this evidence is a decision to accept risk, not a
  demonstration of profitability.
- Nothing moves without Benjamin, in writing, after seeing the full output.

## 8. What a null result triggers

If no market clears at the corrected level:

- **`LAMBDA` stays 0.0.**
- **No re-test of this composite on more data.** Forbidden in advance.
- The choice narrows to two legitimate options: move to a **materially
  different information set** — not a reweighting of the same inputs — or
  **publish the null** and continue as an unvalidated card.
- Reweighting inside the existing composite and re-running is explicitly *not*
  an option this registration leaves open.

## 9. Provenance — recorded against interest

**The endpoint was chosen after looking at data.** On 2026-07-29, while scoping
this gate, the outcome endpoint was measured as unaffordable (§2.1) and the
line-movement endpoint was then measured on 62 pre-gate games. It returned
beta +0.000819, t +2.07 unclustered, corr +0.256, surviving `mkt` removal, with
5 of 6 per-date betas positive.

That is a garden-of-forking-paths result with the worst possible provenance: an
endpoint selected *because* the registered one was underpowered, on data already
in hand.

Three things make the registration nonetheless clean:

1. **Those 62 games are pre-v8.11 and are excluded by era regardless.** The
   gate cannot read them. The sample is strictly prospective.
2. **The method registered here does not reproduce the exploratory result**
   (§5, p = 0.0533). The registration is not a lap of honour around a number
   already seen.
3. **This section exists.** A future reader can judge the provenance rather than
   having to take the file's word for it.

## 10. Non-suspension — binding

Restated from `DECISION_2026-07-28_GATE_SUSPENSION.md` §4, and applying in full
to **this** gate:

> **This suspension is non-repeatable.**
>
> A second suspension of a pre-registered gate, on any grounds whatsoever,
> constitutes failure of the pre-registration mechanism itself. Should that
> happen:
>
> - No λ estimate this project has produced should be treated as evidence.
> - The correct response is to stop, not to re-register a third time.
> - This clause may not be amended by the session that would benefit from
>   amending it.
>
> Any future session proposing to move, soften, delay, or re-scope a
> pre-registered gate must surface this section to Benjamin verbatim before
> proceeding.

**Extension specific to this gate:** re-scoping includes *changing the composite
underneath it and resetting the era*. Phase 1 shipped four era boundaries in
three days; doing that again mid-accrual would void this gate as effectively as
suspending it, and is covered by the clause above.

---

*All outputs are expected value, never predictions. No outcome is guaranteed.
System remains paper-only; nothing in this file supports going live.*
