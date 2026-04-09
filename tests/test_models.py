from stock_select.models import CandidateRecord, CandidateRun, ReviewRecord


def test_candidate_record_omits_none_fields() -> None:
    record = CandidateRecord(
        code="000001.SZ",
        pick_date="2026-04-01",
        method="b1",
        close=10.0,
        turnover_n=20.0,
        name=None,
    )

    payload = record.to_dict()

    assert payload["code"] == "000001.SZ"
    assert payload["method"] == "b1"
    assert "name" not in payload


def test_candidate_run_serializes_candidates_and_metadata() -> None:
    run = CandidateRun(
        pick_date="2026-04-01",
        method="b1",
        candidates=[
            CandidateRecord(
                code="000001.SZ",
                pick_date="2026-04-01",
                method="b1",
                close=10.0,
                turnover_n=20.0,
            )
        ],
        config={"j_threshold": 20},
        query={"start_date": "2026-03-01"},
    )

    payload = run.to_dict()

    assert payload == {
        "pick_date": "2026-04-01",
        "method": "b1",
        "candidates": [
            {
                "code": "000001.SZ",
                "pick_date": "2026-04-01",
                "method": "b1",
                "close": 10.0,
                "turnover_n": 20.0,
            }
        ],
        "config": {"j_threshold": 20},
        "query": {"start_date": "2026-03-01"},
    }


def test_candidate_run_serializes_hcr_method() -> None:
    run = CandidateRun(
        pick_date="2026-04-01",
        method="hcr",
        candidates=[
            CandidateRecord(
                code="000001.SZ",
                pick_date="2026-04-01",
                method="hcr",
                close=10.0,
                turnover_n=20.0,
            )
        ],
        config={"resonance_tolerance_pct": 0.015},
        query={"start_date": "2025-01-01"},
    )

    payload = run.to_dict()

    assert payload["method"] == "hcr"
    assert payload["candidates"][0]["method"] == "hcr"


def test_review_record_serializes_without_none_fields() -> None:
    review = ReviewRecord(
        code="000001.SZ",
        pick_date="2026-04-01",
        decision="PASS",
        signal_type="trend_start",
        comment="周线趋势向上，量价配合健康，前期有异动蓄势，当前位置仍有空间。",
        score=4.2,
        failure_reason=None,
    )

    payload = review.to_dict()

    assert payload["decision"] == "PASS"
    assert payload["signal_type"] == "trend_start"
    assert "failure_reason" not in payload
