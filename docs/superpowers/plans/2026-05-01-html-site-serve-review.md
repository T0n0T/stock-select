# Review HTML 站点与 Serve 子命令 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前 `render-html` 拆成 `stock-select html render|zip|serve` 三个子命令，生成可浏览的多天 review HTML 站点，并保留 `render-html` 兼容入口。

**Architecture:** 保持 CLI 薄层，在 `src/stock_select/cli.py` 中新增 `html_app = typer.Typer(...)` 并把参数校验、数据库名称查询、静态服务接线放在 CLI 层。将 HTML 构建、索引渲染、站点目录同步、ZIP 打包等展示逻辑集中到 `src/stock_select/html_export.py`，由 `html render` 负责生成 `runtime/reviews/site/`，`html zip` 负责打包单日报告目录，`html serve` 负责暴露整个站点根目录。

**Tech Stack:** Python, Typer CLI, stdlib `http.server`, `json`, `zipfile`, pytest, typer.testing

---

## File Structure

- Modify: `src/stock_select/html_export.py`
  - 保留 `load_summary(...)`
  - 拆出单日报告渲染、多天索引渲染、站点目录同步、ZIP 打包 helper
- Modify: `src/stock_select/cli.py`
  - 新增 `html_app`
  - 新增 `_html_render_impl(...)`、`_html_zip_impl(...)`、`_html_serve_impl(...)`
  - 增加 `app.add_typer(html_app, name="html")`
  - 保留 `render-html` 兼容入口并转调新 helper
- Modify: `tests/test_cli.py`
  - 覆盖 `html render|zip|serve`
  - 覆盖 `render-html` 兼容层
  - 覆盖新 HTML 输出包含 verdict / score 导航与多天首页
- Modify: `README.md`
  - 用新命令结构替换 `render-html` 的首选用法
- Modify: `.agents/skills/stock-select/SKILL.md`
  - 将 HTML 工作流改成 `html render`、`html zip`、`html serve`

不新建模块。首轮实现保持在现有 `cli.py` / `html_export.py` 中，避免无必要重构。

### Task 1: 建立 `html` 子命令骨架和 CLI 合约测试

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: 写 `html` 子命令存在性的失败测试**

在 `tests/test_cli.py` 的 CLI 合约测试区域加入：

```python
def test_html_group_exposes_render_zip_and_serve(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    called: list[tuple[str, Path]] = []

    monkeypatch.setattr(cli, "_html_render_impl", lambda **kwargs: called.append(("render", kwargs["runtime_root"])) or (tmp_path / "report.html"))
    monkeypatch.setattr(cli, "_html_zip_impl", lambda **kwargs: called.append(("zip", kwargs["runtime_root"])) or (tmp_path / "summary-package.zip"))
    monkeypatch.setattr(cli, "_html_serve_impl", lambda **kwargs: called.append(("serve", kwargs["runtime_root"])) or "http://127.0.0.1:8000/")

    render_result = runner.invoke(
        app,
        ["html", "render", "--method", "b1", "--pick-date", "2026-04-01", "--runtime-root", str(tmp_path), "--dsn", "postgresql://example"],
    )
    zip_result = runner.invoke(
        app,
        ["html", "zip", "--method", "b1", "--pick-date", "2026-04-01", "--runtime-root", str(tmp_path)],
    )
    serve_result = runner.invoke(
        app,
        ["html", "serve", "--runtime-root", str(tmp_path), "--host", "127.0.0.1", "--port", "8000"],
    )

    assert render_result.exit_code == 0
    assert zip_result.exit_code == 0
    assert serve_result.exit_code == 0
    assert [name for name, _root in called] == ["render", "zip", "serve"]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_cli.py::test_html_group_exposes_render_zip_and_serve -v
```

Expected: FAIL because `html` command group does not exist yet.

- [ ] **Step 3: 写 `html` 子命令最小骨架**

在 `src/stock_select/cli.py` 顶部 `app = typer.Typer(...)` 下方加入：

```python
app = typer.Typer(help="stock-select standalone CLI")
html_app = typer.Typer(help="HTML site utilities")
app.add_typer(html_app, name="html")
```

在 `_render_html_impl(...)` 附近先加入 3 个 stub：

