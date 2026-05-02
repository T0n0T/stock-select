# Dribull Review Prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated `prompt-dribull.md` and route `dribull` review tasks to it so LLM review guidance matches the current `dribull` baseline review contract.

**Architecture:** Keep the shared `llm_review` JSON schema and merge flow unchanged. Isolate the change to method-specific prompt assets, review resolver routing, and supporting docs/tests so `b2` and `dribull` stop sharing mismatched review guidance.

**Tech Stack:** Python, pytest, Typer CLI, markdown prompt assets

---

### Task 1: Route `dribull` To A Dedicated Prompt Path

**Files:**
- Modify: `tests/test_review_resolvers.py`
- Modify: `src/stock_select/review_resolvers.py`
- Test: `tests/test_review_resolvers.py`

- [ ] **Step 1: Write the failing resolver test**

```python
def test_get_review_resolver_routes_dribull_to_dedicated_review_strategy() -> None:
    resolver = get_review_resolver("dribull")

    assert resolver.name == "dribull"
    assert resolver.prompt_path.endswith(".agents/skills/stock-select/references/prompt-dribull.md")
    assert resolver.review_history.__module__ == "stock_select.reviewers.dribull"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_review_resolvers.py::test_get_review_resolver_routes_dribull_to_dedicated_review_strategy -q`
Expected: FAIL because resolver still points to `prompt-b2.md`.

- [ ] **Step 3: Write minimal resolver implementation**

```python
B2_PROMPT_PATH = str(_REFERENCE_DIR / "prompt-b2.md")
DRIBULL_PROMPT_PATH = str(_REFERENCE_DIR / "prompt-dribull.md")


def get_review_resolver(method: str) -> ReviewResolver:
    normalized = method.strip().lower()
    if normalized == "b1":
        ...
    if normalized == "b2":
        return ReviewResolver(
            name="b2",
            prompt_path=B2_PROMPT_PATH,
            review_history=review_b2_symbol_history,
        )
    if normalized == "dribull":
        return ReviewResolver(
            name="dribull",
            prompt_path=DRIBULL_PROMPT_PATH,
            review_history=review_dribull_symbol_history,
        )
    return ReviewResolver(...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_review_resolvers.py::test_get_review_resolver_routes_dribull_to_dedicated_review_strategy -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_review_resolvers.py src/stock_select/review_resolvers.py
git commit -m "refactor: route dribull review to dedicated prompt"
```

### Task 2: Add The Dedicated `prompt-dribull.md` Asset

**Files:**
- Create: `.agents/skills/stock-select/references/prompt-dribull.md`
- Modify: `tests/test_cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing prompt-contract test**

```python
def test_prompt_dribull_documents_dedicated_contract() -> None:
    content = Path(".agents/skills/stock-select/references/prompt-dribull.md").read_text(encoding="utf-8")

    assert "符合 `dribull`" in content
    assert "trend_structure：0.18" in content
    assert "price_position：0.18" in content
    assert "volume_behavior：0.24" in content
    assert "previous_abnormal_move：0.20" in content
    assert "macd_phase：0.20" in content
    assert "3.9 <= total_score < 4.2" in content
    assert "高位置弹性通过条件" in content
    assert "dribull" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_cli.py::test_prompt_dribull_documents_dedicated_contract -q`
Expected: FAIL with missing file or missing content assertions.

- [ ] **Step 3: Write minimal prompt asset**

```md
你是一名 **专业波段交易员**，擅长仅凭 **股票日线图** 做主观交易评估。

你的任务是：

> 根据图表中的 **趋势、位置、量价、历史异动、MACD 趋势状态**，判断该股票当前是否具备 **dribull 偏好的强趋势内部回调修复后再起动潜力**。

...

* `signal_reasoning` 必须明确提到当前周线/日线组合是否符合 `dribull`

...

trend_structure：0.18
price_position：0.18
volume_behavior：0.24
previous_abnormal_move：0.20
macd_phase：0.20

...

高位置弹性通过条件：当 `3.9 <= total_score < 4.2`，且价格位置、历史异动、MACD 与结构质量足够强时，可以从 `WATCH` 提升为 `PASS`。
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_cli.py::test_prompt_dribull_documents_dedicated_contract -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/stock-select/references/prompt-dribull.md tests/test_cli.py
git commit -m "feat: add dedicated dribull review prompt"
```

### Task 3: Update CLI Review Task Expectations For `dribull`

**Files:**
- Modify: `tests/test_cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI routing test**

