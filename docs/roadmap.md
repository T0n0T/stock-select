# stock-select-rs Roadmap

## Purpose

Track the Rust refactor status for `/home/pi/Documents/agents/stock-select` and provide the next execution path for making b1 Rust CLI functionality native while keeping Python artifact parity.

## Current Architecture

The Rust CLI is currently a hybrid replacement path:

```text
stock-select-rs screen  -> Rust native
stock-select-rs chart   -> Rust CLI bridge to Python chart
stock-select-rs review  -> Rust CLI bridge to Python review
stock-select-rs run     -> Rust screen + Python chart + Python review
```

The user-facing runtime layout is aligned with Python:

```text
candidates/<pick_date>.<method>.json
charts/<pick_date>.<method>/<code>_day.png
reviews/<pick_date>.<method>/<code>.json
reviews/<pick_date>.<method>/summary.json
reviews/<pick_date>.<method>/llm_review_tasks.json
```

## Verified b1 Parity

Python golden artifacts are read from:

```text
~/.agents/skills/stock-select/runtime
```

Do not recompute Python outputs unless explicitly requested.

Verified b1 screen parity:

```text
2026-05-25: 104/104
2026-05-22: 114/114
2026-05-21: 137/137
2026-05-20: 117/117
2026-05-19: 108/108
```

Verified b1 review parity through Rust CLI bridge:

```text
pick_date=2026-05-25
reviewed=104
recommendations=3
recommendation codes=000066.SZ,300292.SZ,301290.SZ
```

Representative validation command:

```bash
rm -rf /tmp/stock-select-rs-review-cli-b1

cargo run --release -- screen \
  --method b1 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-review-cli-b1 \
  --recompute

cargo run --release -- chart \
  --method b1 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-review-cli-b1

cargo run --release -- review \
  --method b1 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-review-cli-b1 \
  --environment-state weak \
  --environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱"

python3 scripts/compare_screen.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root /tmp/stock-select-rs-review-cli-b1 \
  --pick-date 2026-05-25 \
  --method b1

python3 scripts/compare_review.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root /tmp/stock-select-rs-review-cli-b1 \
  --pick-date 2026-05-25 \
  --method b1
```

Expected:

```text
PASS screen comparison method=b1 pick_date=2026-05-25 candidates=104/104
PASS review comparison method=b1 pick_date=2026-05-25 reviewed=104 recommendations=3
```

## Completed Rust-Native Work

### Screen

Rust-native screen includes:

- PostgreSQL `daily_market` loading.
- Prepared indicator cache under `prepared/*.bin` plus `*.meta.json`.
- b1/b2/dribull screen candidate generation.
- b1 candidate ordering aligned with Python by code ascending.
- turnover-top pool alignment with Python defaults.

Important b1 alignment details already handled:

- preserve DB NULL OHLCV rows as NaN-like values during preparation semantics
- pandas-like rolling window invalidation
- pandas `ewm(adjust=False)` behavior after NaN gaps
- KDJ RSV invalid fallback to `0.0`
- weekly close aggregation using last non-NaN close while retaining last row date
- default pool source `turnover-top`, including `ma25 > ma60` and top 5000 by `turnover_n`

### CLI Bridge

Rust CLI now exposes:

```text
screen
chart
review
run
```

`chart`, `review`, and `run` bridge to Python where native Rust is not ready. `review` and `run` forward:

```text
--dsn
--environment-state
--environment-reason
--llm-min-baseline-score
--llm-review-limit
```

### Chart

Rust CLI has a `chart` command, but chart rendering still happens in Python:

```text
Rust Command -> uv run stock-select chart
```

Rust-generated chart artifacts were smoke-checked as real PNGs. Existing Python runtime chart files for `2026-05-25.b1` are placeholder text files, so they are not usable as PNG visual golden files.

### Review Core

Rust-native review groundwork exists:

- `src/environment_profiles.rs`
  - b1/b2 weak/neutral/strong profile constants
  - weights, thresholds, subscore modes, and `llm_focus`
- `src/review_protocol.rs`
  - baseline score weighting
  - b1/b2 score weighting
  - profile-aware score weighting
  - signal type and verdict helpers
  - Python-compatible two-decimal float formatting behavior
- `src/reviewers/b1.rs`
  - b1 decision core for final baseline decision fields
  - score combo key
  - high-return combo classification
  - pass family/tier classification
  - environment verdict gate
  - score layer and calibrated total score

Current b1 native decision core is validated against representative Python baseline samples:

```text
000066.SZ exact distribution PASS-B total_score=4.78
runup-over-limit exact distribution WATCH-A total_score=4.32
300166.SZ rebound near WATCH-C total_score=3.54
002428.SZ non-family rebound FAIL total_score=2.91
```

## Known Gaps

### Review Is Not Fully Native Yet