```python
def _html_render_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    raise NotImplementedError("html render is not implemented yet")


def _html_zip_impl(
    *,
    method: str,
    pick_date: str,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    raise NotImplementedError("html zip is not implemented yet")


def _html_serve_impl(
    *,
    runtime_root: Path,
    host: str,
    port: int,
    reporter: ProgressReporter | None = None,
) -> str:
    raise NotImplementedError("html serve is not implemented yet")
```

并加入命令接线：

```python
@html_app.command("render")
def html_render(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_review_method(method)
    reporter = ProgressReporter(enabled=progress)
    output_path = _html_render_impl(
        method=normalized_method,
        pick_date=pick_date,
        dsn=dsn,
        runtime_root=runtime_root,
        reporter=reporter,
    )
    typer.echo(str(output_path))
```

```python
@html_app.command("zip")
def html_zip(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_review_method(method)
    reporter = ProgressReporter(enabled=progress)
    zip_path = _html_zip_impl(
        method=normalized_method,
        pick_date=pick_date,
        runtime_root=runtime_root,
        reporter=reporter,
    )
    typer.echo(str(zip_path))
```

```python
@html_app.command("serve")
def html_serve(
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    reporter = ProgressReporter(enabled=progress)
    base_url = _html_serve_impl(runtime_root=runtime_root, host=host, port=port, reporter=reporter)
    typer.echo(base_url)
```

- [ ] **Step 4: 重新运行测试确认通过**

Run:

```bash
uv run pytest tests/test_cli.py::test_html_group_exposes_render_zip_and_serve -v
```

Expected: PASS because the commands now exist and delegate to monkeypatched helpers.

- [ ] **Step 5: 提交 CLI 骨架**

Run:

```bash
git add tests/test_cli.py src/stock_select/cli.py
git commit -m "test: add html subcommand scaffold"
```

