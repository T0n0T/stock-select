"""原始模型分数的入场分档；不改变排名，也不把分数解释为概率。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from math import isfinite
from typing import Any, Mapping

from .signal_bundle import SignalBundle


@dataclass(frozen=True)
class ScoreEntryDecision:
    action: str
    reason: str


@dataclass(frozen=True)
class ScoreEntryGate:
    open_min_score: float
    discard_below_score: float
    top_n: int
    blocked_environments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        scores = (self.open_min_score, self.discard_below_score)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not isfinite(value) for value in scores):
            raise ValueError("score thresholds must be finite numbers")
        if self.discard_below_score > self.open_min_score:
            raise ValueError("discard threshold must not exceed open threshold")
        if type(self.top_n) is not int or self.top_n <= 0:
            raise ValueError("top_n must be a positive integer")
        if any(env not in {"weak", "neutral", "strong"} for env in self.blocked_environments):
            raise ValueError("unknown blocked environment")

    def decide(self, raw_score: float | None, rank: int | None,
               environment: str | None) -> ScoreEntryDecision:
        if raw_score is None or not isfinite(raw_score):
            return ScoreEntryDecision("observe", "missing_raw_score")
        if raw_score < self.discard_below_score:
            return ScoreEntryDecision("discard", "below_discard_score")
        if environment not in {"weak", "neutral", "strong"}:
            return ScoreEntryDecision("observe", "missing_environment")
        if environment in self.blocked_environments:
            return ScoreEntryDecision("observe", "blocked_environment")
        if rank is None or rank <= 0:
            return ScoreEntryDecision("observe", "missing_rank")
        if rank > self.top_n:
            return ScoreEntryDecision("observe", "outside_top_n")
        if raw_score < self.open_min_score:
            return ScoreEntryDecision("observe", "below_open_score")
        return ScoreEntryDecision("open", "score_and_environment_pass")

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "blocked_environments": list(self.blocked_environments)}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ScoreEntryGate:
        if not isinstance(raw, dict) or raw.keys() - {
            "open_min_score", "discard_below_score", "top_n", "blocked_environments"
        }:
            raise ValueError("unknown score entry gate fields")
        values = dict(raw)
        blocked = values.get("blocked_environments", [])
        if not isinstance(blocked, (list, tuple)):
            raise ValueError("blocked_environments must be a list")
        values["blocked_environments"] = tuple(blocked)
        try:
            return cls(**values)
        except TypeError as exc:
            raise ValueError("incomplete score entry gate") from exc


def filter_score_signals(signals: SignalBundle, gate: ScoreEntryGate,
                         environments: Mapping[str, str]) -> SignalBundle:
    """保留信号日时间轴；不补选原排名之外的股票。输入必须为原始模型分数。"""
    return SignalBundle({day: tuple(row for row in signals.rows_for_date(day)
                                    if gate.decide(row.model_score, row.model_rank,
                                                   environments.get(day)).action == "open")
                         for day in signals.dates})


def validate_bound_score_policy(raw: Any, actual_model_sha256: str,
                                expected_method: str | None = None) -> dict[str, Any]:
    fields = {"schema_version", "method", "model_sha256", "calibration_end_date", "status", "gate"}
    if not isinstance(raw, dict) or raw.keys() != fields:
        raise ValueError("开仓门槛配置字段不完整或包含未知字段")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1 or raw["method"] != "scm":
        raise ValueError("开仓门槛仅支持 SCM v1")
    if raw["status"] not in {"research", "validated"}:
        raise ValueError("未知开仓门槛状态")
    if raw["model_sha256"] != actual_model_sha256:
        raise ValueError("模型与开仓门槛不匹配")
    if expected_method not in (None, "scm"):
        raise ValueError("开仓门槛与模型方法不匹配")
    try:
        day = date.fromisoformat(raw["calibration_end_date"])
        if day.isoformat() != raw["calibration_end_date"]:
            raise ValueError("noncanonical date")
    except (TypeError, ValueError) as exc:
        raise ValueError("开仓门槛校准日期无效") from exc
    ScoreEntryGate.from_dict(raw["gate"])
    return raw
