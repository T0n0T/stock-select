use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::Context;
use chrono::NaiveDate;
use serde_json::{Map, Value, json};

use crate::cache::{atomic_write_json, candidate_output_path, load_prepared_cache};
use crate::config::screen_window;
use crate::environment_profiles::{MethodEnvironmentProfile, get_method_environment_profile};
use crate::macd_trends::{
    classify_daily_macd_trend, classify_weekly_macd_trend, describe_macd_trend_state,
    is_constructive_macd_trend_combo, map_b1_macd_phase_score,
};
use crate::model::{Method, PreparedRow, ScreenResult};
use crate::review_protocol::{compute_weighted_total_for_profile, infer_signal_type};
use crate::reviewers::b1::{B1DecisionInput, decide_b1_review};
use crate::reviewers::b1_scoring::{
    PreviousAbnormalMoveMode, PricePositionMode, compute_b1_environment_gate, compute_bbi,
    score_b1_previous_abnormal_move, score_b1_price_position, score_b1_trend_structure,
    score_b1_volume_behavior,
};

const PYTHON_STOCK_SELECT_ROOT: &str = "/home/pi/Documents/agents/stock-select";
const LLM_REVIEW_MAX_CONCURRENCY: usize = 6;

#[derive(Debug, Clone, PartialEq)]
pub struct NativeReviewArgs {
    pub method: Method,
    pub pick_date: NaiveDate,
    pub runtime_root: PathBuf,
    pub environment_state: Option<String>,
    pub environment_reason: Option<String>,
    pub llm_min_baseline_score: Option<f64>,
    pub llm_review_limit: Option<usize>,
}

#[derive(Debug, Clone, PartialEq)]
struct EnvironmentContext {
    state: String,
    reason: Option<String>,
    source: String,
    profile: MethodEnvironmentProfile,
}

#[derive(Debug, Clone, PartialEq)]
struct WaveTaskContext {
    weekly_wave_context: String,
    daily_wave_context: String,
    wave_combo_context: String,
}

#[derive(Debug, Clone, PartialEq)]
struct B1BaselineOutput {
    review: Value,
    wave_context: WaveTaskContext,
}

pub fn run_native_review(args: NativeReviewArgs) -> anyhow::Result<PathBuf> {
    match args.method {
        Method::B1 => run_native_b1_review(args),
        _ => anyhow::bail!(
            "native review is currently implemented only for b1; method={}",
            args.method.as_str()
        ),
    }
}

