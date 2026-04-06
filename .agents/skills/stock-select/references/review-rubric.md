# Chart Review Rubric

Review charts as a visual trading assessment only. Use only information that is visible on the daily chart.

## Dimensions

### Trend Structure

Assess moving-average direction, alignment, and whether price is trending smoothly or only rebounding.

### Price Position Structure

Assess whether price is breaking out from a lower-risk area, pushing into prior resistance, or already extended near a crowded high-risk zone.

### Volume Behavior

Assess whether advancing legs expand in volume, pullbacks contract in volume, and whether the largest volume events happen on constructive candles rather than destructive selloffs.

### Previous Abnormal Move

Assess whether the chart shows an earlier institutional-style accumulation burst, breakout candle, or abnormal move that still supports the current setup without already exhausting the move.

## Signal Type

Choose exactly one:

- `trend_start`
- `rebound`
- `distribution_risk`

## Decision Rules

- `PASS` when the weighted total is at least 4.0.
- `WATCH` when the weighted total is at least 3.2 and below 4.0.
- `FAIL` when the weighted total is below 3.2.
- Force `FAIL` if volume behavior is the weakest grade and shows clear distribution risk.

## Output Shape

Return structured JSON with:

- `trend_structure`
- `price_position`
- `volume_behavior`
- `previous_abnormal_move`
- `signal_type`
- `decision`
- `comment`

The final `comment` should be one concise Chinese trader-style sentence covering trend, volume-price structure, prior abnormal move, and present risk or upside room.
