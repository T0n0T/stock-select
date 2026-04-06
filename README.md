# stock-select

Standalone repository bootstrap for the `stock-select` skill and CLI.

Current bootstrap scope:

- `pyproject.toml` defines the standalone `uv` package metadata and core runtime dependencies.
- `src/stock_select/__init__.py` exposes the placeholder CLI entrypoint used during early setup.
- `docs/superpowers/specs` and `docs/superpowers/plans` contain the migrated design and implementation plan for follow-up tasks.

This repository is intentionally separate from `/home/pi/Documents/agents/StockTradebyZ`, which remains a read-only reference during migration.

## Usage

Install dependencies:

```bash
uv sync
```

Smoke-test commands:

```bash
uv run stock-select screen --method b1 --pick-date YYYY-MM-DD
uv run stock-select chart --method b1 --pick-date YYYY-MM-DD
uv run stock-select review --method b1 --pick-date YYYY-MM-DD
uv run stock-select run --method b1 --pick-date YYYY-MM-DD
```

Current smoke-test note:

- `screen` writes candidate JSON under `~/.agents/skills/stock-select/runtime/candidates/`.
- `chart` reads the candidate file and writes HTML charts under `~/.agents/skills/stock-select/runtime/charts/<pick_date>/`.
- `review` reads chart outputs and writes per-run summary JSON under `~/.agents/skills/stock-select/runtime/reviews/<pick_date>/summary.json`.
- `run` now chains `screen`, `chart`, and `review` through the skill-local runtime directory.
- The current `screen` implementation is still a deterministic placeholder and emits an empty candidate list until database-backed screening is wired in.