```python
def test_review_dribull_uses_dedicated_resolver_prompt_and_dribull_artifact_method(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ...
    result = runner.invoke(...)

    assert result.exit_code == 0
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))
    assert tasks["prompt_path"] == prompt_path
    assert tasks["method"] == "dribull"
    assert "dribull" in tasks["tasks"][0]["wave_combo_context"]
```

Rename the existing test from `test_review_dribull_uses_b2_resolver_prompt_and_dribull_artifact_method` to mention the dedicated prompt.

- [ ] **Step 2: Run test to verify it fails only if expectations are stale**

Run: `PYTHONPATH=src pytest tests/test_cli.py::test_review_dribull_uses_dedicated_resolver_prompt_and_dribull_artifact_method -q`
Expected: If only the old test name/assertions exist, update them until this exact test captures the new behavior and fails when the resolver still points at `prompt-b2.md`.

- [ ] **Step 3: Keep implementation minimal**

```python
# No extra CLI code should be necessary if Task 1 is complete.
# Only update test names/assertions so the CLI contract now documents
# that dribull uses its own prompt path while preserving method metadata.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_cli.py::test_review_dribull_uses_dedicated_resolver_prompt_and_dribull_artifact_method -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py
git commit -m "test: align dribull review task prompt expectations"
```

### Task 4: Update `stock-select` Skill Documentation

**Files:**
- Modify: `.agents/skills/stock-select/SKILL.md`
- Modify: `tests/test_cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing skill-doc test**

```python
def test_skill_documents_dribull_dedicated_prompt() -> None:
    content = Path(".agents/skills/stock-select/SKILL.md").read_text(encoding="utf-8")

    assert "`dribull` uses `references/prompt-dribull.md`" in content
    assert "dedicated reviewer" in content
    assert "reuses the existing `b2` reviewer" not in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_cli.py::test_skill_documents_dribull_dedicated_prompt -q`
Expected: FAIL because the skill still references `prompt-b2.md` and old reviewer wording.

- [ ] **Step 3: Write minimal documentation update**

```md
- `b1` uses `references/prompt-b1.md`
- `dribull` uses `references/prompt-dribull.md`
- `hcr` uses `references/prompt.md`
- `b2` uses `references/prompt-b2.md`

...

- `review --method dribull` uses the dedicated `dribull` reviewer and `references/prompt-dribull.md`, while review artifacts keep the method key `dribull`.
```

Update every prompt mapping paragraph in the skill so all sections stay internally consistent.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_cli.py::test_skill_documents_dribull_dedicated_prompt -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/stock-select/SKILL.md tests/test_cli.py
git commit -m "docs: align dribull skill prompt mapping"
```

### Task 5: Run Focused Verification

**Files:**
- Test: `tests/test_review_resolvers.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Run focused resolver and CLI tests**

Run: `PYTHONPATH=src pytest tests/test_review_resolvers.py tests/test_cli.py -k "dribull or prompt_dribull or skill_documents_dribull" -q`
Expected: PASS with zero failures.

- [ ] **Step 2: Run the full touched test files**

Run: `PYTHONPATH=src pytest tests/test_review_resolvers.py tests/test_cli.py -q`
Expected: PASS with zero failures.

- [ ] **Step 3: Review final diff**

Run: `git diff --stat HEAD~4..HEAD`
Expected: Shows resolver, prompt asset, skill doc, and targeted tests only.

- [ ] **Step 4: Commit any final polish if needed**

```bash
git add src/stock_select/review_resolvers.py \
  .agents/skills/stock-select/references/prompt-dribull.md \
  .agents/skills/stock-select/SKILL.md \
  tests/test_review_resolvers.py tests/test_cli.py
git commit -m "chore: finalize dribull review prompt alignment"
```

Only create this commit if Task 1-4 left additional unstaged changes after verification.

## Self-Review

- Spec coverage: resolver routing, new prompt asset, skill doc sync, and tests are all covered by Tasks 1-5.
- Placeholder scan: no `TODO`/`TBD`; all tasks include exact file paths, code snippets, and commands.
- Type consistency: `prompt-dribull.md`, `get_review_resolver("dribull")`, and CLI task `prompt_path` use the same dedicated path naming throughout.
