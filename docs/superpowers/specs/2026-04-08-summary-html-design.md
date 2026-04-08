# Summary HTML Design

## Goal

Generate a single self-contained HTML file from the existing review summary output at:

- `~/.agents/skills/stock-select/runtime/reviews/2026-04-08/summary.json`

The HTML should be directly openable in a browser with no build step, external assets, or server dependency.

## Scope

This work only covers a read-only presentation layer for one already-generated summary file.

It does not:

- rerun screening or review
- change summary scoring logic
- add a new CLI command
- introduce a template engine or frontend framework

## Approach

Use a small Python script invocation to read `summary.json` and emit one static `summary.html` file beside it.

Recommended output path:

- `~/.agents/skills/stock-select/runtime/reviews/2026-04-08/summary.html`

The HTML will inline:

- CSS for layout and visual hierarchy
- a small amount of JavaScript for expand/collapse interactions
- all rendered summary content

## Page Structure

The page should contain:

1. A header with:
   - pick date
   - method
   - reviewed count
   - recommendation count
   - failure count

2. A recommendation section:
   - highlight `PASS` items first
   - show code, final score, signal type, review mode, short comment

3. An excluded section:
   - include both `WATCH` and `FAIL`
   - sort by final score descending as already present in summary

4. Per-stock detail cards:
   - code and verdict badge
   - final merged score
   - signal type
   - merged comment
   - baseline review summary
   - llm review summary when present
   - chart image preview using the existing absolute chart path

5. Expandable detail block:
   - baseline score breakdown
   - llm score breakdown
   - reasoning text fields when present

## Visual Direction

Prefer an information-dense but clean layout:

- light background
- strong table/card readability
- clear color coding for `PASS`, `WATCH`, `FAIL`
- sticky or visually distinct top summary metrics
- responsive layout that still works on narrow screens

Avoid decorative complexity. This is an analysis artifact, not a marketing page.

## Data Handling

The implementation should:

- read the already-final `summary.json`
- tolerate missing `llm_review`
- tolerate absent `final_score` by falling back to `total_score`
- HTML-escape user-visible text content before embedding

## Error Handling

If `summary.json` is missing or invalid:

- fail loudly in the generator step
- do not emit a partial misleading HTML file

## Verification

Verification is complete when:

- `summary.html` exists at the target runtime path
- the file opens locally as a standalone document
- key counts in the header match `summary.json`
- the recommendation list includes the merged `PASS` result
- at least one card correctly shows baseline plus llm-derived merged content