fn run_native_b1_review(args: NativeReviewArgs) -> anyhow::Result<PathBuf> {
    let candidate_path = candidate_output_path(&args.runtime_root, args.pick_date, args.method);
    let candidate_payload: ScreenResult = serde_json::from_slice(
        &fs::read(&candidate_path)
            .with_context(|| format!("read candidate file {}", candidate_path.display()))?,
    )
    .with_context(|| format!("parse candidate file {}", candidate_path.display()))?;

    let (start_date, end_date) = screen_window(args.pick_date);
    let prepared = load_prepared_cache(
        &args.runtime_root,
        args.method,
        args.pick_date,
        start_date,
        end_date,
    )?
    .ok_or_else(|| {
        anyhow::anyhow!(
            "prepared cache not found for native review; run screen first for {} {}",
            args.pick_date,
            args.method.as_str()
        )
    })?;
    let histories = group_histories_by_code(&prepared, args.pick_date);
    let env =
        resolve_environment_context(args.method, args.environment_state, args.environment_reason)?;

    let review_dir = args.runtime_root.join("reviews").join(format!(
        "{}.{}",
        args.pick_date.format("%Y-%m-%d"),
        args.method.as_str()
    ));
    fs::create_dir_all(&review_dir)?;
    let chart_dir = args.runtime_root.join("charts").join(format!(
        "{}.{}",
        args.pick_date.format("%Y-%m-%d"),
        args.method.as_str()
    ));

    let mut reviews = Vec::with_capacity(candidate_payload.candidates.len());
    let mut failures = Vec::new();
    let mut tasks = Vec::new();
    for (rank, candidate) in candidate_payload.candidates.iter().enumerate() {
        let code = candidate.code.as_str();
        let chart_path = chart_dir.join(format!("{code}_day.png"));
        if !chart_path.exists() {
            failures.push(json!({
                "code": code,
                "reason": format!("Chart file not found: {}", chart_path.display()),
            }));
            continue;
        }
        let Some(history) = histories.get(code) else {
            failures.push(json!({
                "code": code,
                "reason": "No daily history available for review.",
            }));
            continue;
        };
        let baseline_output =
            build_b1_baseline_review(code, args.pick_date, history, &chart_path, &env.profile)?;
        let mut review =
            build_review_result(code, args.pick_date, &chart_path, baseline_output.review);
        if let Some(yellow_b1) = candidate.yellow_b1 {
            review
                .as_object_mut()
                .expect("review result is an object")
                .insert("yellow_b1".to_string(), Value::Bool(yellow_b1));
        }
        atomic_write_json(&review_dir.join(format!("{code}.json")), &review)?;
        if should_include_llm_task(&review, args.llm_min_baseline_score) {
            tasks.push(build_llm_task(
                code,
                args.pick_date,
                &chart_path,
                rank + 1,
                &review,
                &baseline_output.wave_context,
                &env,
            ));
        }
        reviews.push(review);
    }

    let mut summary = summarize_reviews(args.pick_date, args.method, &reviews, &failures);
    summary.as_object_mut().expect("summary object").insert(
        "environment_snapshot".to_string(),
        json!({
            "state": env.state,
            "interval_start": Value::Null,
            "source": env.source,
            "reason": env.reason,
        }),
    );
    let mut tasks = tasks;
    if let Some(limit) = args.llm_review_limit {
        tasks.truncate(limit);
    }
    let mut tasks_payload = json!({
        "pick_date": args.pick_date.format("%Y-%m-%d").to_string(),
        "method": args.method.as_str(),
        "prompt_path": b1_prompt_path(),
        "max_concurrency": LLM_REVIEW_MAX_CONCURRENCY,
        "tasks": tasks,
    });
    if let Some(limit) = args.llm_review_limit {
        tasks_payload
            .as_object_mut()
            .expect("tasks object")
            .insert("llm_review_limit".to_string(), json!(limit));
    }

    atomic_write_json(&review_dir.join("llm_review_tasks.json"), &tasks_payload)?;
    let summary_path = review_dir.join("summary.json");
    atomic_write_json(&summary_path, &summary)?;
    Ok(summary_path)
}

