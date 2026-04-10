from __future__ import annotations

import html
import json
import zipfile
from pathlib import Path
from typing import Any


def load_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Summary file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid summary json: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Summary json root must be an object.")
    return payload


def render_summary_html(summary: dict[str, Any], *, names_by_code: dict[str, str] | None = None) -> str:
    recommendations = summary.get("recommendations", [])
    excluded = summary.get("excluded", [])
    failures = summary.get("failures", [])
    if not isinstance(recommendations, list) or not isinstance(excluded, list) or not isinstance(failures, list):
        raise ValueError("Summary json shape is invalid.")
    method_label = str(summary.get("method") or "-").upper()

    metrics = "".join(
        [
            _metric_card("Pick Date", summary.get("pick_date", "-")),
            _metric_card("Method", summary.get("method", "-")),
            _metric_card("Reviewed", summary.get("reviewed_count", 0)),
            _metric_card("PASS", len(recommendations)),
            _metric_card("Excluded", len(excluded)),
            _metric_card("Failures", len(failures)),
        ]
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(method_label)} Summary {_escape(summary.get("pick_date", ""))}</title>
  <style>
    :root {{
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --panel-strong: #fff;
      --text: #182028;
      --muted: #5d6977;
      --line: #d8d2c7;
      --accent: #0f5c4d;
      --accent-soft: #d8ebe6;
      --watch: #b26d12;
      --watch-soft: #f8e5c9;
      --fail: #a63232;
      --fail-soft: #f7d8d8;
      --shadow: 0 12px 30px rgba(24, 32, 40, 0.08);
      --radius: 18px;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      --sans: "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--sans);
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(15,92,77,0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(178,109,18,0.10), transparent 24%),
        linear-gradient(180deg, #f8f5ee 0%, var(--bg) 100%);
    }}
    .page {{
      width: min(1400px, calc(100vw - 32px));
      margin: 24px auto 64px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(15,92,77,0.96), rgba(18,40,58,0.95));
      color: #f9fbfc;
      border-radius: 28px;
      padding: 28px;
      box-shadow: var(--shadow);
    }}
    .hero h1 {{
      margin: 0 0 8px;
      font-size: clamp(28px, 5vw, 44px);
      line-height: 1.05;
    }}
    .hero p {{
      margin: 0;
      color: rgba(249, 251, 252, 0.82);
      max-width: 920px;
      line-height: 1.6;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 14px;
      margin-top: 24px;
    }}
    .metric-card {{
      background: rgba(255,255,255,0.10);
      border: 1px solid rgba(255,255,255,0.15);
      border-radius: 16px;
      padding: 16px;
      backdrop-filter: blur(8px);
    }}
    .metric-label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: rgba(249, 251, 252, 0.68);
    }}
    .metric-value {{
      margin-top: 8px;
      font-size: 28px;
      font-weight: 700;
    }}
    .section {{
      margin-top: 26px;
    }}
    .section-heading {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 12px;
    }}
    .section-heading h2 {{
      margin: 0;
      font-size: 24px;
    }}
    .section-heading p {{
      margin: 0;
      color: var(--muted);
    }}
    .card-list {{
      display: grid;
      gap: 16px;
    }}
    .stock-card {{
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 18px;
      box-shadow: var(--shadow);
    }}
    .stock-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .stock-main {{
      min-width: 0;
    }}
    .stock-code {{
      font-size: 24px;
      font-weight: 700;
      font-family: var(--mono);
    }}
    .stock-name {{
      margin-top: 4px;
      color: var(--muted);
      font-size: 15px;
      font-weight: 600;
    }}
    .stock-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .badge, .pill, .score-chip {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid transparent;
      white-space: nowrap;
    }}
    .badge-pass {{ background: var(--accent-soft); color: var(--accent); }}
    .badge-watch {{ background: var(--watch-soft); color: var(--watch); }}
    .badge-fail {{ background: var(--fail-soft); color: var(--fail); }}
    .badge-neutral {{ background: #e8edf2; color: #465364; }}
    .signal-trend {{ background: #d8ebe6; color: #0f5c4d; }}
    .signal-rebound {{ background: #dfe7f5; color: #355a9b; }}
    .signal-risk {{ background: #f7d8d8; color: #a63232; }}
    .signal-neutral, .pill-muted {{ background: #eef1f4; color: #576372; }}
    .score-chip {{ background: #182028; color: #fff; }}
    .toggle-button {{
      border: 1px solid var(--line);
      background: #fff8ef;
      color: var(--text);
      border-radius: 999px;
      padding: 10px 14px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }}
    .stock-comment {{
      margin: 14px 0 0;
      line-height: 1.7;
      color: #283441;
    }}
    .stock-body {{
      display: grid;
      grid-template-columns: minmax(280px, 420px) 1fr;
      gap: 18px;
      margin-top: 18px;
    }}
    .chart-panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 10px;
    }}
    .chart-panel img {{
      display: block;
      width: 100%;
      height: auto;
      border-radius: 10px;
      background: #faf7f0;
    }}
    .stock-summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }}
    .detail-section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
    }}
    .detail-section h4, .reasoning-block h5 {{
      margin: 0 0 10px;
    }}
    .mini-metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 10px;
    }}
    .mini-metric {{
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px;
    }}
    .mini-metric-label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .mini-metric-value {{
      font-weight: 700;
      font-family: var(--mono);
    }}
    .stock-details {{
      margin-top: 16px;
      display: grid;
      gap: 14px;
    }}
    .reasoning-block p {{
      margin: 0;
      color: #31404f;
      line-height: 1.65;
    }}
    .empty-state {{
      background: var(--panel);
      border: 1px dashed var(--line);
      border-radius: 16px;
      padding: 18px;
      color: var(--muted);
    }}
    @media (max-width: 960px) {{
      .stock-body {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 720px) {{
      .page {{ width: min(100vw - 20px, 1400px); margin-top: 10px; }}
      .hero {{ padding: 20px; border-radius: 22px; }}
      .stock-card {{ padding: 14px; }}
      .stock-header {{
        flex-direction: column;
        align-items: start;
      }}
      .toggle-button {{ width: 100%; justify-content: center; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <h1>{_escape(method_label)} Summary Dashboard</h1>
      <p>Single-file review artifact generated from the merged stock-select summary. This package includes the standalone HTML, summary JSON, and referenced charts for offline inspection.</p>
      <div class="metrics">{metrics}</div>
    </section>
    {_render_section("PASS Recommendations", "Merged final picks after chart-review validation.", recommendations, "No PASS items.", names_by_code or {})}
    {_render_section("Excluded", "Includes WATCH and FAIL after merged scoring.", excluded, "No excluded items.", names_by_code or {})}
  </main>
  <script>
    function toggleDetails(button) {{
      const card = button.closest('.stock-card');
      const details = card.querySelector('.stock-details');
      const hidden = details.hasAttribute('hidden');
      if (hidden) {{
        details.removeAttribute('hidden');
        button.textContent = '收起详情';
      }} else {{
        details.setAttribute('hidden', '');
        button.textContent = '展开详情';
      }}
    }}
  </script>
</body>
</html>
"""


def write_summary_package(
    *,
    summary_path: Path,
    output_dir: Path,
    names_by_code: dict[str, str],
) -> Path:
    summary = load_summary(summary_path)
    html_body = render_summary_html(summary, names_by_code=names_by_code)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / "summary.html"
    copied_summary_path = output_dir / "summary.json"
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    html_path.write_text(html_body, encoding="utf-8")
    copied_summary_path.write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")

    for item in _iter_summary_items(summary):
        chart_path = Path(str(item.get("chart_path") or ""))
        if not chart_path.exists():
            continue
        target_path = charts_dir / chart_path.name
        target_path.write_bytes(chart_path.read_bytes())

    zip_path = output_dir / "summary-package.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(html_path, "summary.html")
        archive.write(copied_summary_path, "summary.json")
        for chart_path in sorted(charts_dir.glob("*.png")):
            archive.write(chart_path, f"charts/{chart_path.name}")
    return zip_path


def _iter_summary_items(summary: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in ("recommendations", "excluded"):
        values = summary.get(key, [])
        if isinstance(values, list):
            items.extend(item for item in values if isinstance(item, dict))
    return items


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _score(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def _badge_class(verdict: str) -> str:
    verdict = verdict.upper()
    return {
        "PASS": "badge-pass",
        "WATCH": "badge-watch",
        "FAIL": "badge-fail",
    }.get(verdict, "badge-neutral")


def _signal_class(signal_type: str) -> str:
    signal_type = str(signal_type)
    return {
        "trend_start": "signal-trend",
        "rebound": "signal-rebound",
        "distribution_risk": "signal-risk",
    }.get(signal_type, "signal-neutral")


def _metric_card(label: str, value: Any) -> str:
    return f"""
    <div class="metric-card">
      <div class="metric-label">{_escape(label)}</div>
      <div class="metric-value">{_escape(value)}</div>
    </div>
    """


def _reasoning_block(title: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f"""
    <div class="reasoning-block">
      <h5>{_escape(title)}</h5>
      <p>{_escape(text)}</p>
    </div>
    """


def _score_grid(review: dict[str, Any] | None, title: str) -> str:
    if not review:
        return ""
    items = [
        ("trend_structure", review.get("trend_structure")),
        ("price_position", review.get("price_position")),
        ("volume_behavior", review.get("volume_behavior")),
        ("previous_abnormal_move", review.get("previous_abnormal_move")),
        ("macd_phase", review.get("macd_phase")),
        ("total_score", review.get("total_score")),
    ]
    body = "".join(
        f"""
        <div class="mini-metric">
          <span class="mini-metric-label">{_escape(label)}</span>
          <span class="mini-metric-value">{_score(value)}</span>
        </div>
        """
        for label, value in items
    )
    return f"""
    <section class="detail-section">
      <h4>{_escape(title)}</h4>
      <div class="mini-metrics">{body}</div>
    </section>
    """


def _detail_card(item: dict[str, Any], names_by_code: dict[str, str]) -> str:
    code = str(item.get("code") or "")
    code_label = _escape(code)
    name = _escape(names_by_code.get(code, ""))
    verdict = str(item.get("verdict", ""))
    signal_type = str(item.get("signal_type", ""))
    chart_path = str(item.get("chart_path", "")).strip()
    final_score = item.get("final_score", item.get("total_score"))
    review_mode = item.get("review_mode", "")
    baseline = item.get("baseline_review") if isinstance(item.get("baseline_review"), dict) else None
    llm_review = item.get("llm_review") if isinstance(item.get("llm_review"), dict) else None
    comment = item.get("comment", "")

    reasoning = ""
    if llm_review:
        reasoning = """
        <section class="detail-section">
          <h4>LLM Reasoning</h4>
          {blocks}
        </section>
        """.format(
            blocks="".join(
                [
                    _reasoning_block("Trend", llm_review.get("trend_reasoning")),
                    _reasoning_block("Position", llm_review.get("position_reasoning")),
                    _reasoning_block("Volume", llm_review.get("volume_reasoning")),
                    _reasoning_block("Abnormal Move", llm_review.get("abnormal_move_reasoning")),
                    _reasoning_block("MACD", llm_review.get("macd_reasoning")),
                    _reasoning_block("Signal", llm_review.get("signal_reasoning")),
                ]
            )
        )

    chart_html = ""
    if chart_path:
        chart_name = Path(chart_path).name
        chart_html = f"""
        <div class="chart-panel">
          <img src="{_escape('charts/' + chart_name)}" alt="{code_label} chart" loading="lazy">
        </div>
        """

    name_html = f'<div class="stock-name">{name}</div>' if name else ""
    return f"""
    <article class="stock-card">
      <div class="stock-header">
        <div class="stock-main">
          <div class="stock-code">{code_label}</div>
          {name_html}
          <div class="stock-meta">
            <span class="badge {_badge_class(verdict)}">{_escape(verdict)}</span>
            <span class="pill {_signal_class(signal_type)}">{_escape(signal_type)}</span>
            <span class="pill pill-muted">{_escape(review_mode)}</span>
            <span class="score-chip">score {_score(final_score)}</span>
          </div>
        </div>
        <button class="toggle-button" type="button" onclick="toggleDetails(this)">展开详情</button>
      </div>
      <p class="stock-comment">{_escape(comment)}</p>
      <div class="stock-body">
        {chart_html}
        <div class="stock-summary-grid">
          {_score_grid(baseline, "Baseline Review")}
          {_score_grid(llm_review, "LLM Review")}
        </div>
      </div>
      <div class="stock-details" hidden>
        {reasoning}
      </div>
    </article>
    """


def _render_section(
    title: str,
    subtitle: str,
    items: list[dict[str, Any]],
    empty_text: str,
    names_by_code: dict[str, str],
) -> str:
    if not items:
        return f"""
        <section class="section">
          <div class="section-heading">
            <h2>{_escape(title)}</h2>
            <p>{_escape(subtitle)}</p>
          </div>
          <div class="empty-state">{_escape(empty_text)}</div>
        </section>
        """
    cards = "".join(_detail_card(item, names_by_code) for item in items)
    return f"""
    <section class="section">
      <div class="section-heading">
        <h2>{_escape(title)}</h2>
        <p>{_escape(subtitle)}</p>
      </div>
      <div class="card-list">
        {cards}
      </div>
    </section>
    """
