# Custom Pool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `custom` pool source that reads whitespace-separated stock codes from a text file via `--pool-source custom --pool-file PATH`, with env/default fallbacks and updated skill documentation.

**Architecture:** Extend the existing shared pool resolver in `src/stock_select/cli.py` instead of adding per-method branches. Keep `pool_source` enum-like, thread an optional `pool_file` through CLI plumbing, resolve the effective file path in one helper, parse codes from a text file, and continue intersecting with the prepared screening universe.

**Tech Stack:** Python, Typer, pytest, existing stock-select CLI + skill docs

---

### Task 1: Add failing CLI and resolver tests

**Files:**
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_screen_accepts_custom_pool_file_and_passes_it_to_screen_impl(...):
    ...
    assert kwargs["pool_source"] == "custom"
    assert kwargs["pool_file"] == pool_file


def test_run_accepts_custom_pool_file_and_passes_it_to_screen_step(...):
    ...
    assert kwargs["pool_source"] == "custom"
    assert kwargs["pool_file"] == pool_file


def test_screen_custom_pool_rejects_missing_configuration_with_guidance(...):
    ...
    assert "--pool-file" in result.stderr
    assert "STOCK_SELECT_POOL_FILE" in result.stderr
    assert "custom-pool.txt" in result.stderr


def test_screen_custom_pool_rejects_empty_code_list(...):
    ...
    assert "at least one stock code" in result.stderr.lower()


def test_screen_custom_pool_uses_whitespace_separated_file_codes(...):
    ...
    assert [item["code"] for item in payload["candidates"]] == ["AAA.SZ", "CCC.SZ"]
```

- [ ] **Step 2: Run the targeted tests to verify RED**

Run: `uv run pytest tests/test_cli.py::test_screen_accepts_custom_pool_file_and_passes_it_to_screen_impl tests/test_cli.py::test_run_accepts_custom_pool_file_and_passes_it_to_screen_step tests/test_cli.py::test_screen_custom_pool_rejects_missing_configuration_with_guidance tests/test_cli.py::test_screen_custom_pool_rejects_empty_code_list tests/test_cli.py::test_screen_custom_pool_uses_whitespace_separated_file_codes -v`
Expected: FAIL because `custom` and `--pool-file` are not supported yet.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_cli.py
git commit -m "test: cover custom pool cli contract"
```

### Task 2: Implement minimal custom-pool plumbing

**Files:**
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: Add minimal implementation**

```python
def _validate_pool_source(pool_source: str) -> str:
    normalized = pool_source.strip().lower()
    supported_sources = {"turnover-top", "record-watch", "custom"}
    ...


def _default_custom_pool_path() -> Path:
    return _default_runtime_root() / "custom-pool.txt"


def _resolve_custom_pool_file(pool_file: Path | None) -> Path:
    env_value = os.getenv("STOCK_SELECT_POOL_FILE")
    if pool_file is not None:
        return pool_file
    if env_value:
        return Path(env_value).expanduser()
    return _default_custom_pool_path()


def _load_custom_pool_codes(pool_file: Path | None) -> list[str]:
    path = _resolve_custom_pool_file(pool_file)
    if not path.exists():
        raise typer.BadParameter(...guidance...)
    codes = [token.strip() for token in path.read_text(encoding="utf-8").split() if token.strip()]
    if not codes:
        raise typer.BadParameter("Custom pool must contain at least one stock code.")
    return codes
```

Thread `pool_file: Path | None` through:
- `screen`
- `run`
- `_screen_impl`
- `_screen_intraday_impl`
- `_resolve_pool_codes`

Add a `custom` branch in `_resolve_pool_codes(...)` that intersects parsed custom codes with `prepared_by_symbol` and raises a clear `typer.BadParameter` when the effective custom pool is empty after intersection.

- [ ] **Step 2: Run the targeted tests to verify GREEN**

Run: `uv run pytest tests/test_cli.py::test_screen_accepts_custom_pool_file_and_passes_it_to_screen_impl tests/test_cli.py::test_run_accepts_custom_pool_file_and_passes_it_to_screen_step tests/test_cli.py::test_screen_custom_pool_rejects_missing_configuration_with_guidance tests/test_cli.py::test_screen_custom_pool_rejects_empty_code_list tests/test_cli.py::test_screen_custom_pool_uses_whitespace_separated_file_codes -v`
Expected: PASS

- [ ] **Step 3: Commit the implementation**

```bash
git add src/stock_select/cli.py tests/test_cli.py
git commit -m "feat: add custom pool file support"
```

### Task 3: Update the stock-select skill and verify regressions

**Files:**
- Modify: `.agents/skills/stock-select/SKILL.md`
- Modify: `tests/test_cli.py` if any final wording-driven assertion adjustments are needed

- [ ] **Step 1: Update skill documentation**

```md
- Pool sources are `turnover-top`, `record-watch`, and `custom`.
- `custom` uses `--pool-source custom`.
- Custom pool path precedence is `--pool-file`, `STOCK_SELECT_POOL_FILE`, then `~/.agent/skills/stock-select/runtime/custom-pool.txt`.
- Custom pool files contain whitespace-separated stock codes, for example `603138 300058`.
```

- [ ] **Step 2: Run focused regression verification**

Run: `uv run pytest tests/test_cli.py::test_screen_accepts_pool_source_and_passes_it_to_screen_impl tests/test_cli.py::test_run_accepts_pool_source_and_passes_it_to_screen_step tests/test_cli.py::test_run_intraday_accepts_pool_source_and_passes_it_to_intraday_screen_step tests/test_cli.py::test_screen_accepts_custom_pool_file_and_passes_it_to_screen_impl tests/test_cli.py::test_run_accepts_custom_pool_file_and_passes_it_to_screen_step tests/test_cli.py::test_screen_custom_pool_rejects_missing_configuration_with_guidance tests/test_cli.py::test_screen_custom_pool_rejects_empty_code_list tests/test_cli.py::test_screen_custom_pool_uses_whitespace_separated_file_codes -v`
Expected: PASS

- [ ] **Step 3: Run broader CLI verification**

Run: `uv run pytest tests/test_cli.py -q`
Expected: PASS

- [ ] **Step 4: Commit docs + final verification state**

```bash
git add .agents/skills/stock-select/SKILL.md tests/test_cli.py
git commit -m "docs: document custom pool selection"
```