### Task 2: 先用测试锁定单日报告的新导航与站点目录布局

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/html_export.py`

- [ ] **Step 1: 写单日报告包含 verdict 与 score 导航的失败测试**

在 `tests/test_cli.py` 现有 `render-html` HTML 断言附近新增：

```python
def test_html_render_writes_site_report_with_verdict_and_score_navigation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / _eod_key("2026-04-01", "b1")
    chart_dir = runtime_root / "charts" / _eod_key("2026-04-01", "b1")
    review_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png-bytes")
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "reviewed_count": 2,
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "chart_path": str(chart_dir / "000001.SZ_day.png"),
                        "review_mode": "merged",
                        "baseline_review": {"trend_structure": 5, "price_position": 4, "volume_behavior": 5, "previous_abnormal_move": 4, "macd_phase": 5, "total_score": 4.6, "signal_type": "trend_start", "verdict": "PASS", "comment": "baseline"},
                        "llm_review": None,
                        "final_score": 4.6,
                        "signal_type": "trend_start",
                        "verdict": "PASS",
                        "comment": "pass comment",
                    }
                ],
                "excluded": [
                    {
                        "code": "000002.SZ",
                        "chart_path": str(chart_dir / "000001.SZ_day.png"),
                        "review_mode": "merged",
                        "baseline_review": {"trend_structure": 3, "price_position": 3, "volume_behavior": 3, "previous_abnormal_move": 3, "macd_phase": 3, "total_score": 3.4, "signal_type": "rebound", "verdict": "WATCH", "comment": "baseline"},
                        "llm_review": None,
                        "final_score": 3.4,
                        "signal_type": "rebound",
                        "verdict": "WATCH",
                        "comment": "watch comment",
                    }
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_connect", lambda dsn: object())
    monkeypatch.setattr(cli, "fetch_instrument_names", lambda connection, symbols: {"000001.SZ": "平安银行", "000002.SZ": "万科A"})

    result = runner.invoke(
        app,
        ["html", "render", "--method", "b1", "--pick-date", "2026-04-01", "--runtime-root", str(runtime_root), "--dsn", "postgresql://example"],
    )

    assert result.exit_code == 0
    report_path = Path(result.stdout.strip())
    assert report_path == runtime_root / "reviews" / "site" / "2026-04-01.b1" / "index.html"
    html_text = report_path.read_text(encoding="utf-8")
    assert "PASS" in html_text
    assert "WATCH" in html_text
    assert "FAIL" in html_text
    assert "&gt;= 4.5" in html_text or ">= 4.5" in html_text
    assert "4.0 - 4.49" in html_text
    assert "3.0 - 3.99" in html_text
    assert "score-bucket" in html_text
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_cli.py::test_html_render_writes_site_report_with_verdict_and_score_navigation -v
```

Expected: FAIL because `_html_render_impl(...)` is still unimplemented and no site report exists.

- [ ] **Step 3: 给 `html_export.py` 增加站点目录常量和最小 helper**

在 `src/stock_select/html_export.py` 顶部 imports 下加入：

```python
SCORE_BUCKETS: tuple[tuple[str, float | None, float | None], ...] = (
    (">= 4.5", 4.5, None),
    ("4.0 - 4.49", 4.0, 4.5),
    ("3.0 - 3.99", 3.0, 4.0),
    ("< 3.0", None, 3.0),
)
```

并加入这些 helper：

```python
def site_root_dir(runtime_root: Path) -> Path:
    return runtime_root / "reviews" / "site"


def site_report_dir(runtime_root: Path, *, pick_date: str, method: str) -> Path:
    return site_root_dir(runtime_root) / f"{pick_date}.{method}"


def resolve_item_score(item: dict[str, Any]) -> float | None:
    for key in ("final_score", "total_score"):
        value = item.get(key)
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def score_bucket_label(score: float | None) -> str | None:
    if score is None:
        return None
    for label, lower, upper in SCORE_BUCKETS:
        lower_ok = lower is None or score >= lower
        upper_ok = upper is None or score < upper
        if lower_ok and upper_ok:
            return label
    return None
```

- [ ] **Step 4: 实现最小的站点同步入口**

在 `src/stock_select/html_export.py` 中新增：

```python
def write_summary_site(
    *,
    summary_path: Path,
    runtime_root: Path,
    names_by_code: dict[str, str],
) -> Path:
    summary = load_summary(summary_path)
    pick_date = str(summary.get("pick_date") or "")
    method = str(summary.get("method") or "")
    report_dir = site_report_dir(runtime_root, pick_date=pick_date, method=method)
    report_dir.mkdir(parents=True, exist_ok=True)
    html_path = report_dir / "index.html"
    copied_summary_path = report_dir / "summary.json"
    charts_dir = report_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    html_path.write_text(render_summary_html(summary, names_by_code=names_by_code), encoding="utf-8")
    copied_summary_path.write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")
    for item in _iter_summary_items(summary):
        chart_path = Path(str(item.get("chart_path") or ""))
        if chart_path.exists():
            (charts_dir / chart_path.name).write_bytes(chart_path.read_bytes())
    return html_path
```

然后把 `render_summary_html(...)` 的头部结构改成显式 verdict / score 导航，最小满足测试：

```python
verdict_nav = """
<nav class="section-nav">
  <a href="#verdict-pass">PASS</a>
  <a href="#verdict-watch">WATCH</a>
  <a href="#verdict-fail">FAIL</a>
</nav>
"""
score_nav = """
<nav class="score-nav">
  <a class="score-bucket" href="#score-ge-45">&gt;= 4.5</a>
  <a class="score-bucket" href="#score-ge-40">&gt;4.0 - 4.49</a>
  <a class="score-bucket" href="#score-ge-30">&gt;3.0 - 3.99</a>
  <a class="score-bucket" href="#score-lt-30">&lt; 3.0</a>
</nav>
"""
```

把这两个片段放进 hero 后面即可。此步只求让测试通过，后续再把页面结构做完整。

- [ ] **Step 5: 在 CLI 中最小接入 `_html_render_impl(...)`**

将 `src/stock_select/cli.py` 的 `_html_render_impl(...)` 实现为：

```python
def _html_render_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    review_dir = _review_dir_path(runtime_root, pick_date, method)
    summary_path = review_dir / "summary.json"
    if not summary_path.exists():
        raise typer.BadParameter(f"Summary file not found: {summary_path}")

    resolved_dsn = _resolve_cli_dsn(dsn)
    if reporter:
        reporter.emit("html-render", "connect db")
    connection = _connect(resolved_dsn)
    summary_payload = _load_summary_payload(summary_path)
    codes = sorted(
        {
            str(item.get("code") or "").strip()
            for key in ("recommendations", "excluded")
            for item in summary_payload.get(key, [])
            if isinstance(item, dict) and str(item.get("code") or "").strip()
        }
    )
    names_by_code = fetch_instrument_names(connection, symbols=codes)
    html_path = write_summary_site(summary_path=summary_path, runtime_root=runtime_root, names_by_code=names_by_code)
    return html_path
```

同时把 import 从：

```python
from stock_select.html_export import write_summary_package
```

改成：

```python
from stock_select.html_export import write_summary_package, write_summary_site
```

- [ ] **Step 6: 重新运行测试确认通过**

Run:

```bash
uv run pytest tests/test_cli.py::test_html_render_writes_site_report_with_verdict_and_score_navigation -v
```

Expected: PASS and `runtime/reviews/site/2026-04-01.b1/index.html` exists.

- [ ] **Step 7: 提交站点渲染最小版本**

Run:

```bash
git add tests/test_cli.py src/stock_select/html_export.py src/stock_select/cli.py
git commit -m "feat: add html site render output"
```

### Task 3: 补全多天首页与 verdict/score 分组视图

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/html_export.py`
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: 写多天首页与单日报告分组的失败测试**

在 `tests/test_cli.py` 中新增：

```python
def test_html_render_rebuilds_site_index_for_multiple_review_days(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    chart_dir = runtime_root / "charts" / _eod_key("2026-04-02", "b2")
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png-bytes")

    for pick_date, method, verdict, score in [
        ("2026-04-01", "b1", "PASS", 4.6),
        ("2026-04-02", "b2", "FAIL", 2.8),
    ]:
        review_dir = runtime_root / "reviews" / _eod_key(pick_date, method)
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / "summary.json").write_text(
            json.dumps(
                {
                    "pick_date": pick_date,
                    "method": method,
                    "reviewed_count": 1,
                    "recommendations": [] if verdict != "PASS" else [{"code": "000001.SZ", "chart_path": str(chart_dir / "000001.SZ_day.png"), "review_mode": "merged", "baseline_review": None, "llm_review": None, "final_score": score, "verdict": verdict, "signal_type": "trend_start", "comment": verdict.lower()}],
                    "excluded": [] if verdict == "PASS" else [{"code": "000001.SZ", "chart_path": str(chart_dir / "000001.SZ_day.png"), "review_mode": "merged", "baseline_review": None, "llm_review": None, "final_score": score, "verdict": verdict, "signal_type": "trend_start", "comment": verdict.lower()}],
                    "failures": [],
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(cli, "_connect", lambda dsn: object())
    monkeypatch.setattr(cli, "fetch_instrument_names", lambda connection, symbols: {"000001.SZ": "平安银行"})

    first = runner.invoke(app, ["html", "render", "--method", "b1", "--pick-date", "2026-04-01", "--runtime-root", str(runtime_root), "--dsn", "postgresql://example"])
    second = runner.invoke(app, ["html", "render", "--method", "b2", "--pick-date", "2026-04-02", "--runtime-root", str(runtime_root), "--dsn", "postgresql://example"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    index_path = runtime_root / "reviews" / "site" / "index.html"
    assert index_path.exists()
    html_text = index_path.read_text(encoding="utf-8")
    assert "2026-04-02" in html_text
    assert "2026-04-01" in html_text
    assert html_text.index("2026-04-02") < html_text.index("2026-04-01")
    assert "PASS" in html_text
    assert "FAIL" in html_text
    assert "2026-04-02.b2/index.html" in html_text
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_cli.py::test_html_render_rebuilds_site_index_for_multiple_review_days -v
```

Expected: FAIL because `write_summary_site(...)` does not rebuild the shared index yet.

- [ ] **Step 3: 在 `html_export.py` 中加入视图分组 helper**

加入：

```python
def group_items_by_verdict(summary: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped = {"PASS": [], "WATCH": [], "FAIL": []}
    for item in _iter_summary_items(summary):
        verdict = str(item.get("verdict") or "").upper()
        grouped.setdefault(verdict, [])
        grouped[verdict].append(item)
    for key in grouped:
        grouped[key] = sorted(grouped[key], key=lambda value: resolve_item_score(value) or -1.0, reverse=True)
    return grouped


def bucket_counts(summary: dict[str, Any]) -> dict[str, int]:
    counts = {label: 0 for label, _lower, _upper in SCORE_BUCKETS}
    for item in _iter_summary_items(summary):
        label = score_bucket_label(resolve_item_score(item))
        if label:
            counts[label] += 1
    return counts
```

把 `render_summary_html(...)` 的主体改成使用：

```python
grouped = group_items_by_verdict(summary)
score_counts = bucket_counts(summary)
```

并渲染 3 个 verdict section：

```python
{_render_section("PASS", "Merged PASS results.", grouped.get("PASS", []), "No PASS items.", names_by_code or {}, section_id="verdict-pass")}
{_render_section("WATCH", "WATCH results after merged scoring.", grouped.get("WATCH", []), "No WATCH items.", names_by_code or {}, section_id="verdict-watch")}
{_render_section("FAIL", "FAIL results after merged scoring.", grouped.get("FAIL", []), "No FAIL items.", names_by_code or {}, section_id="verdict-fail")}
```

把 `_render_section(...)` 签名改成：

```python
def _render_section(
    title: str,
    subtitle: str,
    items: list[dict[str, Any]],
    empty_text: str,
    names_by_code: dict[str, str],
    *,
    section_id: str,
) -> str:
```

并给最外层 `<section>` 加上 `id="{_escape(section_id)}"`。

- [ ] **Step 4: 实现多天首页重建**

在 `src/stock_select/html_export.py` 中加入：

```python
def render_site_index(entries: list[dict[str, Any]]) -> str:
    cards = "".join(
        f"""
        <article class="site-card">
          <h2><a href="{_escape(entry['slug'] + '/index.html')}">{_escape(entry['pick_date'])} · {_escape(entry['method'].upper())}</a></h2>
          <p>reviewed={_escape(entry['reviewed_count'])} PASS={_escape(entry['pass_count'])} WATCH={_escape(entry['watch_count'])} FAIL={_escape(entry['fail_count'])}</p>
          <p>score range {_escape(entry['min_score'])} - {_escape(entry['max_score'])}</p>
        </article>
        """
        for entry in entries
    )
    return f\"\"\"<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Review Site Index</title></head>
<body>
  <main>
    <h1>Review Site Index</h1>
    {cards}
  </main>
</body>
</html>
\"\"\"


def rebuild_site_index(runtime_root: Path) -> Path:
    root = site_root_dir(runtime_root)
    root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for summary_copy in sorted(root.glob("*/summary.json"), reverse=True):
        summary = load_summary(summary_copy)
        slug = summary_copy.parent.name
        scores = [resolve_item_score(item) for item in _iter_summary_items(summary)]
        numeric_scores = [score for score in scores if score is not None]
        grouped = group_items_by_verdict(summary)
        entries.append(
            {
                "slug": slug,
                "pick_date": str(summary.get("pick_date") or ""),
                "method": str(summary.get("method") or ""),
                "reviewed_count": int(summary.get("reviewed_count") or 0),
                "pass_count": len(grouped.get("PASS", [])),
                "watch_count": len(grouped.get("WATCH", [])),
                "fail_count": len(grouped.get("FAIL", [])),
                "min_score": "-" if not numeric_scores else f"{min(numeric_scores):.2f}",
                "max_score": "-" if not numeric_scores else f"{max(numeric_scores):.2f}",
            }
        )
    entries.sort(key=lambda item: (item["pick_date"], item["method"]), reverse=True)
    index_path = root / "index.html"
    index_path.write_text(render_site_index(entries), encoding="utf-8")
    return index_path
```

并在 `write_summary_site(...)` 的末尾调用：

```python
rebuild_site_index(runtime_root)
```

- [ ] **Step 5: 重新运行测试确认通过**

Run:

```bash
uv run pytest tests/test_cli.py::test_html_render_rebuilds_site_index_for_multiple_review_days -v
```

Expected: PASS and `runtime/reviews/site/index.html` links to both daily reports in reverse date order.

- [ ] **Step 6: 提交索引与分组视图**

Run:

```bash
git add tests/test_cli.py src/stock_select/html_export.py src/stock_select/cli.py
git commit -m "feat: add review html site index"
```

### Task 4: 拆出 `html zip` 与 `render-html` 兼容层

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`
- Modify: `src/stock_select/html_export.py`

- [ ] **Step 1: 写 `html zip` 与 `render-html` 兼容层的失败测试**

在 `tests/test_cli.py` 中新增：

```python
def test_html_zip_packages_existing_site_report(tmp_path: Path) -> None:
    runner = CliRunner()
    report_dir = tmp_path / "runtime" / "reviews" / "site" / "2026-04-01.b1"
    charts_dir = report_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "index.html").write_text("<html><body>report</body></html>", encoding="utf-8")
    (report_dir / "summary.json").write_text("{}", encoding="utf-8")
    (charts_dir / "000001.SZ_day.png").write_bytes(b"png-bytes")

    result = runner.invoke(
        app,
        ["html", "zip", "--method", "b1", "--pick-date", "2026-04-01", "--runtime-root", str(tmp_path / "runtime")],
    )

    assert result.exit_code == 0
    zip_path = Path(result.stdout.strip())
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        assert "index.html" in names
        assert "summary.json" in names
        assert "charts/000001.SZ_day.png" in names
