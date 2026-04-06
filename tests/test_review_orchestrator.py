from stock_select.review_orchestrator import build_review_payload, summarize_reviews


def test_build_review_payload_includes_chart_and_rubric() -> None:
    payload = build_review_payload(
        code="000001.SZ",
        pick_date="2026-04-01",
        chart_path="/tmp/000001_day.html",
        rubric_path="references/review-rubric.md",
    )

    assert payload["code"] == "000001.SZ"
    assert payload["chart_path"] == "/tmp/000001_day.html"
    assert payload["rubric_path"] == "references/review-rubric.md"


def test_summarize_reviews_sorts_recommendations() -> None:
    reviews = [
        {"code": "A", "total_score": 3.0, "verdict": "FAIL"},
        {"code": "B", "total_score": 5.0, "verdict": "PASS"},
    ]

    summary = summarize_reviews("2026-04-01", "b1", reviews, min_score=4.0, failures=[])

    assert summary["recommendations"][0]["code"] == "B"
    assert summary["excluded"][0]["code"] == "A"
