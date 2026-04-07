# Mplfinance Charting Design

## Goal

Replace the current Plotly and Kaleido based PNG export path with a pure Python `mplfinance` implementation so chart export no longer depends on Chrome or Chromium.

## Scope

In scope:

- replace the static chart rendering implementation in `src/stock_select/charting.py`
- keep the existing `export_daily_chart(df, code, out_path, bars=120)` interface
- preserve the current runtime output contract:
  - PNG output
  - one daily candlestick chart per candidate
  - two indicator overlays: `zxdq` and `zxdkx`
  - one volume subplot
- update tests and dependencies to match the new renderer

Out of scope:

- HTML chart export
- browser-based interactivity
- charting changes outside the standalone CLI runtime outputs
- changes to B1 logic, review orchestration, or runtime layout

## Current Problem

The current charting path uses:

- `plotly`
- `kaleido`
- a system Chrome or Chromium runtime

This introduces operational fragility for a CLI-oriented repository whose primary need is deterministic static image output for downstream review.

## Design

### 1. Rendering Engine

Use `mplfinance` on top of `matplotlib` to render a static figure directly to PNG.

This removes the browser dependency while keeping support for:

- OHLC candlesticks
- indicator overlays
- volume subplot

### 2. Chart Structure

The rendered chart should preserve the existing analytical structure:

- main panel:
  - daily candlesticks
  - `zxdq` line
  - `zxdkx` line
- lower panel:
  - daily volume bars

The visual style may differ slightly from the Plotly version. That is acceptable as long as the structure and information density remain equivalent.

### 3. Data Preparation

`charting.py` should build a normalized DataFrame indexed by trading date and containing:

- `Open`
- `High`
- `Low`
- `Close`
- `Volume`
- `zxdq`
- `zxdkx`

This helper should also enforce date sorting and the `bars` tail window.

### 4. Public API

Keep:

- `export_daily_chart(df, code, out_path, bars=120) -> Path`

`build_daily_chart()` no longer needs to return a Plotly figure. It may be replaced by a helper that returns the prepared plotting DataFrame and plot configuration needed by `export_daily_chart()`.

### 5. Dependency Changes

Add:

- `mplfinance`

Remove:

- `kaleido`
- `plotly`

This is safe because current repository behavior only requires static PNG export, not interactive chart objects.

## Error Handling

- invalid or empty price data should continue to fail before export, as today
- no browser-related runtime errors should remain after the migration
- export should raise normal Python or matplotlib errors only when the input data or filesystem state is invalid

## Testing

Required test coverage:

- chart preparation keeps the expected columns and date ordering
- export writes a PNG file
- export respects the `bars` tail window
- no Plotly-specific tests remain

Tests should validate the stable contract of the exporter, not internal matplotlib artist details.

## Success Criteria

- `stock-select chart` can render PNG charts without Chrome or Chromium
- repository dependencies no longer include `kaleido`
- repository dependencies no longer include `plotly`
- existing CLI callers do not need to change