fn build_b1_baseline_review(
    code: &str,
    pick_date: NaiveDate,
    history: &[PreparedRow],
    chart_path: &Path,
    profile: &MethodEnvironmentProfile,
) -> anyhow::Result<B1BaselineOutput> {
    if history.is_empty() {
        anyhow::bail!("No daily history available for review.");
    }
    let open = history.iter().map(|row| row.open).collect::<Vec<_>>();
    let high = history.iter().map(|row| row.high).collect::<Vec<_>>();
    let low = history.iter().map(|row| row.low).collect::<Vec<_>>();
    let close = history.iter().map(|row| row.close).collect::<Vec<_>>();
    let volume = history.iter().map(|row| row.volume).collect::<Vec<_>>();
    let ma25 = history.iter().map(|row| row.ma25).collect::<Vec<_>>();
    let zxdq = history.iter().map(|row| row.zxdq).collect::<Vec<_>>();
    let zxdkx = history.iter().map(|row| row.zxdkx).collect::<Vec<_>>();
    let dif = history.iter().map(|row| row.dif).collect::<Vec<_>>();
    let dea = history.iter().map(|row| row.dea).collect::<Vec<_>>();
    let bbi = compute_bbi(&close);
    let price_mode = match profile
        .subscore_mode
        .get("price_position")
        .map(String::as_str)
    {
        Some("left_side_favored") => PricePositionMode::LeftSideFavored,
        Some("less_left_bias") => PricePositionMode::LessLeftBias,
        _ => PricePositionMode::Default,
    };

    let trend_structure = score_b1_trend_structure(&open, &close, &ma25, &zxdkx, &bbi);
    let price_position = score_b1_price_position(&close, &high, &low, &ma25, &zxdq, price_mode);
    let recent_start = open.len().saturating_sub(20);
    let volume_behavior = score_b1_volume_behavior(
        &open[recent_start..],
        &close[recent_start..],
        &volume[recent_start..],
    );
    let previous_abnormal_move = score_b1_previous_abnormal_move(
        &open,
        &close,
        &low,
        &volume,
        PreviousAbnormalMoveMode::Default,
    );

    let weekly_trend = classify_weekly_macd_trend(history);
    let daily_trend = classify_daily_macd_trend(history);
    let macd_phase = map_b1_macd_phase_score(
        history.len(),
        &weekly_trend,
        &daily_trend,
        &close,
        &profile.state,
    );
    let raw_total_score = compute_weighted_total_for_profile(
        &[
            ("trend_structure", trend_structure),
            ("price_position", price_position),
            ("volume_behavior", volume_behavior),
            ("previous_abnormal_move", previous_abnormal_move),
            ("macd_phase", macd_phase),
        ],
        profile,
        None,
    );
    let gate = compute_b1_environment_gate(&close, &ma25, &dif, &dea, &profile.state);
    let signal_type = infer_signal_type(
        *close.last().unwrap_or(&f64::NAN),
        *open.last().unwrap_or(&f64::NAN),
        trend_structure,
        volume_behavior,
        price_position,
        false,
    );
    let gate_flags = gate
        .triggered_flags
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    let decision = decide_b1_review(B1DecisionInput {
        signal_type,
        trend_structure,
        price_position,
        volume_behavior,
        previous_abnormal_move,
        macd_phase,
        raw_total_score,
        environment_state: &profile.state,
        gate_flags,
    });
    let close_above_ma25_pct = pct_above_option(
        *close.last().unwrap_or(&f64::NAN),
        ma25.last().copied().flatten(),
    );
    let close_above_zxdq_pct = pct_above_option(
        *close.last().unwrap_or(&f64::NAN),
        zxdq.last().copied().flatten(),
    );
    let day_pct = match (
        *open.last().unwrap_or(&f64::NAN),
        *close.last().unwrap_or(&f64::NAN),
    ) {
        (open, close) if open.is_finite() && open != 0.0 => Some((close / open - 1.0) * 100.0),
        _ => None,
    };
    let watch_reason = infer_b1_watch_reason(
        &decision.verdict,
        signal_type,
        raw_total_score,
        trend_structure,
        price_position,
        volume_behavior,
        previous_abnormal_move,
        macd_phase,
        close_above_zxdq_pct,
        day_pct,
    );
    let watch_score = score_b1_watch(
        &decision.verdict,
        watch_reason.as_deref(),
        trend_structure,
        volume_behavior,
        previous_abnormal_move,
        macd_phase,
        close_above_ma25_pct,
        close_above_zxdq_pct,
        day_pct,
    );
    let watch_tier = infer_b1_watch_tier(&decision.verdict, watch_reason.as_deref(), watch_score);

    let comment = build_b1_comment(&weekly_trend, &daily_trend, &decision.verdict);
    let weekly_wave_context = format!(
        "确定性识别结果：{}；原因：{}。",
        describe_macd_trend_state("周线", &weekly_trend),
        weekly_trend.reason
    );
    let daily_wave_context = format!(
        "确定性识别结果：{}；原因：{}。",
        describe_macd_trend_state("日线", &daily_trend),
        daily_trend.reason
    );
    let wave_combo_context = format!(
        "组合判定：{} b1 候选要求。",
        if is_constructive_macd_trend_combo(&weekly_trend, &daily_trend) {
            "符合"
        } else {
            "不符合"
        }
    );
    let baseline_review = json!({
        "code": code,
        "pick_date": pick_date.format("%Y-%m-%d").to_string(),
        "chart_path": chart_path.to_string_lossy(),
        "review_type": "baseline",
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
        "raw_total_score": raw_total_score,
        "total_score": decision.total_score,
        "signal_type": signal_type,
        "score_combo_key": decision.score_combo_key,
        "high_return_combo_match": decision.high_return_combo_match,
        "pass_family": decision.pass_family,
        "pass_family_tier": decision.pass_family_tier,
        "verdict": decision.verdict,
        "gate_flags": gate.triggered_flags,
        "gate_cooldown_active": gate.cooldown_active,
        "gate_below_ma25": gate.below_ma25,
        "gate_runup_pct": gate.runup_pct,
        "gate_sideways_amplitude_pct": gate.sideways_amplitude_pct,
        "gate_drawdown_pct": Value::Null,
        "gate_weekly_slope_26w": gate.weekly_slope_26w,
        "gate_weekly_macd_cooldown_active": gate.weekly_macd_cooldown_active,
        "watch_reason": watch_reason,
        "watch_score": watch_score,
        "watch_tier": watch_tier,
        "score_layer": decision.score_layer,
        "score_layer_score": decision.score_layer_score,
        "comment": comment,
    });
    Ok(B1BaselineOutput {
        review: baseline_review,
        wave_context: WaveTaskContext {
            weekly_wave_context,
            daily_wave_context,
            wave_combo_context,
        },
    })
}