`stock-select-rs review` still delegates complete per-stock review execution to Python. Rust-native code can decide final b1 fields once supplied with the same inputs, but Rust does not yet compute all required inputs from OHLCV history.

Missing b1 native pieces:

- one-year per-candidate history loading for review
- review prepared frame construction
- b1 trend structure score
- b1 price position score
- b1 volume behavior score
- previous abnormal move score
- MACD wave classification
- MACD phase score and divergence penalty
- environment gate metrics:
  - cooldown flags
  - below MA25
  - runup percent
  - sideways amplitude
  - weekly MACD cooldown
- comment generation
- `llm_review_tasks.json` task context generation
- summary/recommendation writer

### Environment Profile Status

Python currently owns automatic market environment resolution and profile application.

Rust currently supports:

- profile constants
- profile-aware scoring helpers
- manual environment forwarding to Python review

Rust does not yet support:

- automatic market environment evaluation
- runtime `environment/history.jsonl` resolution
- environment daily/latest file writing

### Chart Status

Chart rendering is still Python. This is intentional until review parity is native and chart visual smoke tests are stronger.

## Next Roadmap

### Phase 1: b1 Review Fixture Harness

Goal: compare Rust-native b1 decision core against every Python baseline review artifact.

Tasks:

1. Add a fixture loader for `reviews/2026-05-25.b1/*.json`.
2. Extract these fields from each Python baseline review:
   - `signal_type`
   - `trend_structure`
   - `price_position`
   - `volume_behavior`
   - `previous_abnormal_move`
   - `macd_phase`
   - `raw_total_score`
   - `gate_flags`
   - `environment_state`
3. Feed those values into `decide_b1_review`.
4. Assert Rust output matches Python:
   - `score_combo_key`
   - `high_return_combo_match`
   - `pass_family`
   - `pass_family_tier`
   - `verdict`
   - `total_score`
   - `score_layer`
   - `score_layer_score`

Acceptance:

```text
104/104 b1 decision fixtures match Python for 2026-05-25
```

### Phase 2: Native b1 History Scoring

Goal: compute the b1 input scores natively from OHLCV history.

Suggested order:

1. Fetch one-year candidate histories in Rust.
2. Port or reuse MA25, BBI, zxdq/zxdkx, MACD helpers.
3. Implement and fixture-test:
   - trend structure
   - price position
   - volume behavior
   - previous abnormal move
4. Keep each score function independently tested before composing the full reviewer.

Acceptance:

```text
For 2026-05-25 b1, all 104 symbols match Python baseline score fields.
```

### Phase 3: MACD Wave Port

Goal: port Python `analysis/macd_waves.py` and b1 MACD phase logic.

Tasks:

1. Implement MACD state machine structs.
2. Implement daily MACD trend classification.
3. Implement weekly aggregation and weekly MACD trend classification.
4. Generate text context:
   - `weekly_wave_context`
   - `daily_wave_context`
   - `wave_combo_context`
5. Match Python reason strings where they affect comments/tasks.

Acceptance:

```text
For 2026-05-25 b1, all 104 symbols match Python macd_phase and wave task context.
```

### Phase 4: Native b1 Review Command

Goal: add native Rust review path behind an explicit option before changing defaults.

Proposed CLI:

```bash
stock-select-rs review \
  --method b1 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-native-review-b1 \
  --environment-state weak \
  --environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱" \
  --native
```

Acceptance:

```text
python3 scripts/compare_review.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root /tmp/stock-select-rs-native-review-b1 \
  --pick-date 2026-05-25 \
  --method b1

PASS review comparison method=b1 pick_date=2026-05-25 reviewed=104 recommendations=3
```

### Phase 5: Switch b1 run Review Default

Only after native b1 review passes full golden comparison:

- make `stock-select-rs review --method b1` native by default
- keep Python bridge behind an explicit fallback option
- update `stock-select-rs run --method b1` to use native review

## Verification Baseline

Run before claiming progress:

```bash
cargo fmt --check
cargo test --quiet
python3 -m py_compile scripts/check_charts.py scripts/compare_screen.py scripts/compare_review.py
```

For b1 CLI parity:

```bash
python3 scripts/compare_screen.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root <rust-runtime-root> \
  --pick-date 2026-05-25 \
  --method b1

python3 scripts/compare_review.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root <rust-runtime-root> \
  --pick-date 2026-05-25 \
  --method b1
```

## Recent Commit Trail

```text
fbbb1fc feat: add b1 reviewer decision core
c989bf4 feat: add review command bridge
7c86956 feat: add review profile scoring core
c5805c0 feat: add chart command bridge
46b3003 docs: add review rust port design
1e93035 docs: add chart bridge design
c8b14be test: add review golden comparison script
4d23d46 feat: add hybrid run command
56262ea test: add multi-date b1 screen regression
2683a51 test: add screen golden comparison script
```
