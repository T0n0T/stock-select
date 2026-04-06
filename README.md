# stock-select

Standalone repository bootstrap for the `stock-select` skill and CLI.

Current bootstrap scope:

- `pyproject.toml` defines the standalone `uv` package metadata and core runtime dependencies.
- `src/stock_select/__init__.py` exposes the placeholder CLI entrypoint used during early setup.
- `docs/superpowers/specs` and `docs/superpowers/plans` contain the migrated design and implementation plan for follow-up tasks.

This repository is intentionally separate from `/home/pi/Documents/agents/StockTradebyZ`, which remains a read-only reference during migration.
