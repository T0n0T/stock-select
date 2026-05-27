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
    classify_daily_macd_trend, classify_weekly_macd_trend, describe_b2_macd_score_context,
    describe_macd_trend_state, is_constructive_macd_trend_combo, map_b1_macd_phase_score,
    map_b2_macd_phase_score,
};
use crate::model::{Method, PreparedRow, ScreenResult};
use crate::review_protocol::{compute_weighted_total_for_profile, infer_signal_type};
use crate::reviewers::b1::{B1DecisionInput, decide_b1_review};
use crate::reviewers::b1_scoring::{
    PreviousAbnormalMoveMode, PricePositionMode, compute_b1_environment_gate, compute_bbi,
    score_b1_previous_abnormal_move, score_b1_price_position, score_b1_trend_structure,
    score_b1_volume_behavior,
};
use crate::reviewers::b2_scoring::{
    B2VerdictInput, B2WatchInput, infer_b2_elastic_watch, infer_b2_verdict, infer_b2_watch_tier,
    previous_abnormal_move_mode, price_position_mode, score_b2_previous_abnormal_move,
    score_b2_price_position, score_b2_trend_structure, score_b2_volume_behavior, score_b2_watch,
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
pub struct NativeReviewMergeArgs {
    pub method: Method,
    pub pick_date: NaiveDate,
    pub runtime_root: PathBuf,
    pub codes: Option<Vec<String>>,
}

#[derive(Debug, Clone, PartialEq)]
struct EnvironmentContext {
    state: String,
    reason: Option<String>,
    source: String,
    profile: MethodEnvironmentProfile,
}

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct WaveTaskContext {
    pub(crate) weekly_wave_context: String,
    pub(crate) daily_wave_context: String,
    pub(crate) wave_combo_context: String,
}

#[derive(Debug, Clone, PartialEq)]
struct B1BaselineOutput {
    review: Value,
    wave_context: WaveTaskContext,
}

#[derive(Debug, Clone, PartialEq)]
struct BaselineOutput {
    review: Value,
    wave_context: WaveTaskContext,
}

pub fn run_native_review(args: NativeReviewArgs) -> anyhow::Result<PathBuf> {
    match args.method {
        Method::B1 | Method::B2 => run_native_method_review(args),
        _ => anyhow::bail!(
            "native review is currently implemented only for b1 and b2; method={}",
            args.method.as_str()
        ),
    }
}

pub fn run_native_review_merge(args: NativeReviewMergeArgs) -> anyhow::Result<PathBuf> {
    let review_dir = args.runtime_root.join("reviews").join(format!(
        "{}.{}",
        args.pick_date.format("%Y-%m-%d"),
        args.method.as_str()
    ));
    if !review_dir.exists() {
        anyhow::bail!("Review directory not found: {}", review_dir.display());
    }
    let llm_results_dir = review_dir.join("llm_review_results");
    if !llm_results_dir.exists() {
        anyhow::bail!(
            "LLM review result directory not found: {}",
            llm_results_dir.display()
        );
    }

    let selected_codes = args
        .codes
        .unwrap_or_default()
        .into_iter()
        .collect::<BTreeSet<_>>();
    let restrict_codes = !selected_codes.is_empty();
    let existing_summary = fs::read(review_dir.join("summary.json"))
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok());

    let mut review_paths = fs::read_dir(&review_dir)
        .with_context(|| format!("read review directory {}", review_dir.display()))?
        .map(|entry| entry.map(|entry| entry.path()))
        .collect::<Result<Vec<_>, _>>()?;
    review_paths.sort();

    let mut merged_reviews = Vec::new();
    let mut failures = Vec::new();
    for review_path in review_paths {
        if review_path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        if matches!(
            review_path.file_name().and_then(|value| value.to_str()),
            Some("summary.json" | "llm_review_tasks.json")
        ) {
            continue;
        }
        let mut existing_review: Value = serde_json::from_slice(
            &fs::read(&review_path)
                .with_context(|| format!("read review file {}", review_path.display()))?,
        )
        .with_context(|| format!("parse review file {}", review_path.display()))?;
        let code = existing_review
            .get("code")
            .and_then(Value::as_str)
            .map(str::to_string)
            .ok_or_else(|| {
                anyhow::anyhow!("review file missing code: {}", review_path.display())
            })?;
        if restrict_codes && !selected_codes.contains(&code) {
            merged_reviews.push(existing_review);
            continue;
        }

        let llm_path = llm_results_dir.join(format!("{code}.json"));
        if !llm_path.exists() {
            failures.push(json!({
                "code": code,
                "reason": format!("LLM review result not found: {}", llm_path.display()),
            }));
            merged_reviews.push(existing_review);
            continue;
        }

        match merge_llm_review(&mut existing_review, &llm_path) {
            Ok(()) => {
                atomic_write_json(&review_path, &existing_review)?;
                merged_reviews.push(existing_review);
            }
            Err(err) => {
                failures.push(json!({
                    "code": code,
                    "reason": err.to_string(),
                }));
                merged_reviews.push(existing_review);
            }
        }
    }

    let mut summary = summarize_reviews(args.pick_date, args.method, &merged_reviews, &failures);
    if let Some(environment_snapshot) =
        existing_summary.and_then(|summary| summary.get("environment_snapshot").cloned())
    {
        summary
            .as_object_mut()
            .expect("summary object")
            .insert("environment_snapshot".to_string(), environment_snapshot);
    }
    let summary_path = review_dir.join("summary.json");
    atomic_write_json(&summary_path, &summary)?;
    Ok(summary_path)
}