fn build_review_result(
    code: &str,
    pick_date: NaiveDate,
    chart_path: &Path,
    baseline_review: Value,
) -> Value {
    let primary = baseline_review.as_object().expect("baseline review object");
    let mut out = Map::new();
    out.insert("code".to_string(), json!(code));
    out.insert(
        "pick_date".to_string(),
        json!(pick_date.format("%Y-%m-%d").to_string()),
    );
    out.insert(
        "chart_path".to_string(),
        json!(chart_path.to_string_lossy()),
    );
    out.insert("review_mode".to_string(), json!("baseline_local"));
    out.insert("llm_review".to_string(), Value::Null);
    out.insert("baseline_review".to_string(), baseline_review.clone());
    for key in [
        "total_score",
        "signal_type",
        "verdict",
        "comment",
        "watch_reason",
        "watch_score",
        "watch_tier",
        "score_combo_key",
        "high_return_combo_match",
        "pass_family",
        "pass_family_tier",
        "gate_flags",
        "gate_cooldown_active",
        "gate_below_ma25",
        "gate_runup_pct",
        "gate_sideways_amplitude_pct",
        "gate_weekly_macd_cooldown_active",
        "score_layer",
        "score_layer_score",
    ] {
        if let Some(value) = primary.get(key) {
            if !value.is_null()
                || matches!(
                    key,
                    "watch_reason"
                        | "watch_score"
                        | "watch_tier"
                        | "pass_family"
                        | "score_layer"
                        | "score_layer_score"
                )
            {
                out.insert(key.to_string(), value.clone());
            }
        }
    }
    Value::Object(out)
}

fn summarize_reviews(
    pick_date: NaiveDate,
    method: Method,
    reviews: &[Value],
    failures: &[Value],
) -> Value {
    let mut recommendations = reviews
        .iter()
        .filter(|review| review.get("verdict").and_then(Value::as_str) == Some("PASS"))
        .cloned()
        .collect::<Vec<_>>();
    let recommendation_codes = recommendations
        .iter()
        .filter_map(|review| review.get("code").and_then(Value::as_str))
        .collect::<BTreeSet<_>>();
    let mut excluded = reviews
        .iter()
        .filter(|review| {
            review
                .get("code")
                .and_then(Value::as_str)
                .is_none_or(|code| !recommendation_codes.contains(code))
        })
        .cloned()
        .collect::<Vec<_>>();
    recommendations.sort_by(compare_review_desc);
    excluded.sort_by(compare_review_desc);
    json!({
        "pick_date": pick_date.format("%Y-%m-%d").to_string(),
        "method": method.as_str(),
        "reviewed_count": reviews.len(),
        "recommendations": recommendations,
        "excluded": excluded,
        "failures": failures,
    })
}

fn build_llm_task(
    code: &str,
    pick_date: NaiveDate,
    chart_path: &Path,
    rank: usize,
    review: &Value,
    wave_context: &WaveTaskContext,
    env: &EnvironmentContext,
) -> Value {
    let baseline_score = review.get("total_score").cloned().unwrap_or(Value::Null);
    let baseline_verdict = review.get("verdict").cloned().unwrap_or(Value::Null);
    json!({
        "code": code,
        "pick_date": pick_date.format("%Y-%m-%d").to_string(),
        "chart_path": chart_path.to_string_lossy(),
        "rubric_path": "references/review-rubric.md",
        "prompt_path": b1_prompt_path(),
        "input_mode": "image",
        "dispatch": "subagent",
        "weekly_wave_context": wave_context.weekly_wave_context,
        "daily_wave_context": wave_context.daily_wave_context,
        "wave_combo_context": wave_context.wave_combo_context,
        "review_focus_context": b1_review_focus_context(&env.profile),
        "environment_state": env.state,
        "environment_reason": env.reason,
        "environment_llm_focus": env.profile.llm_focus,
        "rank": rank,
        "baseline_score": baseline_score,
        "baseline_verdict": baseline_verdict,
    })
}

