# 2026-04-14 Custom Pool File Design

## Goal
Add a third CLI pool source, `custom`, so callers can screen from a whitespace-separated text file of stock codes using the formal interface `--pool-source custom --pool-file PATH`, while preserving the existing `turnover-top` and `record-watch` behavior.

## Scope
In scope:
- add `custom` as a valid `pool_source`
- add `--pool-file` to `screen` and `run`
- resolve custom pool path using this precedence:
  1. explicit `--pool-file`
  2. environment variable `STOCK_SELECT_POOL_FILE`
  3. default `~/.agent/skills/stock-select/runtime/custom-pool.txt`
- parse stock codes from the selected file by splitting on arbitrary whitespace
- require that at least one code is recognized from the file contents
- when no custom-pool path is available or the selected file is missing, raise a clear `typer.BadParameter` that tells the user all supported ways to define a custom pool
- pass the resolved `pool_file` through CLI plumbing into the shared pool resolver
- continue intersecting custom pool codes with the prepared universe before screening
- update the bundled `stock-select` skill documentation to describe pool selection, custom-pool precedence, file format, and the default path

Out of scope:
- changing pool semantics for `turnover-top` or `record-watch`
- adding a generic code-format normalization layer beyond the repository's current symbol handling
- adding a new standalone command for custom pool management

## CLI Contract
`screen` and `run` will both accept:
- `--pool-source custom`
- optional `--pool-file PATH`

Rules:
- `--pool-file` is only meaningful when `pool_source=custom`; for other sources it is accepted but ignored only if the current CLI already tolerates extra options through plumbing. The implementation should keep behavior minimal and not add unrelated validation.
- `pool_source` remains a normalized enum-like value stored in candidate payloads and prepared-cache metadata.
- `pool_file` is runtime configuration, not part of the stable pool-source identity. Reuse safety continues to be keyed by `pool_source`, not by a file-content hash.

## Resolver Design
Extend the existing shared pool-resolution path in `src/stock_select/cli.py`.

Add helpers for:
- resolving the effective custom pool file path from CLI / env / default
- loading custom pool codes from the chosen text file
- raising a single clear guidance error when the custom pool file is missing or not configured by any supported method

Resolution flow for `pool_source=custom`:
1. Resolve the effective file path with precedence `--pool-file` > `STOCK_SELECT_POOL_FILE` > default runtime path.
2. If the resulting path does not exist, raise `typer.BadParameter` with guidance that mentions:
   - `--pool-file PATH`
   - `STOCK_SELECT_POOL_FILE`
   - `~/.agent/skills/stock-select/runtime/custom-pool.txt`
3. Read the file as UTF-8 text and split on whitespace.
4. If zero non-empty tokens are found, raise `typer.BadParameter` stating that at least one stock code must be provided.
5. Intersect parsed codes with `prepared_by_symbol` and return the surviving list.
6. If the intersection is empty, raise `typer.BadParameter` explaining that the effective custom pool is empty after prepared-data intersection.

This keeps `custom` aligned with the current `record-watch` contract: resolve explicit symbols first, then intersect with the prepared universe.

## Testing
Follow TDD and add failing CLI-focused tests before implementation.

Minimum coverage:
- `screen` accepts `--pool-source custom --pool-file PATH` and passes both through to `_screen_impl`
- `run` accepts `--pool-source custom --pool-file PATH` and passes both through to the screen step
- invalid custom configuration with no CLI path, no env var, and no default file fails with guidance mentioning all three supported setup methods
- custom pool file parsing accepts whitespace-separated codes and screens only the matching prepared subset
- custom pool file with no recognizable codes fails clearly
- update or extend at least one end-to-end CLI contract test through the shared resolver path so the new source is exercised beyond pure option plumbing

## Skill Update
Update `.agents/skills/stock-select/SKILL.md` to explicitly document pool selection:
- built-in pool sources: `turnover-top`, `record-watch`, `custom`
- `custom` uses `--pool-source custom`
- path precedence: `--pool-file`, `STOCK_SELECT_POOL_FILE`, default runtime file
- file format example: `603138 300058`
- note that custom pool still intersects with the prepared screening universe

## Risks and Constraints
- Do not break existing payload metadata or reuse checks for `turnover-top` and `record-watch`.
- Keep implementation in the existing shared resolver shape rather than adding per-method branches.
- Keep errors user-facing and actionable; avoid low-level `FileNotFoundError` leaking to stderr.