```

```python
def test_render_html_remains_compatible_and_prints_deprecation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli, "_html_render_impl", lambda **kwargs: tmp_path / "runtime" / "reviews" / "site" / "2026-04-01.b1" / "index.html")
    monkeypatch.setattr(cli, "_html_zip_impl", lambda **kwargs: tmp_path / "runtime" / "reviews" / "site" / "2026-04-01.b1" / "summary-package.zip")

    result = runner.invoke(
        app,
        ["render-html", "--method", "b1", "--pick-date", "2026-04-01", "--runtime-root", str(tmp_path / "runtime"), "--dsn", "postgresql://example"],
    )

    assert result.exit_code == 0
    assert "deprecated" in result.stderr.lower()
    assert str(tmp_path / "runtime" / "reviews" / "site" / "2026-04-01.b1" / "summary-package.zip") in result.stdout
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest \
  tests/test_cli.py::test_html_zip_packages_existing_site_report \
  tests/test_cli.py::test_render_html_remains_compatible_and_prints_deprecation -v
```

Expected: FAIL because `_html_zip_impl(...)` and the compatibility wrapper are not implemented yet.

- [ ] **Step 3: 实现目录打包 helper**

在 `src/stock_select/html_export.py` 中加入：

```python
def zip_site_report(report_dir: Path) -> Path:
    if not report_dir.exists():
        raise ValueError(f"HTML report directory not found: {report_dir}")
    zip_path = report_dir / "summary-package.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(report_dir / "index.html", "index.html")
        archive.write(report_dir / "summary.json", "summary.json")
        for chart_path in sorted((report_dir / "charts").glob("*.png")):
            archive.write(chart_path, f"charts/{chart_path.name}")
    return zip_path
