# Turnover-Top MA25 Above MA60 Gate Design

## Goal

Tighten the default `turnover-top` screening pool by requiring `ma25 > ma60` before a symbol can enter the top-turnover candidate pool.

This change should apply only to the default shared pool source:

- `pool_source=turnover-top`

It should affect all methods that consume that default pool:

- `b1`
- `b2`
- `dribull`
- `hcr`

It must not change the behavior of:

- `pool_source=record-watch`
- `pool_source=custom`

## Current Problem

The current default pool gate uses only `turnover_n` ranking:

- build a per-trade-date universe from prepared symbol data
- sort by `turnover_n`
- keep the top `5000`

This means a symbol can enter the default candidate pool even when its medium-term moving-average structure is not in constructive alignment.

The requested tightening is to require the faster medium-term average to already be above the slower one before the symbol is even considered for the default pool.

## Design Decision

Add the rule `ma25 > ma60` inside the shared `build_top_turnover_pool(...)` helper in [src/stock_select/strategies/b1.py](/home/pi/Documents/agents/stock-select/src/stock_select/strategies/b1.py).

This is the correct layer because:

- `turnover-top` is a shared pool concept, not a method-specific screen rule
- the helper already owns per-trade-date pool membership before ranking
- `ma25` and `ma60` are already computed in shared prepared data for the methods that use this pool path

Do not duplicate this filter in `cli.py` or in method-specific screening functions.

## Rule Semantics

For each symbol row considered by `build_top_turnover_pool(...)`, the row is eligible for the default pool only when all of the following are true:

1. `trade_date` is valid
2. `turnover_n` is valid
3. `ma25` is valid
4. `ma60` is valid
5. `ma25 > ma60`

If any of these checks fail, the row is excluded from the pool before ranking.

After filtering, the helper should keep its current behavior:

- group by `trade_date`
- sort eligible rows by `turnover_n` descending
- keep the top `top_m`
- return the symbol list for each trade date

## Scope

In scope:

- tighten the shared `turnover-top` pool membership rule
- apply the rule consistently to end-of-day and intraday flows that reuse the same helper
- preserve existing pool-size ranking behavior after filtering
- add automated coverage for the new gate

Out of scope:

- changing any method-specific screening formula
- changing `record-watch`
- changing `custom`
- changing `top_m`
- introducing a configurable MA gate threshold
- changing review scoring logic

## Implementation Shape

### 1. Shared Pool Helper

Update `build_top_turnover_pool(...)` so that it reads and normalizes:

- `trade_date`
- `turnover_n`
- `ma25`
- `ma60`

Rows should be skipped when:

- `trade_date` is missing
- `turnover_n` is missing
- `ma25` is missing
- `ma60` is missing
- `ma25 <= ma60`

This keeps the filtering local to the helper that already defines default-pool membership.

### 2. CLI Behavior

No CLI contract changes are required.

Existing `screen` and `run` commands should continue to behave the same way externally:

- default remains `--pool-source turnover-top`
- `record-watch` remains untouched
- `custom` remains untouched

The only observable behavior change is that fewer symbols may enter the default pool when `ma25 <= ma60`.

## Method Impact

This is an intentional shared behavior change for all methods that use `turnover-top`:

- `b1`
- `b2`
- `dribull`
- `hcr`

This is acceptable because the requested rule is explicitly about the default candidate pool, not about one strategy's internal formula.

## Edge Cases

### 1. Insufficient History

If a symbol lacks enough history for either `ma25` or `ma60` on a trade date, that row should not enter the default pool.

This is consistent with the meaning of the new rule: the pool gate requires a valid `ma25 > ma60` relationship, not an inferred fallback.

### 2. Malformed Numeric Inputs

If `turnover_n`, `ma25`, or `ma60` cannot be parsed as numeric values, the row should be skipped rather than causing the pool builder to fail.

This matches the current helper behavior for malformed pool inputs.

### 3. Non-default Pool Sources

The new gate must not be applied after `record-watch` or `custom` resolution. Those sources continue to be defined only by their own symbol lists intersected with prepared data.

## Test Plan

Add focused coverage in existing test files.

### 1. Pool Helper Tests

Extend [tests/test_b1_logic.py](/home/pi/Documents/agents/stock-select/tests/test_b1_logic.py):

- verify that `build_top_turnover_pool(...)` excludes a higher-turnover symbol when `ma25 <= ma60`
- verify that rows missing `ma25` or `ma60` are skipped
- keep existing malformed-row behavior intact

### 2. CLI Pool-Resolution Test

Add or update one focused test in [tests/test_cli.py](/home/pi/Documents/agents/stock-select/tests/test_cli.py) to verify:

- under `pool_source=turnover-top`, only symbols surviving the shared pool helper reach the method screen call
- `record-watch` and `custom` are not newly gated by `ma25 > ma60`

## Expected Outcome

After this change:

- default `turnover-top` candidate pools will be smaller or equal in size
- every symbol entering the default pool on a trade date will satisfy `ma25 > ma60`
- `record-watch` and `custom` workflows will behave exactly as before
- no method-specific screening formula will change
