# B1 Screen Tightening Design

## Goal

Reduce the number of symbols returned by `screen --method b1` without changing the core identity of the current `b1` strategy.

The current deterministic `b1` preselection is intentionally simple:

- low `J` by absolute threshold or expanding historical quantile
- `close > zxdkx`
- `zxdq > zxdkx`
- weekly moving averages in bullish alignment
- max-volume day in the lookback window is not bearish

That logic is implemented in [src/stock_select/strategies/b1.py](/home/pi/Documents/agents/stock-select/src/stock_select/strategies/b1.py) and documented in [references/b1-selector.md](/home/pi/Documents/agents/stock-select/.agents/skills/stock-select/references/b1-selector.md).

The user provided an alternative `b1` formula that adds several risk and structure filters. The design goal is to borrow only the parts that materially tighten the current selector while preserving its left-side setup semantics.

## Current Problem

Recent end-of-day runs are returning around 28 to 31 `b1` candidates per day, which is too many for downstream chart review.

The existing `b1` filter is currently narrow in concept but broad in practice because it does not explicitly reject:

- non-shrinking volume during the pullback
- symbols that recently printed a heavy distribution day and have not cooled off
- long-trend baselines that have started flipping direction too frequently
- symbols already extended by a large same-day price move

These are all present in the alternative formula, but the full formula is not a stricter superset of the current strategy. It is a multi-branch selector that would widen the universe if ported directly.

## Evaluation Summary

Using the local prepared cache and review outputs for `2026-04-20`:

- current repository `b1` selected 30 symbols
- the full alternative formula selected 61 symbols inside the same top-turnover pool
- overlap between the two sets was only 15 symbols

That result confirms the alternative formula should not replace the current strategy wholesale.

On the same `2026-04-20` candidate set, the following individual filters tightened the current 30-symbol output while preserving both of the day’s `WATCH` names:

- `V_SHRINK`: 30 -> 26
- `SAFE_MODE`: 30 -> 28
- `LT_FILTER`: 30 -> 28
- `CHG_D <= 4.0`: 30 -> 28

The combined filter `V_SHRINK + SAFE_MODE + LT_FILTER + CHG_D <= 4.0` reduced the 30 current `b1` names to 22 while still preserving the two `WATCH` names from the baseline review.

By contrast, `HLTH_SPC` and any compound gate built around `ENV_OK` would remove both `WATCH` names on the same sample day, so they are too aggressive for the current `b1` strategy definition.

## Design Decision

Extend the current deterministic `b1` screening path with four additional hard filters, evaluated after the existing five core gates:

1. `CHG_D <= 4.0`
2. `V_SHRINK`
3. `SAFE_MODE`
4. `LT_FILTER`

This preserves the meaning of `b1` as a left-side setup selector built around low `J` and `zxdkx` support, while tightening the output using pullback quality and recent-risk constraints.

The following conditions from the user-provided formula are explicitly out of scope for this change:

- `HLTH_SPC`
- `ENV_OK` as a top-level hard gate
- `RSI6 > REF(RSI6, 1)` as a mandatory gate
- `C > O` as a mandatory gate
- `RED_1ST`
- `TOP_RES`
- `ACCUM_BASE`
- `B1_Q`

Those conditions either change the strategy into a more confirmation-oriented selector or introduce extra branches that broaden rather than tighten the existing `b1`.

## Formula Mapping

All added filters should be computed from the existing daily OHLCV input during `_prepare_screen_data()` and stored in the per-symbol prepared frame.

### `CHG_D`

Daily close-to-previous-close percentage change:

```text
REF_C = REF(C, 1)
CHG_D = (C - REF_C) / REF_C * 100
```

Required rule:

```text
CHG_D <= 4.0
```

### `V_SHRINK`

Short-term volume average must be below the medium short-term average:

```text
VM3 = MA(VOL, 3)
VM10 = MA(VOL, 10)
V_SHRINK = VM3 < VM10
```

### `SAFE_MODE`

Reject symbols that recently printed a heavy distribution day and have not cooled off long enough.

Definitions:

```text
REF_C = REF(C, 1)
CHG_D = (C - REF_C) / REF_C * 100
AMP_D = (H - L) / REF_C * 100
BODY_D = (O - C) / REF_C * 100
VM5 = MA(VOL, 5)
VM10 = MA(VOL, 10)
HIGH_POS = (HHV(H, 20) - LLV(L, 20)) / LLV(L, 20) * 100 > 15
VOL_BIG = VOL > VM5 * 1.3 OR VOL > VM10 * 1.5
BAD_DUMP = (BODY_D > 6.0 OR CHG_D < -5.5) AND VOL_BIG AND HIGH_POS
DUMP_DAY = BARSLAST(BAD_DUMP)
COOL_OFF = IF(COUNT(BAD_DUMP, 10) >= 2, 10, 5)
IN_REV = DUMP_DAY >= COOL_OFF AND DUMP_DAY <= 15
SHAPE_OK = AMP_D <= 10.0 AND CHG_D >= -4.0 AND CHG_D <= 4.0
M5 = MA(C, 5)
CG_OK = (C > M5) OR (M5 >= REF(M5, 1)) OR (ABS(C - M5) / M5 * 100 < 1.5)
SAFE_MODE = (DUMP_DAY >= COOL_OFF) AND IF(IN_REV, SHAPE_OK AND CG_OK, 1)
```