```

保留 `write_summary_package(...)`，但改成复用新 helper：

```python
def write_summary_package(
    *,
    summary_path: Path,
    output_dir: Path,
    names_by_code: dict[str, str],
) -> Path:
    runtime_root = output_dir.parents[2]
    html_path = write_summary_site(summary_path=summary_path, runtime_root=runtime_root, names_by_code=names_by_code)
    report_dir = html_path.parent
    return zip_site_report(report_dir)
```

- [ ] **Step 4: 实现 `_html_zip_impl(...)` 和 `render-html` 兼容层**

在 `src/stock_select/cli.py` 中把 `_html_zip_impl(...)` 实现为：

```python
def _html_zip_impl(
    *,
    method: str,
    pick_date: str,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    report_dir = site_report_dir(runtime_root, pick_date=pick_date, method=method)
    if not report_dir.exists():
        raise typer.BadParameter(f"HTML report directory not found: {report_dir}. Run `stock-select html render` first.")
    zip_path = zip_site_report(report_dir)
    if reporter:
        reporter.emit("html-zip", f"write package={zip_path}")
    return zip_path
```

把 imports 改成：

```python
from stock_select.html_export import site_report_dir, write_summary_package, write_summary_site, zip_site_report
```

把旧 `_render_html_impl(...)` 改成兼容包装：

```python
def _render_html_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    html_path = _html_render_impl(
        method=method,
        pick_date=pick_date,
        dsn=dsn,
        runtime_root=runtime_root,
        reporter=reporter,
    )
    zip_path = _html_zip_impl(method=method, pick_date=pick_date, runtime_root=runtime_root, reporter=reporter)
    return zip_path
```

把旧命令 `render_html(...)` 改成：

```python
@app.command(name="render-html")
def render_html(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_review_method(method)
    reporter = ProgressReporter(enabled=progress)
    typer.echo("`render-html` is deprecated; use `stock-select html render` and `stock-select html zip`.", err=True)
    zip_path = _render_html_impl(
        method=normalized_method,
        pick_date=pick_date,
        dsn=dsn,
        runtime_root=runtime_root,
        reporter=reporter,
    )
    typer.echo(str(zip_path))
```

- [ ] **Step 5: 重新运行测试确认通过**

Run:

```bash
uv run pytest \
  tests/test_cli.py::test_html_zip_packages_existing_site_report \
  tests/test_cli.py::test_render_html_remains_compatible_and_prints_deprecation -v
```

Expected: PASS and the zip contains `index.html`, `summary.json`, and `charts/*.png`.

- [ ] **Step 6: 提交 zip 拆分与兼容层**

Run:

```bash
git add tests/test_cli.py src/stock_select/cli.py src/stock_select/html_export.py
git commit -m "feat: split html zip from render-html"
```

### Task 5: 实现 `html serve`、错误路径和文档更新

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`
- Modify: `README.md`
- Modify: `.agents/skills/stock-select/SKILL.md`

- [ ] **Step 1: 写 `html serve` 错误路径和成功接线的失败测试**

在 `tests/test_cli.py` 中新增：

```python
def test_html_serve_requires_existing_site_root(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["html", "serve", "--runtime-root", str(tmp_path / "runtime"), "--host", "127.0.0.1", "--port", "8000"],
    )

    assert result.exit_code != 0
    assert "html site root not found" in result.stderr.lower()
```

```python
def test_html_serve_prints_base_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    site_root = tmp_path / "runtime" / "reviews" / "site"
    site_root.mkdir(parents=True, exist_ok=True)
    (site_root / "index.html").write_text("<html></html>", encoding="utf-8")

    captured: dict[str, object] = {}

    class FakeServer:
        def serve_forever(self) -> None:
            captured["served"] = True

    def fake_make_server(*, directory: Path, host: str, port: int):
        captured["directory"] = directory
        captured["host"] = host
        captured["port"] = port
        return FakeServer()

    monkeypatch.setattr(cli, "_make_html_http_server", fake_make_server)

    result = runner.invoke(
        app,
        ["html", "serve", "--runtime-root", str(tmp_path / "runtime"), "--host", "127.0.0.1", "--port", "8000"],
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "http://127.0.0.1:8000/"
    assert captured["directory"] == site_root
    assert captured["served"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest \
  tests/test_cli.py::test_html_serve_requires_existing_site_root \
  tests/test_cli.py::test_html_serve_prints_base_url -v
```

Expected: FAIL because `_html_serve_impl(...)` and `_make_html_http_server(...)` do not exist yet.

- [ ] **Step 3: 实现 `html serve` helper**

在 `src/stock_select/cli.py` 中加入：

```python
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
```

新增：

```python
def _make_html_http_server(*, directory: Path, host: str, port: int) -> ThreadingHTTPServer:
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    return ThreadingHTTPServer((host, port), handler)
```

```python
def _html_serve_impl(
    *,
    runtime_root: Path,
    host: str,
    port: int,
    reporter: ProgressReporter | None = None,
) -> str:
    root = site_root_dir(runtime_root)
    index_path = root / "index.html"
    if not root.exists() or not index_path.exists():
        raise typer.BadParameter(f"HTML site root not found: {root}. Run `stock-select html render` first.")
    if reporter:
        reporter.emit("html-serve", f"serve root={root}")
    server = _make_html_http_server(directory=root, host=host, port=port)
    base_url = f"http://{host}:{port}/"
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return base_url
```

然后把 `html_serve(...)` 命令体改成先拿到 URL 再输出：

```python
base_url = _html_serve_impl(runtime_root=runtime_root, host=host, port=port, reporter=reporter)
typer.echo(base_url)
```

如果测试表明 `serve_forever()` 阻塞导致 stdout 无法输出，则调整 `_html_serve_impl(...)` 返回 `(server, base_url)`，再在命令体中先 `typer.echo(base_url)` 后 `server.serve_forever()`。实现时以测试通过为准，但不要改变错误消息文本。

- [ ] **Step 4: 更新 README 和 skill**

在 `README.md` 中把所有 `render-html` 的首选用法改成：

```text
- `html render`
  - 读取 `reviews/<pick_date>.<method>/summary.json`
  - 生成 `runtime/reviews/site/<pick_date>.<method>/index.html`
  - 重建 `runtime/reviews/site/index.html`
- `html zip`
  - 打包已渲染的 `site/<pick_date>.<method>/`
- `html serve`
  - 暴露整个 `runtime/reviews/site/` 为本地静态站点
- `render-html`
  - 兼容入口；内部转调 `html render` + `html zip`
```

在 `.agents/skills/stock-select/SKILL.md` 中把这些旧描述：

```text
- When the caller needs a shareable offline report, run CLI `render-html` after `review-merge`.
- `render-html` must look up stock names from PostgreSQL and render `code + name` in the HTML, not only the code.
- The packaged export should be a zip containing `summary.html`, `summary.json`, and the referenced chart PNG files under `charts/`.
```

改成：

```text
- When the caller needs a shareable HTML report after `review-merge`, run `stock-select html render`.
- `stock-select html render` must look up stock names from PostgreSQL `instruments`, render `code + name`, generate `runtime/reviews/site/<pick_date>.<method>/index.html`, and rebuild `runtime/reviews/site/index.html`.
- When the caller needs an offline package, run `stock-select html zip` after `stock-select html render`.
- `stock-select html zip` packages `index.html`, `summary.json`, and referenced chart PNG files under `charts/`.
- When the caller wants browser access to the full review site, run `stock-select html serve`.
- `render-html` is a compatibility entrypoint only and should not be the preferred workflow.
```

同时把执行顺序里原来的：

```text
10. If the caller asks for packaged HTML output, run CLI `render-html` after `review-merge`.
```

改成：

```text
10. If the caller asks for HTML output, run `stock-select html render` after `review-merge`.
11. If the caller asks for an offline package, run `stock-select html zip` after `stock-select html render`.
12. If the caller asks for browser access to the full review site, run `stock-select html serve`.
```

- [ ] **Step 5: 运行目标测试与文档相关回归**

Run:

```bash
uv run pytest \
  tests/test_cli.py::test_html_serve_requires_existing_site_root \
  tests/test_cli.py::test_html_serve_prints_base_url \
  tests/test_cli.py::test_html_group_exposes_render_zip_and_serve \
  tests/test_cli.py::test_html_render_writes_site_report_with_verdict_and_score_navigation \
  tests/test_cli.py::test_html_render_rebuilds_site_index_for_multiple_review_days \
  tests/test_cli.py::test_html_zip_packages_existing_site_report \
  tests/test_cli.py::test_render_html_remains_compatible_and_prints_deprecation -v
```

Expected: PASS.

- [ ] **Step 6: 运行完整相关回归**

Run:

```bash
uv run pytest tests/test_cli.py -k "html or render_html" -v
```

Expected: PASS for all HTML-related CLI coverage.

- [ ] **Step 7: 提交 serve 与文档更新**

Run:

```bash
git add tests/test_cli.py src/stock_select/cli.py README.md .agents/skills/stock-select/SKILL.md
git commit -m "feat: add review html serve workflow"
```

## Self-Review

- Spec coverage: 本计划覆盖了 `html render`、`html zip`、`html serve`、多天首页、单日报告导航、`render-html` 兼容层、README 更新、skill 更新。无遗漏项。
- Placeholder scan: 计划中没有 `TODO`、`TBD`、或“自行处理”式空泛步骤。所有任务都给出具体文件、代码片段和测试命令。
- Type consistency:
  - CLI helper 名称统一为 `_html_render_impl(...)`、`_html_zip_impl(...)`、`_html_serve_impl(...)`
  - 站点目录 helper 统一为 `site_root_dir(...)`、`site_report_dir(...)`
  - ZIP helper 统一为 `zip_site_report(...)`
  - 多天首页 helper 统一为 `rebuild_site_index(...)`

