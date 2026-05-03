from dataclasses import dataclass


@dataclass(frozen=True)
class MethodEnvironmentProfile:
    method: str
    state: str
    weights: dict[str, float]
    signal_weight: float | None
    pass_threshold: float
    watch_threshold: float
    subscore_mode: dict[str, str]
    llm_focus: str


_PROFILES = {
    ("b1", "weak"): MethodEnvironmentProfile(
        method="b1",
        state="weak",
        weights={
            "trend_structure": 0.20,
            "price_position": 0.26,
            "volume_behavior": 0.20,
            "previous_abnormal_move": 0.20,
            "macd_phase": 0.14,
        },
        signal_weight=None,
        pass_threshold=4.1,
        watch_threshold=3.2,
        subscore_mode={
            "price_position": "left_side_favored",
            "trend_structure": "support_preserving",
        },
        llm_focus="优先高分给回调充分、支撑有效、赔率优先的结构。",
    ),
    ("b1", "neutral"): MethodEnvironmentProfile(
        method="b1",
        state="neutral",
        weights={
            "trend_structure": 0.23,
            "price_position": 0.20,
            "volume_behavior": 0.22,
            "previous_abnormal_move": 0.20,
            "macd_phase": 0.15,
        },
        signal_weight=None,
        pass_threshold=4.0,
        watch_threshold=3.2,
        subscore_mode={"price_position": "default", "trend_structure": "default"},
        llm_focus="优先高分给结构完整且赔率仍可接受的回调低点。",
    ),
    ("b1", "strong"): MethodEnvironmentProfile(
        method="b1",
        state="strong",
        weights={
            "trend_structure": 0.25,
            "price_position": 0.17,
            "volume_behavior": 0.23,
            "previous_abnormal_move": 0.20,
            "macd_phase": 0.15,
        },
        signal_weight=None,
        pass_threshold=4.0,
        watch_threshold=3.2,
        subscore_mode={
            "price_position": "less_left_bias",
            "trend_structure": "restart_favored",
        },
        llm_focus="优先高分给回调后接近再启动，而不是纯防守抄底。",
    ),
    ("b2", "weak"): MethodEnvironmentProfile(
        method="b2",
        state="weak",
        weights={
            "trend_structure": 0.12,
            "price_position": 0.28,
            "volume_behavior": 0.00,
            "previous_abnormal_move": 0.20,
            "macd_phase": 0.25,
        },
        signal_weight=0.15,
        pass_threshold=4.15,
        watch_threshold=3.3,
        subscore_mode={"price_position": "low_risk_required", "macd_phase": "strict"},
        llm_focus="弱环境下要压制高位右侧追启动，优先保留位置更安全且承接更强的样本。",
    ),
    ("b2", "neutral"): MethodEnvironmentProfile(
        method="b2",
        state="neutral",
        weights={
            "trend_structure": 0.14,
            "price_position": 0.22,
            "volume_behavior": 0.00,
            "previous_abnormal_move": 0.14,
            "macd_phase": 0.35,
        },
        signal_weight=0.15,
        pass_threshold=4.0,
        watch_threshold=3.3,
        subscore_mode={"price_position": "default", "macd_phase": "default"},
        llm_focus="中性环境下优先高分给结构完整且没有明显过热的启动样本。",
    ),
    ("b2", "strong"): MethodEnvironmentProfile(
        method="b2",
        state="strong",
        weights={
            "trend_structure": 0.18,
            "price_position": 0.18,
            "volume_behavior": 0.00,
            "previous_abnormal_move": 0.12,
            "macd_phase": 0.37,
        },
        signal_weight=0.15,
        pass_threshold=3.95,
        watch_threshold=3.3,
        subscore_mode={"price_position": "breakout_tolerant", "macd_phase": "aggressive"},
        llm_focus="强环境下优先高分给右侧启动确认和强 MACD 共振。",
    ),
}


def get_method_environment_profile(*, method: str, state: str) -> MethodEnvironmentProfile:
    key = (method.strip().lower(), state.strip().lower())
    if key not in _PROFILES:
        raise ValueError(f"Unsupported environment profile method/state: {key[0]} {key[1]}")
    profile = _PROFILES[key]
    return MethodEnvironmentProfile(
        method=profile.method,
        state=profile.state,
        weights=dict(profile.weights),
        signal_weight=profile.signal_weight,
        pass_threshold=profile.pass_threshold,
        watch_threshold=profile.watch_threshold,
        subscore_mode=dict(profile.subscore_mode),
        llm_focus=profile.llm_focus,
    )