Interpretation for Python implementation:

- if the symbol has not had a qualifying `BAD_DUMP` inside the available history, treat `DUMP_DAY` as large enough to satisfy the cooling check
- if `BAD_DUMP` occurred recently, the symbol must either be fully past the cooling window or pass the tighter in-recovery shape checks

### `LT_FILTER`

Reject unstable long-trend baselines that are flipping direction too often, while keeping a waiver for fresh or clearly separated bullish crossovers.

Definitions:

```text
ST_T1 = EMA(EMA(C, 10), 10)
LT_T1 = (MA(C, 14) + MA(C, 28) + MA(C, 57) + MA(C, 114)) / 4
C_DAYS = BARSLAST(CROSS(ST_T1, LT_T1))
WAIVER = (C_DAYS >= 0 AND C_DAYS <= 30 AND ST_T1 > LT_T1) OR (ST_T1 > LT_T1 * 1.03)
LT_DIR = IF(BARSCOUNT(C) > 114, IF(LT_T1 > REF(LT_T1, 1), 1, -1), 1)
LT_FILTER = COUNT(LT_DIR != REF(LT_DIR, 1), 30) <= 2 OR WAIVER
```

Interpretation for Python implementation:

- `ST_T1` should reuse the same double-EMA construction already used for `zxdq`
- `LT_T1` matches the same moving-average average already used for `zxdkx`
- `LT_DIR` only starts directional flipping after enough history exists for the full `LT_T1`

## Screening Order

The first five existing `b1` conditions remain unchanged and in the same order.

New order:

1. low `J` by threshold or expanding quantile
2. `zxdkx` exists on the pick date
3. `close > zxdkx`
4. `zxdq > zxdkx`
5. `weekly_ma_bull`
6. `max_vol_not_bearish`
7. `CHG_D <= 4.0`
8. `V_SHRINK`
9. `SAFE_MODE`
10. `LT_FILTER`

Rationale:

- keep the current `b1` identity visible in the first stage
- only apply new tightening logic after a symbol already qualifies for the existing setup
- preserve current failure counts for the historical gates before counting new reasons

## Prepared Data Changes

Add the following prepared columns in `_prepare_screen_data()`:

- `chg_d`
- `amp_d`
- `body_d`
- `vm3`
- `vm5`
- `vm10`
- `m5`
- `v_shrink`
- `safe_mode`
- `lt_filter`

The strategy code should use these prepared columns instead of recomputing them inside the screening loop.

`ST_T1` and `LT_T1` do not need to be persisted as columns if the implementation only needs the final boolean `lt_filter`, but persisting them is acceptable if it makes testing clearer.

## Stats and CLI Output

Extend `run_b1_screen_with_stats()` with new first-failure counters:

- `fail_chg_cap`
- `fail_v_shrink`
- `fail_safe_mode`
- `fail_lt_filter`

The CLI screen progress summary should include these new counters in the printed breakdown so it is obvious where symbols are being rejected.

## Documentation Changes

Update the repository `B1` screening description in [README.md](/home/pi/Documents/agents/stock-select/README.md) to include the new filtering order and the meaning of the added rejection counters.

Update [references/b1-selector.md](/home/pi/Documents/agents/stock-select/.agents/skills/stock-select/references/b1-selector.md) so the bundled selector reference matches the actual screening behavior.

## Testing Requirements

Add deterministic tests that prove:

- a symbol failing only `CHG_D <= 4.0` is counted under `fail_chg_cap`
- a symbol failing only `V_SHRINK` is counted under `fail_v_shrink`
- a symbol failing only `SAFE_MODE` is counted under `fail_safe_mode`
- a symbol failing only `LT_FILTER` is counted under `fail_lt_filter`
- the new filters are applied after the current legacy conditions
- prepared data includes the new columns used by `b1`
- CLI progress output includes the new failure counters

The tests should extend existing `b1` strategy and CLI coverage rather than introducing a separate strategy test file.

## Non-Goals

This change does not:

- replace the current `b1` formula with the full user-provided formula
- add new `b1` sub-branches such as `B1_Y`, `B1_W`, `B1_Q`, or `TOP_RES`
- change the `review` phase scoring or verdict logic
- introduce configuration flags for enabling or disabling individual new filters

If later testing shows one of the new filters is too strict, that should be handled as a follow-up design rather than by broadening this scope now.