fn should_include_llm_task(review: &Value, min_score: Option<f64>) -> bool {
    match min_score {
        Some(min_score) => review
            .get("total_score")
            .and_then(Value::as_f64)
            .is_some_and(|score| score >= min_score),
        None => true,
    }
}

fn compare_review_desc(left: &Value, right: &Value) -> std::cmp::Ordering {
    let left_key = review_sort_key(left);
    let right_key = review_sort_key(right);
    right_key
        .0
        .partial_cmp(&left_key.0)
        .unwrap_or(std::cmp::Ordering::Equal)
        .then_with(|| {
            right_key
                .1
                .partial_cmp(&left_key.1)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
}

fn review_sort_key(review: &Value) -> (f64, f64) {
    let baseline_score = review
        .get("baseline_review")
        .and_then(|baseline| baseline.get("total_score"))
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let total_score = review
        .get("total_score")
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    (baseline_score, total_score)
}

fn resolve_environment_context(
    method: Method,
    environment_state: Option<String>,
    environment_reason: Option<String>,
) -> anyhow::Result<EnvironmentContext> {
    let state = environment_state
        .unwrap_or_else(|| "neutral".to_string())
        .trim()
        .to_ascii_lowercase();
    let profile = get_method_environment_profile(method.as_str(), &state)?;
    Ok(EnvironmentContext {
        state,
        reason: environment_reason,
        source: "manual_override".to_string(),
        profile,
    })
}

fn pct_above_option(numerator: f64, denominator: Option<f64>) -> Option<f64> {
    match denominator {
        Some(denominator)
            if numerator.is_finite() && denominator.is_finite() && denominator != 0.0 =>
        {
            Some((numerator / denominator - 1.0) * 100.0)
        }
        _ => None,
    }
}

fn infer_b1_watch_reason(
    verdict: &str,
    signal_type: &str,
    total_score: f64,
    trend_structure: f64,
    price_position: f64,
    volume_behavior: f64,
    previous_abnormal_move: f64,
    macd_phase: f64,
    close_above_zxdq_pct: Option<f64>,
    day_pct: Option<f64>,
) -> Option<String> {
    if verdict != "WATCH" {
        return None;
    }
    if signal_type == "distribution_risk" {
        return Some("distribution_elastic".to_string());
    }
    if signal_type == "trend_start" {
        let trend_repair_like = total_score >= 3.8
            && trend_structure >= 4.0
            && (3.0..=4.0).contains(&price_position)
            && volume_behavior >= 3.0
            && previous_abnormal_move >= 3.0
            && (3.2..=4.2).contains(&macd_phase)
            && close_above_zxdq_pct.is_none_or(|value| value <= -5.0)
            && day_pct.is_none_or(|value| value <= 1.5);
        return Some(
            if trend_repair_like {
                "trend_start_repair"
            } else {
                "trend_start_weak"
            }
            .to_string(),
        );
    }
    if signal_type == "rebound" {
        if total_score >= 4.0 {
            return Some("rebound_near_pass_flawed".to_string());
        }
        let elastic_rebound = total_score >= 3.0
            && trend_structure >= 3.0
            && volume_behavior >= 3.0
            && previous_abnormal_move >= 3.0
            && (2.8..=4.2).contains(&macd_phase);
        return Some(
            if elastic_rebound {
                "rebound_elastic"
            } else {
                "rebound_ordinary"
            }
            .to_string(),
        );
    }
    Some("watch_ordinary".to_string())
}

fn score_b1_watch(
    verdict: &str,
    watch_reason: Option<&str>,
    trend_structure: f64,
    volume_behavior: f64,
    previous_abnormal_move: f64,
    macd_phase: f64,
    close_above_ma25_pct: Option<f64>,
    close_above_zxdq_pct: Option<f64>,
    day_pct: Option<f64>,
) -> Option<f64> {
    if verdict != "WATCH" {
        return None;
    }
    let mut score = 0.0;
    if let Some(value) = close_above_ma25_pct {
        if value <= -5.0 {
            score += 25.0;
        } else if value <= -3.0 {
            score += 20.0;
        } else if value <= 0.0 {
            score += 10.0;
        } else {
            score -= 10.0;
        }
    }
    if let Some(value) = close_above_zxdq_pct {
        if value <= -6.0 {
            score += 20.0;
        } else if value <= -4.0 {
            score += 12.0;
        } else if value <= 0.0 {
            score += 5.0;
        } else {
            score -= 10.0;
        }
    }
    if (3.2..=4.05).contains(&macd_phase) {
        score += 20.0;
    } else if (2.8..3.2).contains(&macd_phase) {
        score += 12.0;
    } else if macd_phase > 4.05 && macd_phase <= 4.2 {
        score += 5.0;
    } else {
        score -= 8.0;
    }
    score += (trend_structure - 3.0).max(0.0) * 6.0;
    score += (volume_behavior - 3.0).max(0.0) * 5.0;
    score += (previous_abnormal_move - 3.0).max(0.0) * 4.0;
    if let Some(value) = day_pct {
        if value <= 0.0 {
            score += 10.0;
        } else if value <= 1.0 {
            score += 5.0;
        } else if value > 3.0 {
            score -= 10.0;
        }
    }
    score += match watch_reason.unwrap_or("") {
        "distribution_elastic" => 5.0,
        "rebound_elastic" => 6.0,
        "trend_start_repair" => 4.0,
        "rebound_near_pass_flawed" => -2.0,
        "trend_start_weak" => -12.0,
        _ => 0.0,
    };
    Some(round2(score))
}

fn infer_b1_watch_tier(
    verdict: &str,
    watch_reason: Option<&str>,
    watch_score: Option<f64>,
) -> Option<String> {
    if verdict != "WATCH" {
        return None;
    }
    let reason = watch_reason.unwrap_or("");
    let score = watch_score.unwrap_or(0.0);
    if reason == "distribution_elastic" {
        return Some("WATCH-A".to_string());
    }
    if reason == "rebound_elastic" && score >= 55.0 {
        return Some("WATCH-A".to_string());
    }
    if reason == "trend_start_repair" || score >= 40.0 {
        return Some("WATCH-B".to_string());
    }
    Some("WATCH-C".to_string())
}

fn round2(value: f64) -> f64 {
    format!("{value:.2}")
        .parse::<f64>()
        .expect("formatted finite f64 should parse")
}

fn group_histories_by_code(
    rows: &[PreparedRow],
    pick_date: NaiveDate,
) -> BTreeMap<String, Vec<PreparedRow>> {
    let mut histories: BTreeMap<String, Vec<PreparedRow>> = BTreeMap::new();
    for row in rows.iter().filter(|row| row.trade_date <= pick_date) {
        histories
            .entry(row.ts_code.clone())
            .or_default()
            .push(row.clone());
    }
    for history in histories.values_mut() {
        history.sort_by_key(|row| row.trade_date);
    }
    histories
}

fn b1_prompt_path() -> String {
    format!("{PYTHON_STOCK_SELECT_ROOT}/.agents/skills/stock-select/references/prompt-b1.md")
}

fn b1_review_focus_context(profile: &MethodEnvironmentProfile) -> String {
    format!(
        "当前 review 重点：左侧赔率优先，目标是 N 型回调低点而不是右侧追价；深度回调不天然扣分，关键看趋势支撑是否仍在；周 MACD 红柱质量优先于旧日线 MACD 叙事，重点判断红柱是否有效、是否水上、是否明显衰减或背离。 环境附加重点：{}",
        profile.llm_focus
    )
}

fn build_b1_comment(
    weekly_trend: &crate::macd_trends::MacdTrendState,
    daily_trend: &crate::macd_trends::MacdTrendState,
    verdict: &str,
) -> String {
    let combo = if is_constructive_macd_trend_combo(weekly_trend, daily_trend) {
        "符合b1"
    } else {
        "不符合b1"
    };
    format!(
        "{}、{}，该MACD组合{}，当前结论为{}。",
        describe_macd_trend_state("周线", weekly_trend),
        describe_macd_trend_state("日线", daily_trend),
        combo,
        verdict
    )
}