fn run_native_method_review(args: NativeReviewArgs) -> anyhow::Result<PathBuf> {
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
        let baseline_output = build_baseline_review(
            args.method,
            code,
            args.pick_date,
            history,
            &chart_path,
            candidate.signal.as_deref(),
            &env.profile,
        )?;
        let mut review =
            build_review_result(code, args.pick_date, &chart_path, baseline_output.review);
        maybe_merge_llm_review(
            &mut review,
            &review_dir
                .join("llm_review_results")
                .join(format!("{code}.json")),
        )?;
        if let Some(yellow_b1) = candidate.yellow_b1 {
            review
                .as_object_mut()
                .expect("review result is an object")
                .insert("yellow_b1".to_string(), Value::Bool(yellow_b1));
        }
        atomic_write_json(&review_dir.join(format!("{code}.json")), &review)?;
        if should_include_llm_task(&review, args.llm_min_baseline_score) {
            tasks.push(build_llm_task(
                args.method,
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
    limit_llm_review_tasks(&mut tasks, args.llm_review_limit);
    let mut tasks_payload = json!({
        "pick_date": args.pick_date.format("%Y-%m-%d").to_string(),
        "method": args.method.as_str(),
        "prompt_path": prompt_path(args.method),
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

fn build_baseline_review(
    method: Method,
    code: &str,
    pick_date: NaiveDate,
    history: &[PreparedRow],
    chart_path: &Path,
    signal: Option<&str>,
    profile: &MethodEnvironmentProfile,
) -> anyhow::Result<BaselineOutput> {
    match method {
        Method::B1 => {
            let output = build_b1_baseline_review(code, pick_date, history, chart_path, profile)?;
            Ok(BaselineOutput {
                review: output.review,
                wave_context: output.wave_context,
            })
        }
        Method::B2 => {
            build_b2_baseline_review(code, pick_date, history, chart_path, signal, profile)
        }
        _ => anyhow::bail!("native review is currently implemented only for b1 and b2"),
    }
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

fn build_b2_baseline_review(
    code: &str,
    pick_date: NaiveDate,
    history: &[PreparedRow],
    chart_path: &Path,
    signal: Option<&str>,
    profile: &MethodEnvironmentProfile,
) -> anyhow::Result<BaselineOutput> {
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
    let weekly_trend = classify_weekly_macd_trend(history);
    let daily_trend = classify_daily_macd_trend(history);

    let mut trend_structure = score_b2_trend_structure(
        &close,
        &low,
        &ma25,
        &zxdkx,
        Some(&weekly_trend),
        Some(&daily_trend),
        Some(profile),
    );
    let mut price_position =
        score_b2_price_position(&close, &high, &low, price_position_mode(profile));
    if profile.state == "neutral" {
        if price_position == 3.0
            && matches!(close.last().zip(ma25.last()), Some((close, Some(ma25))) if close >= ma25)
        {
            price_position = 4.0;
        }
        if price_position >= 5.0 {
            price_position = 4.0;
        }
    }
    if profile.state == "weak" && trend_structure > 4.0 {
        trend_structure = 4.0;
    }
    let volume_behavior = score_b2_volume_behavior(&close, &volume);
    let previous_abnormal_move = score_b2_previous_abnormal_move(
        &open,
        &close,
        &volume,
        previous_abnormal_move_mode(profile),
    );
    let mut macd_phase = map_b2_macd_phase_score(
        history.len(),
        &weekly_trend,
        &daily_trend,
        signal,
        &profile.state,
    );
    macd_phase = adjust_b2_weak_macd_phase_boundary(
        macd_phase,
        profile,
        signal,
        trend_structure,
        price_position,
        volume_behavior,
        previous_abnormal_move,
    );
    let base_total_score = compute_weighted_total_for_profile(
        &[
            ("trend_structure", trend_structure),
            ("price_position", price_position),
            ("volume_behavior", volume_behavior),
            ("previous_abnormal_move", previous_abnormal_move),
            ("macd_phase", macd_phase),
        ],
        profile,
        signal,
    );
    let signal_type = infer_signal_type(
        *close.last().unwrap_or(&f64::NAN),
        *open.last().unwrap_or(&f64::NAN),
        trend_structure,
        volume_behavior,
        price_position,
        true,
    );
    let close_above_ma25_pct = pct_above_option(
        *close.last().unwrap_or(&f64::NAN),
        ma25.last().copied().flatten(),
    );
    let ma25_above_zxdkx_pct = match (
        ma25.last().copied().flatten(),
        zxdkx.last().copied().flatten(),
    ) {
        (Some(ma25), Some(zxdkx)) if zxdkx.is_finite() && zxdkx != 0.0 => {
            Some((ma25 / zxdkx - 1.0) * 100.0)
        }
        _ => None,
    };
    let structure_score = round2(base_total_score);
    let mut verdict = infer_b2_verdict(B2VerdictInput {
        total_score: structure_score,
        trend_structure,
        price_position,
        volume_behavior,
        previous_abnormal_move,
        macd_phase,
        signal,
        signal_type,
        close_above_ma25_pct,
        ma25_above_zxdkx_pct,
        zxdq_5d_slope_pct: tail_slope_pct(&zxdq, 5),
        profile: Some(profile),
        strong_negative_macd_guard: resolve_strong_negative_macd_guard(history),
    });
    let relaunch_override = if profile.state == "weak" {
        infer_b2_weak_relaunch_override(B2WeakRelaunchInput {
            close: &close,
            high: &high,
            low: &low,
            ma25: &ma25,
            zxdq: &zxdq,
            zxdkx: &zxdkx,
            trend_structure,
            price_position,
            volume_behavior,
            previous_abnormal_move,
            macd_phase,
            signal,
            signal_type,
            current_verdict: verdict,
        })
    } else {
        B2RelaunchOverride {
            verdict,
            watch_tier: None,
        }
    };
    verdict = relaunch_override.verdict;
    let watch_seed = B2WatchInput {
        verdict,
        total_score: structure_score,
        trend_structure,
        price_position,
        volume_behavior,
        previous_abnormal_move,
        macd_phase,
        elastic_watch_reason: None,
        signal,
        signal_type,
    };
    let (elastic_watch, elastic_watch_reason) = infer_b2_elastic_watch(&watch_seed);
    let watch_score = score_b2_watch(B2WatchInput {
        elastic_watch_reason,
        ..watch_seed
    });
    let mut watch_tier = infer_b2_watch_tier(verdict, watch_score, elastic_watch_reason, signal);
    if verdict == "WATCH" && relaunch_override.watch_tier.is_some() {
        watch_tier = relaunch_override.watch_tier;
    }
    let total_score =
        calibrate_b2_selection_score(structure_score, verdict, watch_score, watch_tier);
    let comment = build_b2_comment(&weekly_trend, &daily_trend, verdict);
    let wave_context = describe_b2_macd_score_context(&weekly_trend, &daily_trend, "");
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
        "structure_score": structure_score,
        "total_score": total_score,
        "signal": signal,
        "signal_type": signal_type,
        "verdict": verdict,
        "elastic_watch": elastic_watch,
        "elastic_watch_reason": elastic_watch_reason,
        "watch_score": watch_score,
        "watch_tier": watch_tier,
        "comment": comment,
    });
    Ok(BaselineOutput {
        review: baseline_review,
        wave_context,
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
        "signal",
        "elastic_watch",
        "elastic_watch_reason",
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

fn maybe_merge_llm_review(review: &mut Value, llm_path: &Path) -> anyhow::Result<()> {
    if !llm_path.exists() {
        return Ok(());
    }
    merge_llm_review(review, llm_path)
}

fn merge_llm_review(review: &mut Value, llm_path: &Path) -> anyhow::Result<()> {
    let llm_review: Value = serde_json::from_slice(
        &fs::read(llm_path).with_context(|| format!("read llm review {}", llm_path.display()))?,
    )
    .with_context(|| format!("parse llm review {}", llm_path.display()))?;
    validate_llm_review(&llm_review)?;

    let baseline_score = review
        .get("baseline_review")
        .and_then(|baseline| baseline.get("total_score"))
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let llm_score = llm_review
        .get("total_score")
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let weighted_review_score = round2(baseline_score * 0.4 + llm_score * 0.6);
    let final_score = round2(baseline_score);
    let final_verdict = infer_final_verdict(final_score);
    let object = review.as_object_mut().expect("review result is an object");
    object.insert("review_mode".to_string(), json!("merged"));
    object.insert("llm_review".to_string(), llm_review.clone());
    object.insert("llm_score".to_string(), json!(llm_score));
    object.insert(
        "weighted_review_score".to_string(),
        json!(weighted_review_score),
    );
    object.insert("final_score".to_string(), json!(final_score));
    object.insert("total_score".to_string(), json!(final_score));
    object.insert(
        "signal_type".to_string(),
        llm_review
            .get("signal_type")
            .cloned()
            .unwrap_or_else(|| json!("")),
    );
    object.insert("verdict".to_string(), json!(final_verdict));
    object.insert(
        "comment".to_string(),
        llm_review
            .get("comment")
            .cloned()
            .unwrap_or_else(|| json!("")),
    );
    Ok(())
}

fn validate_llm_review(payload: &Value) -> anyhow::Result<()> {
    let object = payload
        .as_object()
        .ok_or_else(|| anyhow::anyhow!("llm review must be a JSON object"))?;
    for field in [
        "trend_reasoning",
        "position_reasoning",
        "volume_reasoning",
        "abnormal_move_reasoning",
        "macd_reasoning",
        "signal_reasoning",
        "comment",
    ] {
        if object
            .get(field)
            .and_then(Value::as_str)
            .is_none_or(|value| value.trim().is_empty())
        {
            anyhow::bail!("llm review missing or empty field: {field}");
        }
    }
    let scores = object
        .get("scores")
        .and_then(Value::as_object)
        .ok_or_else(|| anyhow::anyhow!("llm review missing scores object"))?;
    for field in [
        "trend_structure",
        "price_position",
        "volume_behavior",
        "previous_abnormal_move",
        "macd_phase",
    ] {
        let Some(score) = scores.get(field).and_then(Value::as_f64) else {
            anyhow::bail!("llm review missing score field: {field}");
        };
        if !(0.0..=5.0).contains(&score) {
            anyhow::bail!("llm review score out of range: {field}");
        }
    }
    let verdict = object
        .get("verdict")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("llm review missing verdict"))?;
    if !["PASS", "WATCH", "FAIL"].contains(&verdict) {
        anyhow::bail!("llm review invalid verdict: {verdict}");
    }
    let signal_type = object
        .get("signal_type")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("llm review missing signal_type"))?;
    if !["trend_start", "rebound", "distribution_risk"].contains(&signal_type) {
        anyhow::bail!("llm review invalid signal_type: {signal_type}");
    }
    Ok(())
}

fn infer_final_verdict(total_score: f64) -> &'static str {
    if total_score >= 4.0 {
        "PASS"
    } else if total_score >= 3.2 {
        "WATCH"
    } else {
        "FAIL"
    }
}

fn build_llm_task(
    method: Method,
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
    let mut task = json!({
        "code": code,
        "pick_date": pick_date.format("%Y-%m-%d").to_string(),
        "chart_path": chart_path.to_string_lossy(),
        "rubric_path": "references/review-rubric.md",
        "prompt_path": prompt_path(method),
        "input_mode": "image",
        "dispatch": "subagent",
        "weekly_wave_context": wave_context.weekly_wave_context,
        "daily_wave_context": wave_context.daily_wave_context,
        "wave_combo_context": wave_context.wave_combo_context,
        "review_focus_context": review_focus_context(method, &env.profile),
        "environment_state": env.state,
        "environment_reason": env.reason,
        "environment_llm_focus": env.profile.llm_focus,
        "rank": rank,
        "baseline_score": baseline_score,
        "baseline_verdict": baseline_verdict,
    });
    if method == Method::B2 {
        task.as_object_mut().expect("task object").insert(
            "signal".to_string(),
            review.get("signal").cloned().unwrap_or(Value::Null),
        );
    }
    task
}

fn limit_llm_review_tasks(tasks: &mut Vec<Value>, limit: Option<usize>) {
    let Some(limit) = limit else {
        return;
    };
    tasks.sort_by(|left, right| {
        let left_score = left
            .get("baseline_score")
            .and_then(Value::as_f64)
            .unwrap_or(0.0);
        let right_score = right
            .get("baseline_score")
            .and_then(Value::as_f64)
            .unwrap_or(0.0);
        right_score
            .partial_cmp(&left_score)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| {
                let left_rank = left.get("rank").and_then(Value::as_u64).unwrap_or(u64::MAX);
                let right_rank = right
                    .get("rank")
                    .and_then(Value::as_u64)
                    .unwrap_or(u64::MAX);
                left_rank.cmp(&right_rank)
            })
    });
    tasks.truncate(limit);
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

#[derive(Debug, Clone, Copy, PartialEq)]
struct B2RelaunchOverride {
    verdict: &'static str,
    watch_tier: Option<&'static str>,
}

#[derive(Debug, Clone, Copy)]
struct B2WeakRelaunchInput<'a> {
    close: &'a [f64],
    high: &'a [f64],
    low: &'a [f64],
    ma25: &'a [Option<f64>],
    zxdq: &'a [Option<f64>],
    zxdkx: &'a [Option<f64>],
    trend_structure: f64,
    price_position: f64,
    volume_behavior: f64,
    previous_abnormal_move: f64,
    macd_phase: f64,
    signal: Option<&'a str>,
    signal_type: &'a str,
    current_verdict: &'static str,
}

fn infer_b2_weak_relaunch_override(input: B2WeakRelaunchInput<'_>) -> B2RelaunchOverride {
    let support_slopes = B2SupportSlopes {
        zxdq_5d: tail_slope_pct(input.zxdq, 5),
        zxdkx_5d: tail_slope_pct(input.zxdkx, 5),
    };
    let support_positions =
        compute_b2_recent_support_positions(input.close, input.ma25, input.zxdq, input.zxdkx);
    let a_result = detect_b2_weak_safe_relaunch_a(&input);
    if a_result.matched && a_result.redundancy_pct.is_some_and(|value| value <= 5.0) {
        if a_result.quality == Some("clean")
            && signal_eq(input.signal, "B2")
            && input.signal_type == "rebound"
            && input.macd_phase < 4.0
            && !(support_slopes.zxdq_5d.unwrap_or(0.0) <= -1.0
                && input.volume_behavior >= 3.0
                && input.macd_phase >= 3.5)
        {
            return B2RelaunchOverride {
                verdict: "PASS",
                watch_tier: None,
            };
        }
        let mut watch_tier = Some("WATCH-A");
        if input.signal_type == "trend_start" {
            watch_tier = Some("WATCH-B");
        } else if signal_in(input.signal, &["B3", "B3+"]) && input.signal_type == "rebound" {
            watch_tier = Some("WATCH-B");
        } else if input.signal_type == "rebound"
            && ((support_slopes.zxdq_5d.unwrap_or(0.0) <= -1.5
                && support_positions.close_vs_ma25.unwrap_or(0.0) <= 0.0
                && support_positions.close_vs_zxdq.unwrap_or(0.0) <= 0.0)
                || (input.macd_phase >= 4.2
                    && support_positions.close_vs_zxdkx.unwrap_or(0.0) >= 8.0))
        {
            watch_tier = Some("WATCH-B");
        }
        return B2RelaunchOverride {
            verdict: "WATCH",
            watch_tier,
        };
    }

    let b_result = detect_b2_weak_safe_relaunch_b(&input);
    if b_result.matched && b_result.redundancy_pct.is_some_and(|value| value <= 5.0) {
        if input.current_verdict == "FAIL" {
            return B2RelaunchOverride {
                verdict: "WATCH",
                watch_tier: Some("WATCH-B"),
            };
        }
        if b_result.quality == Some("clean") {
            return B2RelaunchOverride {
                verdict: "WATCH",
                watch_tier: Some("WATCH-A"),
            };
        }
        if !(signal_eq(input.signal, "B2")
            && input.signal_type == "trend_start"
            && input.volume_behavior >= 5.0
            && (2.60..=2.62).contains(&input.macd_phase))
        {
            return B2RelaunchOverride {
                verdict: input.current_verdict,
                watch_tier: None,
            };
        }
        return B2RelaunchOverride {
            verdict: "WATCH",
            watch_tier: Some("WATCH-B"),
        };
    }

    B2RelaunchOverride {
        verdict: input.current_verdict,
        watch_tier: None,
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct B2SupportSlopes {
    zxdq_5d: Option<f64>,
    zxdkx_5d: Option<f64>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct B2SupportPositions {
    close_vs_ma25: Option<f64>,
    close_vs_zxdq: Option<f64>,
    close_vs_zxdkx: Option<f64>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct B2RelaunchDetection {
    matched: bool,
    quality: Option<&'static str>,
    redundancy_pct: Option<f64>,
}

fn compute_b2_recent_support_positions(
    close: &[f64],
    ma25: &[Option<f64>],
    zxdq: &[Option<f64>],
    zxdkx: &[Option<f64>],
) -> B2SupportPositions {
    let latest_close = close.last().copied().unwrap_or(0.0);
    B2SupportPositions {
        close_vs_ma25: pct_above_option(latest_close, ma25.last().copied().flatten()),
        close_vs_zxdq: pct_above_option(latest_close, zxdq.last().copied().flatten()),
        close_vs_zxdkx: pct_above_option(latest_close, zxdkx.last().copied().flatten()),
    }
}

fn detect_b2_weak_safe_relaunch_a(input: &B2WeakRelaunchInput<'_>) -> B2RelaunchDetection {
    if input.close.len() < 20 {
        return B2RelaunchDetection {
            matched: false,
            quality: None,
            redundancy_pct: None,
        };
    }
    let latest_close = *input.close.last().unwrap_or(&f64::NAN);
    let latest_ma25 = input.ma25.last().copied().flatten().unwrap_or(f64::NAN);
    let latest_zxdkx = input.zxdkx.last().copied().flatten().unwrap_or(f64::NAN);
    if !latest_zxdkx.is_finite() || latest_zxdkx <= 0.0 {
        return B2RelaunchDetection {
            matched: false,
            quality: None,
            redundancy_pct: None,
        };
    }
    let pullback_low = min_tail_f64(input.low, 15).unwrap_or(f64::NAN);
    let reclaim_ok = latest_close >= latest_zxdkx && pullback_low <= latest_zxdkx * 1.02;
    let redundancy_pct = if latest_ma25.is_finite() && latest_ma25 > 0.0 {
        (latest_close / latest_zxdkx.max(latest_ma25) - 1.0) * 100.0
    } else {
        (latest_close / latest_zxdkx - 1.0) * 100.0
    };
    if !reclaim_ok {
        return B2RelaunchDetection {
            matched: false,
            quality: None,
            redundancy_pct: Some(round2(redundancy_pct)),
        };
    }
    let matched = matches!(input.signal_type, "rebound" | "trend_start")
        && input.trend_structure >= 3.0
        && input.price_position >= 3.0
        && input.volume_behavior >= 2.0
        && input.previous_abnormal_move >= 5.0
        && pullback_low >= latest_zxdkx * 0.95;
    if !matched {
        return B2RelaunchDetection {
            matched: false,
            quality: None,
            redundancy_pct: Some(round2(redundancy_pct)),
        };
    }
    let quality = if input.price_position >= 4.0
        && [2.0, 3.0].contains(&input.volume_behavior)
        && input.macd_phase < 4.5
    {
        "clean"
    } else {
        "borderline"
    };
    B2RelaunchDetection {
        matched: true,
        quality: Some(quality),
        redundancy_pct: Some(round2(redundancy_pct)),
    }
}

fn detect_b2_weak_safe_relaunch_b(input: &B2WeakRelaunchInput<'_>) -> B2RelaunchDetection {
    if input.close.len() < 25 {
        return B2RelaunchDetection {
            matched: false,
            quality: None,
            redundancy_pct: None,
        };
    }
    let latest_close = *input.close.last().unwrap_or(&f64::NAN);
    let latest_zxdq = input.zxdq.last().copied().flatten().unwrap_or(f64::NAN);
    let latest_zxdkx = input.zxdkx.last().copied().flatten().unwrap_or(f64::NAN);
    if !latest_zxdq.is_finite() || latest_zxdq <= 0.0 || !latest_zxdkx.is_finite() {
        return B2RelaunchDetection {
            matched: false,
            quality: None,
            redundancy_pct: None,
        };
    }
    let tail_start = input.close.len().saturating_sub(20);
    let tail_close = &input.close[tail_start..];
    let tail_low = &input.low[tail_start..];
    let tail_zxdq = &input.zxdq[tail_start..];
    let consolidation_low = min_tail_f64(input.low, 20).unwrap_or(f64::NAN);
    let consolidation_high = max_tail_f64(input.high, 20).unwrap_or(f64::NAN);
    let consolidation_span_pct = if consolidation_low > 0.0 {
        (consolidation_high / consolidation_low - 1.0) * 100.0
    } else {
        999.0
    };
    let reclaim_ok = latest_close >= latest_zxdq && consolidation_low <= latest_zxdq * 1.05;
    let consolidation_ok = consolidation_span_pct <= 38.0
        && tail_close.last().copied().unwrap_or(f64::NAN) >= tail_close[0] * 0.95;
    let anchor_price = find_recent_support_reclaim_anchor(tail_close, tail_low, tail_zxdq);
    let redundancy_pct = if anchor_price.is_some_and(|value| value > 0.0) {
        (latest_close / anchor_price.unwrap() - 1.0) * 100.0
    } else {
        (latest_close / latest_zxdq - 1.0) * 100.0
    };
    if !reclaim_ok || !consolidation_ok {
        return B2RelaunchDetection {
            matched: false,
            quality: None,
            redundancy_pct: Some(round2(redundancy_pct)),
        };
    }
    let matched = input.signal_type == "trend_start"
        && input.trend_structure >= 4.0
        && input.price_position >= 4.0
        && input.volume_behavior >= 3.0
        && input.previous_abnormal_move >= 3.0
        && latest_close >= latest_zxdkx;
    if !matched {
        return B2RelaunchDetection {
            matched: false,
            quality: None,
            redundancy_pct: Some(round2(redundancy_pct)),
        };
    }
    let quality = if signal_eq(input.signal, "B2") && input.macd_phase >= 4.2 {
        "clean"
    } else {
        "normal"
    };
    B2RelaunchDetection {
        matched: true,
        quality: Some(quality),
        redundancy_pct: Some(round2(redundancy_pct)),
    }
}

fn find_recent_support_reclaim_anchor(
    tail_close: &[f64],
    tail_low: &[f64],
    tail_support: &[Option<f64>],
) -> Option<f64> {
    if tail_close.len() < 2 {
        return None;
    }
    for idx in (1..tail_close.len()).rev() {
        let current_close = tail_close[idx];
        let current_support = tail_support[idx]?;
        let previous_close = tail_close[idx - 1];
        let previous_support = tail_support[idx - 1]?;
        let current_low = tail_low[idx];
        let previous_low = tail_low[idx - 1];
        let touched_support =
            previous_low <= previous_support * 1.02 || current_low <= current_support * 1.02;
        let reclaimed_support =
            current_close >= current_support && previous_close < previous_support * 1.01;
        if touched_support && reclaimed_support {
            return Some(current_close);
        }
    }
    None
}

fn min_tail_f64(values: &[f64], len: usize) -> Option<f64> {
    values
        .iter()
        .rev()
        .take(len)
        .copied()
        .filter(|value| value.is_finite())
        .fold(None, |acc: Option<f64>, value| {
            Some(acc.map_or(value, |current| current.min(value)))
        })
}

fn max_tail_f64(values: &[f64], len: usize) -> Option<f64> {
    values
        .iter()
        .rev()
        .take(len)
        .copied()
        .filter(|value| value.is_finite())
        .fold(None, |acc: Option<f64>, value| {
            Some(acc.map_or(value, |current| current.max(value)))
        })
}

fn signal_eq(signal: Option<&str>, expected: &str) -> bool {
    signal.unwrap_or("").trim().eq_ignore_ascii_case(expected)
}

fn signal_in(signal: Option<&str>, expected: &[&str]) -> bool {
    expected.iter().any(|item| signal_eq(signal, item))
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

fn adjust_b2_weak_macd_phase_boundary(
    macd_phase: f64,
    profile: &MethodEnvironmentProfile,
    signal: Option<&str>,
    trend_structure: f64,
    price_position: f64,
    volume_behavior: f64,
    previous_abnormal_move: f64,
) -> f64 {
    if profile.state == "weak"
        && signal_eq(signal, "B3")
        && (2.60..=2.62).contains(&macd_phase)
        && trend_structure >= 4.0
        && price_position <= 2.0
        && volume_behavior >= 5.0
        && previous_abnormal_move >= 5.0
    {
        2.75
    } else {
        macd_phase
    }
}

fn calibrate_b2_selection_score(
    structure_score: f64,
    verdict: &str,
    watch_score: Option<f64>,
    watch_tier: Option<&str>,
) -> f64 {
    if !verdict.eq_ignore_ascii_case("WATCH") || watch_score.is_none() {
        return round2(structure_score.clamp(1.0, 5.0));
    }
    let tier_bonus = match watch_tier.unwrap_or("").to_ascii_uppercase().as_str() {
        "WATCH-A" => 0.12,
        "WATCH-C" => -0.12,
        _ => 0.0,
    };
    let calibrated = 3.3 + watch_score.unwrap_or(0.0).clamp(0.0, 100.0) / 100.0 + tier_bonus;
    let selected = if structure_score >= 4.2 {
        structure_score.max(calibrated)
    } else {
        calibrated
    };
    round2(selected.clamp(1.0, 5.0))
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

fn prompt_path(method: Method) -> String {
    let prompt = match method {
        Method::B1 => "prompt-b1.md",
        Method::B2 => "prompt-b2.md",
        Method::Dribull => "prompt-dribull.md",
    };
    format!("{PYTHON_STOCK_SELECT_ROOT}/.agents/skills/stock-select/references/{prompt}")
}

fn review_focus_context(method: Method, profile: &MethodEnvironmentProfile) -> String {
    match method {
        Method::B1 => format!(
            "当前 review 重点：左侧赔率优先，目标是 N 型回调低点而不是右侧追价；深度回调不天然扣分，关键看趋势支撑是否仍在；周 MACD 红柱质量优先于旧日线 MACD 叙事，重点判断红柱是否有效、是否水上、是否明显衰减或背离。 环境附加重点：{}",
            profile.llm_focus
        ),
        Method::B2 => format!(
            "当前 review 重点：右侧启动确认和 MACD 共振质量；识别 B2/B3/B3+/B4/B5 信号后的延续性、过热风险和可交易冗余。 环境附加重点：{}",
            profile.llm_focus
        ),
        _ => profile.llm_focus.clone(),
    }
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

fn build_b2_comment(
    weekly_trend: &crate::macd_trends::MacdTrendState,
    daily_trend: &crate::macd_trends::MacdTrendState,
    verdict: &str,
) -> String {
    let combo_text = if is_constructive_macd_trend_combo(weekly_trend, daily_trend) {
        "符合"
    } else {
        "不符合"
    };
    format!(
        "{}、{}，该MACD组合{}b2，当前结论为{}。",
        describe_macd_trend_state("周线", weekly_trend),
        describe_macd_trend_state("日线", daily_trend),
        combo_text,
        verdict
    )
}

fn tail_slope_pct(values: &[Option<f64>], periods: usize) -> Option<f64> {
    let filtered = values.iter().copied().flatten().collect::<Vec<_>>();
    if filtered.len() <= periods {
        return None;
    }
    let previous = filtered[filtered.len() - periods - 1];
    let latest = filtered[filtered.len() - 1];
    if previous == 0.0 {
        None
    } else {
        Some((latest / previous - 1.0) * 100.0)
    }
}

fn resolve_strong_negative_macd_guard(history: &[PreparedRow]) -> bool {
    let mut negative_run = Vec::new();
    for row in history.iter().rev() {
        let hist = row.macd_hist;
        if hist < 0.0 {
            negative_run.push(hist.abs());
        } else {
            break;
        }
    }
    let Some(latest_hist) = history.last().map(|row| row.macd_hist) else {
        return true;
    };
    if latest_hist >= 0.0 {
        return true;
    }
    let recent_peak = negative_run
        .into_iter()
        .fold(latest_hist.abs(), |current, value| current.max(value));
    recent_peak <= 0.0 || latest_hist.abs() < recent_peak * 0.5
}
