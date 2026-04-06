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
- `chart` currently validates candidate input and returns the candidate file path.
- `review` expects chart inputs under the skill runtime directory.
