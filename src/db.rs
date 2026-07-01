use chrono::{Datelike, NaiveDate};
use postgres::{Client, NoTls, fallible_iterator::FallibleIterator};
use std::collections::BTreeMap;

use crate::intraday::MacdPeriodState;
use crate::model::{InstrumentInfo, MarketRow};

const DAILY_WINDOW_SESSION_SETTINGS_SQL: &str = "
    SET max_parallel_workers_per_gather = 2;
    SET work_mem = '64MB';
";

const MIN_DB_NATIVE_WINDOW_TRADE_DATES: i64 = 235;

const DB_NATIVE_DAILY_WINDOW_QUERY: &str = "
        WITH query_params AS (
            SELECT $1::date AS start_date, $2::date AS end_date
        ),
        market_placeholder AS (
            SELECT 1
        )
        SELECT
            s.ts_code,
            s.trade_date,
            s.open::double precision AS open,
            s.high::double precision AS high,
            s.low::double precision AS low,
            s.close::double precision AS close,
            s.adj_factor::double precision AS adj_factor,
            s.vol::double precision AS vol,
            s.amount::double precision AS amount,
            s.turnover_rate::double precision AS turnover_rate
        FROM stock_stk_factor_pro s
        WHERE s.trade_date BETWEEN (SELECT start_date FROM query_params) AND (SELECT end_date FROM query_params)
        ";

const DB_NATIVE_PICK_DATE_EXTRAS_QUERY: &str = "
        WITH recent_trade_dates AS (
            SELECT trade_date
            FROM (
                SELECT DISTINCT trade_date
                FROM stock_stk_factor_pro
                WHERE trade_date <= $1
                ORDER BY trade_date DESC
                LIMIT 252
            ) d
        ),
        index_market_base AS (
            SELECT
                i.ts_code,
                i.trade_date,
                i.close::double precision AS close,
                lag(i.close, 5) OVER (PARTITION BY i.ts_code ORDER BY i.trade_date)::double precision AS close_5_ago,
                lag(i.close, 20) OVER (PARTITION BY i.ts_code ORDER BY i.trade_date)::double precision AS close_20_ago,
                avg(i.close::double precision) OVER (PARTITION BY i.ts_code ORDER BY i.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS close_ma20,
                stddev_samp(i.pct_change::double precision) OVER (PARTITION BY i.ts_code ORDER BY i.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)::double precision AS volatility20_pct
            FROM index_idx_factor_pro i
            JOIN recent_trade_dates w
              ON w.trade_date = i.trade_date
            WHERE i.ts_code IN ('000001.SH', '399303.SZ')
        ),
        index_market_raw AS (
            SELECT
                ts_code,
                trade_date,
                CASE
                    WHEN close_5_ago IS NOT NULL AND close_5_ago != 0
                    THEN (close - close_5_ago) / close_5_ago * 100.0
                END AS ret5_pct,
                CASE
                    WHEN close_20_ago IS NOT NULL AND close_20_ago != 0
                    THEN (close - close_20_ago) / close_20_ago * 100.0
                END AS ret20_pct,
                CASE
                    WHEN close_ma20 IS NOT NULL AND close_ma20 != 0
                    THEN (close - close_ma20) / close_ma20 * 100.0
                END AS ma20_bias_pct,
                volatility20_pct
            FROM index_market_base
        ),
        index_market_factors AS (
            SELECT
                trade_date,
                max(ret5_pct) FILTER (WHERE ts_code = '000001.SH')::double precision AS market_sse_ret5_pct,
                max(ret20_pct) FILTER (WHERE ts_code = '000001.SH')::double precision AS market_sse_ret20_pct,
                max(ma20_bias_pct) FILTER (WHERE ts_code = '000001.SH')::double precision AS market_sse_ma20_bias_pct,
                max(volatility20_pct) FILTER (WHERE ts_code = '000001.SH')::double precision AS market_sse_volatility20_pct,
                max(ret5_pct) FILTER (WHERE ts_code = '399303.SZ')::double precision AS market_cn2000_ret5_pct,
                max(ret20_pct) FILTER (WHERE ts_code = '399303.SZ')::double precision AS market_cn2000_ret20_pct,
                max(ma20_bias_pct) FILTER (WHERE ts_code = '399303.SZ')::double precision AS market_cn2000_ma20_bias_pct,
                max(volatility20_pct) FILTER (WHERE ts_code = '399303.SZ')::double precision AS market_cn2000_volatility20_pct,
                CASE WHEN count(ret5_pct) = 2 THEN avg(ret5_pct)::double precision END AS market_broad_ret5_pct,
                CASE WHEN count(ret20_pct) = 2 THEN avg(ret20_pct)::double precision END AS market_broad_ret20_pct,
                CASE WHEN count(ma20_bias_pct) = 2 THEN avg(ma20_bias_pct)::double precision END AS market_broad_ma20_bias_pct,
                CASE WHEN count(volatility20_pct) = 2 THEN avg(volatility20_pct)::double precision END AS market_broad_volatility20_pct
            FROM index_market_raw
            GROUP BY trade_date
        )
        SELECT
            s.ts_code,
            s.trade_date,
            s.amount::double precision AS amount,
            s.turnover_rate_f::double precision AS turnover_rate_f,
            s.volume_ratio::double precision AS volume_ratio,
            s.kdj_k_qfq::double precision AS kdj_k_qfq,
            s.kdj_d_qfq::double precision AS kdj_d_qfq,
            CASE
                WHEN s.kdj_k_qfq IS NOT NULL AND s.kdj_d_qfq IS NOT NULL
                THEN 3.0 * s.kdj_k_qfq::double precision - 2.0 * s.kdj_d_qfq::double precision
            END AS kdj_j_qfq,
            s.rsi_qfq_6::double precision AS rsi_qfq_6,
            s.rsi_qfq_12::double precision AS rsi_qfq_12,
            s.rsi_qfq_24::double precision AS rsi_qfq_24,
            s.boll_upper_qfq::double precision AS boll_upper_qfq,
            s.boll_mid_qfq::double precision AS boll_mid_qfq,
            s.boll_lower_qfq::double precision AS boll_lower_qfq,
            s.dmi_adxr_qfq::double precision AS dmi_adxr_qfq,
            s.dmi_adx_qfq::double precision AS dmi_adx_qfq,
            s.dmi_pdi_qfq::double precision AS dmi_pdi_qfq,
            s.dmi_mdi_qfq::double precision AS dmi_mdi_qfq,
            s.dmi_pdi_qfq::double precision - s.dmi_mdi_qfq::double precision AS dmi_pdi_mdi_spread_qfq,
            s.dmi_adx_qfq::double precision - s.dmi_adxr_qfq::double precision AS dmi_adx_adxr_gap_qfq,
            s.wr_qfq::double precision AS wr_qfq,
            s.mtm_qfq::double precision AS mtm_qfq,
            s.roc_qfq::double precision AS roc_qfq,
            s.trix_qfq::double precision AS trix_qfq,
            s.obv_qfq::double precision AS obv_qfq,
            s.vr_qfq::double precision AS vr_qfq,
            s.psy_qfq::double precision AS psy_qfq,
            s.bias1_qfq::double precision AS bias1_qfq,
            s.macd_dif_qfq::double precision AS tushare_macd_dif_qfq,
            s.macd_dea_qfq::double precision AS tushare_macd_dea_qfq,
            s.macd_qfq::double precision AS tushare_macd_qfq,
            s.pe::double precision AS pe,
            s.pe_ttm::double precision AS pe_ttm,
            s.pb::double precision AS pb,
            s.ps::double precision AS ps,
            s.ps_ttm::double precision AS ps_ttm,
            s.dv_ratio::double precision AS dv_ratio,
            s.total_mv::double precision AS total_mv,
            s.circ_mv::double precision AS circ_mv,
            s.total_share::double precision AS total_share,
            s.free_share::double precision AS free_share,
            a.daily_dif_asof::double precision AS macd_daily_dif,
            a.daily_dea_asof::double precision AS macd_daily_dea,
            a.daily_hist_x2_asof::double precision / 2.0 AS macd_daily_hist,
            a.daily_dea_pctile_asof::double precision AS macd_daily_dea_pctile,
            a.daily_period_count::double precision AS macd_daily_period_count,
            a.weekly_dif_asof::double precision AS macd_weekly_dif,
            a.weekly_dea_asof::double precision AS macd_weekly_dea,
            a.weekly_hist_x2_asof::double precision / 2.0 AS macd_weekly_hist,
            a.weekly_dea_pctile_asof::double precision AS macd_weekly_dea_pctile,
            a.weekly_period_count::double precision AS macd_weekly_period_count,
            a.monthly_dif_asof::double precision AS macd_monthly_dif,
            a.monthly_dea_asof::double precision AS macd_monthly_dea,
            a.monthly_hist_x2_asof::double precision / 2.0 AS macd_monthly_hist,
            a.monthly_dea_pctile_asof::double precision AS macd_monthly_dea_pctile,
            a.monthly_period_count::double precision AS macd_monthly_period_count,
            r.ma25_qfq::double precision AS rolling_ma25_qfq,
            r.ma144_qfq::double precision AS rolling_ma144_qfq,
            r.ma220_qfq::double precision AS rolling_ma220_qfq,
            r.high_20_qfq::double precision AS rolling_high_20_qfq,
            r.close_to_20d_max_close_pct::double precision AS close_to_20d_max_close_pct,
            r.high_90_qfq::double precision AS rolling_high_90_qfq,
            r.low_90_qfq::double precision AS rolling_low_90_qfq,
            r.high_120_qfq::double precision AS rolling_high_120_qfq,
            r.low_120_qfq::double precision AS rolling_low_120_qfq,
            r.position_90d::double precision AS rolling_position_90d,
            r.position_120d::double precision AS rolling_position_120d,
            r.volume_ma5::double precision AS rolling_volume_ma5,
            r.volume_ma20::double precision AS rolling_volume_ma20,
            r.volume_to_ma5_ratio::double precision AS rolling_volume_to_ma5_ratio,
            r.volume_to_ma20_ratio::double precision AS rolling_volume_to_ma20_ratio,
            r.volume_ma5_to_ma20_ratio::double precision AS rolling_volume_ma5_to_ma20_ratio,
            r.turnover_rate_ma5::double precision AS rolling_turnover_rate_ma5,
            r.turnover_to_ma5_ratio::double precision AS rolling_turnover_to_ma5_ratio,
            r.range_compression_20d::double precision AS rolling_range_compression_20d,
            r.range_compression_40d::double precision AS rolling_range_compression_40d,
            l.left_peak_high::double precision AS left_peak_high,
            l.breakout_close::double precision AS left_peak_breakout_close,
            (CASE WHEN l.breakout_body_above_left_peak THEN 1.0 ELSE 0.0 END)::double precision AS left_peak_breakout_body_above_flag,
            l.first_bear_open::double precision AS left_peak_first_bear_open,
            (CASE WHEN l.first_bear_missing THEN 1.0 ELSE 0.0 END)::double precision AS left_peak_first_bear_missing_flag,
            l.b_div_a::double precision AS left_peak_b_div_a,
            l.abs_ba_minus_1::double precision AS left_peak_abs_ba_minus_1,
            (CASE WHEN l.a_lt_b THEN 1.0 ELSE 0.0 END)::double precision AS left_peak_a_lt_b,
            (CASE WHEN l.is_valid THEN 1.0 ELSE 0.0 END)::double precision AS left_peak_valid,
            CASE WHEN l.left_peak_date IS NOT NULL THEN (s.trade_date - l.left_peak_date)::double precision END AS left_peak_days_since_peak,
            CASE WHEN l.breakout_date IS NOT NULL THEN (s.trade_date - l.breakout_date)::double precision END AS left_peak_days_since_breakout,
            CASE WHEN l.first_bear_date IS NOT NULL THEN (s.trade_date - l.first_bear_date)::double precision END AS left_peak_days_since_first_bear,
            smf.net_amount::double precision AS stock_mf_net_amount,
            smf.net_d5_amount::double precision AS stock_mf_net_d5_amount,
            smf.buy_lg_amount::double precision AS stock_mf_buy_lg_amount,
            smf.buy_lg_amount_rate::double precision AS stock_mf_buy_lg_amount_rate,
            smf.buy_md_amount::double precision AS stock_mf_buy_md_amount,
            smf.buy_md_amount_rate::double precision AS stock_mf_buy_md_amount_rate,
            smf.buy_sm_amount::double precision AS stock_mf_buy_sm_amount,
            smf.buy_sm_amount_rate::double precision AS stock_mf_buy_sm_amount_rate,
            CASE
                WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.buy_lg_amount IS NOT NULL
                THEN smf.buy_lg_amount::double precision / s.amount::double precision * 100.0
            END AS large_net_amount_to_amount_pct,
            CASE
                WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.buy_md_amount IS NOT NULL
                THEN smf.buy_md_amount::double precision / s.amount::double precision * 100.0
            END AS mid_net_amount_to_amount_pct,
            CASE
                WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.buy_sm_amount IS NOT NULL
                THEN smf.buy_sm_amount::double precision / s.amount::double precision * 100.0
            END AS small_net_amount_to_amount_pct,
            CASE
                WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.net_amount IS NOT NULL
                THEN smf.net_amount::double precision / s.amount::double precision * 100.0
            END AS net_mf_amount_to_amount_pct,
            imf.market_sse_ret5_pct,
            imf.market_sse_ret20_pct,
            imf.market_sse_ma20_bias_pct,
            imf.market_sse_volatility20_pct,
            imf.market_cn2000_ret5_pct,
            imf.market_cn2000_ret20_pct,
            imf.market_cn2000_ma20_bias_pct,
            imf.market_cn2000_volatility20_pct,
            imf.market_broad_ret5_pct,
            imf.market_broad_ret20_pct,
            imf.market_broad_ma20_bias_pct,
            imf.market_broad_volatility20_pct
        FROM stock_stk_factor_pro s
        LEFT JOIN stock_daily_asof_indicators a
          ON a.ts_code = s.ts_code
         AND a.trade_date = s.trade_date
         AND a.calc_version = 'macd_qfq_12_26_9_v1'
        LEFT JOIN stock_daily_rolling_factors r
          ON r.ts_code = s.ts_code
         AND r.trade_date = s.trade_date
         AND r.calc_version = 'rolling_qfq_v1'
        LEFT JOIN stock_daily_left_peak l
          ON l.ts_code = s.ts_code
         AND l.trade_date = s.trade_date
         AND l.calc_version = 'left_peak_qfq_v1'
        LEFT JOIN stock_moneyflow_ths smf
          ON smf.ts_code = s.ts_code
         AND smf.trade_date = s.trade_date
        LEFT JOIN index_market_factors imf
          ON imf.trade_date = s.trade_date
        WHERE s.trade_date = $1
        ";

const DB_NATIVE_THS_SECTOR_EXTRAS_QUERY: &str = "
        WITH recent_trade_dates AS (
            SELECT trade_date
            FROM (
                SELECT DISTINCT trade_date
                FROM stock_stk_factor_pro
                WHERE trade_date <= $1
                ORDER BY trade_date DESC
                LIMIT 252
            ) d
        ),
        index_market_base AS (
            SELECT
                i.ts_code,
                i.trade_date,
                i.close::double precision AS close,
                lag(i.close, 5) OVER (PARTITION BY i.ts_code ORDER BY i.trade_date)::double precision AS close_5_ago,
                lag(i.close, 20) OVER (PARTITION BY i.ts_code ORDER BY i.trade_date)::double precision AS close_20_ago,
                avg(i.close::double precision) OVER (PARTITION BY i.ts_code ORDER BY i.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS close_ma20,
                stddev_samp(i.pct_change::double precision) OVER (PARTITION BY i.ts_code ORDER BY i.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)::double precision AS volatility20_pct
            FROM index_idx_factor_pro i
            JOIN recent_trade_dates w
              ON w.trade_date = i.trade_date
            WHERE i.ts_code IN ('000001.SH', '399303.SZ')
        ),
        index_market_raw AS (
            SELECT
                ts_code,
                trade_date,
                CASE
                    WHEN close_5_ago IS NOT NULL AND close_5_ago != 0
                    THEN (close - close_5_ago) / close_5_ago * 100.0
                END AS ret5_pct,
                CASE
                    WHEN close_20_ago IS NOT NULL AND close_20_ago != 0
                    THEN (close - close_20_ago) / close_20_ago * 100.0
                END AS ret20_pct,
                CASE
                    WHEN close_ma20 IS NOT NULL AND close_ma20 != 0
                    THEN (close - close_ma20) / close_ma20 * 100.0
                END AS ma20_bias_pct,
                volatility20_pct
            FROM index_market_base
        ),
        index_market_factors AS (
            SELECT
                trade_date,
                max(ret5_pct) FILTER (WHERE ts_code = '000001.SH')::double precision AS market_sse_ret5_pct,
                max(ret20_pct) FILTER (WHERE ts_code = '000001.SH')::double precision AS market_sse_ret20_pct,
                max(ma20_bias_pct) FILTER (WHERE ts_code = '000001.SH')::double precision AS market_sse_ma20_bias_pct,
                max(volatility20_pct) FILTER (WHERE ts_code = '000001.SH')::double precision AS market_sse_volatility20_pct,
                max(ret5_pct) FILTER (WHERE ts_code = '399303.SZ')::double precision AS market_cn2000_ret5_pct,
                max(ret20_pct) FILTER (WHERE ts_code = '399303.SZ')::double precision AS market_cn2000_ret20_pct,
                max(ma20_bias_pct) FILTER (WHERE ts_code = '399303.SZ')::double precision AS market_cn2000_ma20_bias_pct,
                max(volatility20_pct) FILTER (WHERE ts_code = '399303.SZ')::double precision AS market_cn2000_volatility20_pct,
                CASE WHEN count(ret5_pct) = 2 THEN avg(ret5_pct)::double precision END AS market_broad_ret5_pct,
                CASE WHEN count(ret20_pct) = 2 THEN avg(ret20_pct)::double precision END AS market_broad_ret20_pct,
                CASE WHEN count(ma20_bias_pct) = 2 THEN avg(ma20_bias_pct)::double precision END AS market_broad_ma20_bias_pct,
                CASE WHEN count(volatility20_pct) = 2 THEN avg(volatility20_pct)::double precision END AS market_broad_volatility20_pct
            FROM index_market_raw
            GROUP BY trade_date
        ),
        index_limit_cpt_daily AS (
            SELECT
                ts_code,
                trade_date,
                max(up_nums)::double precision AS up_nums,
                max(days)::double precision AS days,
                max(pct_chg)::double precision AS pct_chg,
                min(rank)::double precision AS rank
            FROM index_limit_cpt_list
            WHERE trade_date = $1
            GROUP BY ts_code, trade_date
        ),
        current_ths_membership AS (
            SELECT
                ts_code,
                con_code
            FROM index_ths_member
        ),
        ths_sector_base AS (
            SELECT
                d.ts_code,
                d.trade_date,
                d.close::double precision AS close,
                lag(d.close, 5) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date)::double precision AS ths_close_5_ago,
                lag(d.close, 20) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date)::double precision AS ths_close_20_ago,
                avg(d.close::double precision) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ths_close_ma20
            FROM index_ths_daily d
            JOIN recent_trade_dates w
              ON w.trade_date = d.trade_date
        ),
        ths_sector_rolling AS (
            SELECT
                ts_code,
                trade_date,
                CASE
                    WHEN ths_close_5_ago IS NOT NULL AND ths_close_5_ago != 0
                    THEN (close - ths_close_5_ago) / ths_close_5_ago * 100.0
                END AS ths_ret5_pct,
                CASE
                    WHEN ths_close_20_ago IS NOT NULL AND ths_close_20_ago != 0
                    THEN (close - ths_close_20_ago) / ths_close_20_ago * 100.0
                END AS ths_ret20_pct,
                CASE
                    WHEN ths_close_ma20 IS NOT NULL AND ths_close_ma20 != 0
                    THEN (close - ths_close_ma20) / ths_close_ma20 * 100.0
                END AS ths_ma20_bias_pct
            FROM ths_sector_base
        ),
        ths_sector_daily AS (
            SELECT
                d.ts_code AS ths_ts_code,
                d.trade_date,
                d.pct_change::double precision AS ths_pct_change,
                tr.ths_ret5_pct,
                tr.ths_ret20_pct,
                tr.ths_ma20_bias_pct,
                d.vol::double precision AS ths_vol,
                d.turnover_rate::double precision AS ths_turnover_rate,
                d.total_mv::double precision AS ths_total_mv,
                d.float_mv::double precision AS ths_float_mv,
                mf.net_amount::double precision AS ths_net_amount,
                mf.net_buy_amount::double precision AS ths_net_buy_amount,
                mf.net_sell_amount::double precision AS ths_net_sell_amount,
                il.up_nums::double precision AS ths_limit_up_count,
                il.days::double precision AS ths_limit_days,
                il.pct_chg::double precision AS ths_limit_pct_chg,
                il.rank::double precision AS ths_limit_rank,
                mf.pct_change_stock::double precision AS ths_lead_stock_pct_change,
                ia.daily_dif_asof::double precision AS ths_macd_daily_dif,
                ia.daily_dea_asof::double precision AS ths_macd_daily_dea,
                ia.daily_hist_x2_asof::double precision / 2.0 AS ths_macd_daily_hist,
                ia.weekly_dif_asof::double precision AS ths_macd_weekly_dif,
                ia.weekly_dea_asof::double precision AS ths_macd_weekly_dea,
                ia.weekly_hist_x2_asof::double precision / 2.0 AS ths_macd_weekly_hist,
                ia.monthly_dif_asof::double precision AS ths_macd_monthly_dif,
                ia.monthly_dea_asof::double precision AS ths_macd_monthly_dea,
                ia.monthly_hist_x2_asof::double precision / 2.0 AS ths_macd_monthly_hist,
                ROW_NUMBER() OVER (
                    PARTITION BY d.trade_date
                    ORDER BY mf.net_amount DESC NULLS LAST, d.pct_change DESC NULLS LAST, d.ts_code ASC
                )::double precision AS ths_sector_rank
            FROM index_ths_daily d
            LEFT JOIN index_moneyflow_cnt_ths mf
              ON mf.ts_code = d.ts_code
             AND mf.trade_date = d.trade_date
            LEFT JOIN index_limit_cpt_daily il
              ON il.ts_code = d.ts_code
             AND il.trade_date = d.trade_date
            LEFT JOIN index_daily_asof_indicators ia
              ON ia.ts_code = d.ts_code
             AND ia.trade_date = d.trade_date
             AND ia.calc_version = 'macd_qfq_12_26_9_v1'
            LEFT JOIN ths_sector_rolling tr
              ON tr.ts_code = d.ts_code
             AND tr.trade_date = d.trade_date
            WHERE d.trade_date = $1
        ),
        stock_ths_sector_candidates AS (
            SELECT
                s.ts_code,
                s.trade_date,
                s.pct_chg::double precision AS stock_pct_chg,
                td.ths_ts_code,
                td.ths_sector_rank,
                td.ths_pct_change,
                td.ths_ret5_pct,
                td.ths_ret20_pct,
                td.ths_ma20_bias_pct,
                td.ths_vol,
                td.ths_turnover_rate,
                td.ths_total_mv,
                td.ths_float_mv,
                td.ths_net_amount,
                td.ths_net_buy_amount,
                td.ths_net_sell_amount,
                td.ths_limit_up_count,
                td.ths_limit_days,
                td.ths_limit_pct_chg,
                td.ths_limit_rank,
                td.ths_lead_stock_pct_change,
                td.ths_macd_daily_dif,
                td.ths_macd_daily_dea,
                td.ths_macd_daily_hist,
                td.ths_macd_weekly_dif,
                td.ths_macd_weekly_dea,
                td.ths_macd_weekly_hist,
                td.ths_macd_monthly_dif,
                td.ths_macd_monthly_dea,
                td.ths_macd_monthly_hist,
                ROW_NUMBER() OVER (
                    PARTITION BY s.ts_code, s.trade_date
                    ORDER BY ths_sector_rank ASC NULLS LAST, ths_net_amount DESC NULLS LAST, ths_pct_change DESC NULLS LAST, ths_ts_code ASC
                ) AS sector_choice_rank
            FROM stock_stk_factor_pro s
            JOIN current_ths_membership cm
              ON cm.con_code = s.ts_code
            JOIN ths_sector_daily td
              ON td.ths_ts_code = cm.ts_code
             AND td.trade_date = s.trade_date
            WHERE s.trade_date = $1
        ),
        stock_ths_main_sector AS (
            SELECT *
            FROM stock_ths_sector_candidates
            WHERE sector_choice_rank = 1
        ),
        stock_ths_sector_agg AS (
            SELECT
                ts_code,
                trade_date,
                COUNT(*)::double precision AS ths_sector_count,
                MAX(ths_pct_change) AS ths_best_pct_change,
                AVG(ths_pct_change) AS ths_avg_pct_change,
                MAX(ths_net_amount) AS ths_best_net_amount,
                AVG(ths_net_amount) AS ths_avg_net_amount,
                MAX(ths_net_buy_amount) AS ths_best_net_buy_amount,
                AVG(ths_net_buy_amount) AS ths_avg_net_buy_amount,
                MAX(ths_net_sell_amount) AS ths_best_net_sell_amount,
                AVG(ths_net_sell_amount) AS ths_avg_net_sell_amount,
                MAX(ths_limit_up_count) AS ths_best_limit_up_count,
                AVG(ths_limit_up_count) AS ths_avg_limit_up_count,
                MAX(
                    CASE
                        WHEN ths_limit_up_count IS NOT NULL AND ths_limit_up_count > 0
                        THEN 1.0
                        ELSE 0.0
                    END
                )::double precision AS ths_any_limit_up_sector_flag,
                SUM(
                    CASE
                        WHEN ths_limit_up_count IS NOT NULL AND ths_limit_up_count > 0
                        THEN 1.0
                        ELSE 0.0
                    END
                )::double precision AS ths_limit_up_sector_count,
                AVG(
                    CASE
                        WHEN ths_limit_up_count IS NOT NULL AND ths_limit_up_count > 0
                        THEN 1.0
                        ELSE 0.0
                    END
                )::double precision AS ths_limit_up_sector_ratio,
                MAX(ths_limit_days) AS ths_best_limit_days,
                MAX(ths_limit_pct_chg) AS ths_best_limit_pct_chg,
                AVG(ths_limit_pct_chg) AS ths_avg_limit_pct_chg,
                MIN(ths_limit_rank) AS ths_best_limit_rank
            FROM stock_ths_sector_candidates
            GROUP BY ts_code, trade_date
        )
        SELECT
            COALESCE(m.ts_code, ta.ts_code) AS ts_code,
            COALESCE(m.trade_date, ta.trade_date) AS trade_date,
            m.ths_ts_code AS ths_main_sector_code,
            (CASE WHEN m.ths_ts_code IS NOT NULL THEN 1.0 ELSE 0.0 END)::double precision AS ths_membership_current_flag,
                m.ths_sector_rank::double precision AS ths_main_sector_rank,
            m.ths_pct_change AS ths_main_pct_change,
            m.ths_ret5_pct AS stock_env_sector_ret5_pct,
            m.ths_ret20_pct AS stock_env_sector_ret20_pct,
            m.ths_ma20_bias_pct AS stock_env_sector_ma20_bias_pct,
            m.ths_vol AS ths_main_vol,
            m.ths_turnover_rate AS ths_main_turnover_rate,
            m.ths_total_mv AS ths_main_total_mv,
            m.ths_float_mv AS ths_main_float_mv,
            m.ths_net_amount AS ths_main_net_amount,
            m.ths_net_buy_amount AS ths_main_net_buy_amount,
            m.ths_net_sell_amount AS ths_main_net_sell_amount,
            m.ths_limit_up_count AS ths_main_limit_up_count,
            m.ths_limit_days AS ths_main_limit_days,
            m.ths_limit_pct_chg AS ths_main_limit_pct_chg,
            m.ths_limit_rank AS ths_main_limit_rank,
            m.ths_lead_stock_pct_change AS ths_main_lead_stock_pct_change,
            m.ths_macd_daily_dif AS ths_main_macd_daily_dif,
            m.ths_macd_daily_dea AS ths_main_macd_daily_dea,
            m.ths_macd_daily_hist AS ths_main_macd_daily_hist,
            m.ths_macd_weekly_dif AS ths_main_macd_weekly_dif,
            m.ths_macd_weekly_dea AS ths_main_macd_weekly_dea,
            m.ths_macd_weekly_hist AS ths_main_macd_weekly_hist,
            m.ths_macd_monthly_dif AS ths_main_macd_monthly_dif,
            m.ths_macd_monthly_dea AS ths_main_macd_monthly_dea,
            m.ths_macd_monthly_hist AS ths_main_macd_monthly_hist,
            ta.ths_sector_count::double precision AS ths_sector_count,
            ta.ths_best_pct_change AS ths_best_pct_change,
            ta.ths_avg_pct_change AS ths_avg_pct_change,
            ta.ths_best_net_amount AS ths_best_net_amount,
            ta.ths_avg_net_amount AS ths_avg_net_amount,
            ta.ths_best_net_buy_amount AS ths_best_net_buy_amount,
            ta.ths_avg_net_buy_amount AS ths_avg_net_buy_amount,
            ta.ths_best_net_sell_amount AS ths_best_net_sell_amount,
            ta.ths_avg_net_sell_amount AS ths_avg_net_sell_amount,
            ta.ths_best_limit_up_count AS ths_best_limit_up_count,
            ta.ths_avg_limit_up_count AS ths_avg_limit_up_count,
            ta.ths_any_limit_up_sector_flag AS ths_any_limit_up_sector_flag,
            ta.ths_limit_up_sector_count AS ths_limit_up_sector_count,
            ta.ths_limit_up_sector_ratio AS ths_limit_up_sector_ratio,
            ta.ths_best_limit_days AS ths_best_limit_days,
            ta.ths_best_limit_pct_chg AS ths_best_limit_pct_chg,
            ta.ths_avg_limit_pct_chg AS ths_avg_limit_pct_chg,
            ta.ths_best_limit_rank AS ths_best_limit_rank,
            m.stock_pct_chg - m.ths_pct_change AS stock_vs_ths_main_pct_change,
            m.stock_pct_chg - ta.ths_avg_pct_change AS stock_vs_ths_avg_pct_change,
            m.ths_ret5_pct - imf.market_broad_ret5_pct AS stock_env_sector_vs_broad_ret5_pct,
            m.ths_ret20_pct - imf.market_broad_ret20_pct AS stock_env_sector_vs_broad_ret20_pct,
            imf.market_cn2000_ret5_pct - imf.market_sse_ret5_pct AS stock_env_style_ret5_spread_pct,
            m.ths_ret5_pct + imf.market_broad_ret5_pct AS stock_env_market_sector_ret5_sum_pct,
            (
                COALESCE(imf.market_broad_ret5_pct, 0.0) * 0.5
                + COALESCE(imf.market_broad_ma20_bias_pct, 0.0) * 0.3
                - COALESCE(imf.market_broad_volatility20_pct, 0.0) * 0.2
            )::double precision AS stock_env_market_score,
            (
                COALESCE(m.ths_ret5_pct, 0.0) * 0.45
                + COALESCE(m.ths_ma20_bias_pct, 0.0) * 0.25
                + COALESCE(m.ths_pct_change, 0.0) * 0.15
                + COALESCE(m.ths_net_amount, 0.0) * 0.0000000001
            )::double precision AS stock_env_sector_score,
            (
                CASE
                    WHEN imf.market_broad_ret5_pct IS NOT NULL
                     AND m.ths_ret5_pct IS NOT NULL
                     AND imf.market_broad_ret5_pct > 0
                     AND m.ths_ret5_pct > 0
                    THEN 1.0
                    WHEN imf.market_broad_ret5_pct IS NOT NULL
                     AND m.ths_ret5_pct IS NOT NULL
                     AND imf.market_broad_ret5_pct < 0
                     AND m.ths_ret5_pct < 0
                    THEN -1.0
                    WHEN imf.market_broad_ret5_pct IS NOT NULL
                     AND m.ths_ret5_pct IS NOT NULL
                    THEN 0.0
                END
            )::double precision AS stock_env_alignment_score,
            (
                COALESCE(ta.ths_limit_up_sector_ratio, 0.0) * 2.0
                + COALESCE(ta.ths_limit_up_sector_count, 0.0) * 0.2
                + COALESCE(ta.ths_best_limit_up_count, 0.0) * 0.05
            )::double precision AS stock_env_limit_heat_score,
            (
                COALESCE(imf.market_broad_ret5_pct, 0.0) * 0.25
                + COALESCE(imf.market_broad_ma20_bias_pct, 0.0) * 0.15
                - COALESCE(imf.market_broad_volatility20_pct, 0.0) * 0.10
                + COALESCE(m.ths_ret5_pct, 0.0) * 0.25
                + COALESCE(m.ths_ma20_bias_pct, 0.0) * 0.15
                + COALESCE(ta.ths_limit_up_sector_ratio, 0.0) * 0.8
                + COALESCE(ta.ths_limit_up_sector_count, 0.0) * 0.08
            )::double precision AS stock_env_overall_score
        FROM stock_ths_main_sector m
        FULL OUTER JOIN stock_ths_sector_agg ta
          ON ta.ts_code = m.ts_code
         AND ta.trade_date = m.trade_date
        LEFT JOIN index_market_factors imf
          ON imf.trade_date = COALESCE(m.trade_date, ta.trade_date)
        ORDER BY ts_code ASC, trade_date ASC
        ";

const DB_NATIVE_COVERAGE_PROBE_QUERY: &str = "
        WITH trading_window AS (
            SELECT DISTINCT trade_date
            FROM stock_stk_factor_pro
            WHERE trade_date BETWEEN ($1::date - INTERVAL '1 year')::date AND $1
        )
        SELECT
            (SELECT min(trade_date) FROM trading_window) AS window_start_date,
            (SELECT max(trade_date) FROM trading_window) AS window_end_date,
            (SELECT count(*) FROM trading_window) AS window_trade_dates,
            (SELECT count(*) FROM stock_stk_factor_pro WHERE trade_date = $1) AS stock_factor_rows,
            (
                SELECT count(*)
                FROM stock_daily_asof_indicators
                WHERE trade_date = $1
                  AND calc_version = 'macd_qfq_12_26_9_v1'
            ) AS stock_macd_rows,
            (
                SELECT count(*)
                FROM stock_daily_rolling_factors
                WHERE trade_date = $1
                  AND calc_version = 'rolling_qfq_v1'
            ) AS stock_rolling_rows,
            (
                SELECT count(*)
                FROM stock_daily_left_peak
                WHERE trade_date = $1
                  AND calc_version = 'left_peak_qfq_v1'
            ) AS stock_left_peak_rows,
            (SELECT count(*) FROM stock_moneyflow_ths WHERE trade_date = $1) AS stock_moneyflow_rows,
            (SELECT count(*) FROM index_ths_daily WHERE trade_date = $1) AS index_ths_daily_rows,
            (SELECT count(*) FROM index_idx_factor_pro WHERE trade_date = $1 AND ts_code IN ('000001.SH', '399303.SZ')) AS index_market_rows,
            (
                SELECT count(*)
                FROM index_daily_asof_indicators
                WHERE trade_date = $1
                  AND calc_version = 'macd_qfq_12_26_9_v1'
            ) AS index_macd_rows,
            (SELECT count(*) FROM index_moneyflow_cnt_ths WHERE trade_date = $1) AS index_moneyflow_rows,
            (SELECT count(*) FROM index_limit_cpt_list WHERE trade_date = $1) AS index_limit_rows
        ";

const PREVIOUS_TRADE_DATE_QUERY: &str = "
        SELECT max(trade_date) AS trade_date
        FROM stock_stk_factor_pro
        WHERE trade_date < $1
        ";

const STOCK_PERIOD_MACD_STATE_QUERY: &str = "
        SELECT DISTINCT ON (p.ts_code, p.period_type)
            p.ts_code,
            p.period_type,
            p.ema12::double precision AS ema12,
            p.ema26::double precision AS ema26,
            p.dea::double precision AS dea,
            p.period_count::integer AS period_count
        FROM stock_period_indicator_state p
        WHERE p.ts_code = ANY($1)
          AND p.period_type IN ('daily', 'weekly', 'monthly')
          AND p.period_end_date < $2
          AND p.calc_version = 'macd_qfq_12_26_9_v1'
          AND p.period_count IS NOT NULL
        ORDER BY p.ts_code, p.period_type, p.period_end_date DESC
        ";

const INSTRUMENT_INFO_QUERY: &str = "
        SELECT
            con_code AS ts_code,
            max(con_name) AS name,
            NULL::text AS industry
        FROM index_ths_member
        WHERE con_code = ANY($1)
        GROUP BY con_code
        ORDER BY con_code ASC
        ";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DbNativeCoverageProbe {
    pub pick_date: NaiveDate,
    pub window_start_date: Option<NaiveDate>,
    pub window_end_date: Option<NaiveDate>,
    pub window_trade_dates: i64,
    pub stock_factor_rows: i64,
    pub stock_macd_rows: i64,
    pub stock_rolling_rows: i64,
    pub stock_left_peak_rows: i64,
    pub stock_moneyflow_rows: i64,
    pub index_ths_daily_rows: i64,
    pub index_market_rows: i64,
    pub index_macd_rows: i64,
    pub index_moneyflow_rows: i64,
    pub index_limit_rows: i64,
}

#[derive(Debug, Clone, PartialEq)]
struct DbNativeDailyRow {
    ts_code: String,
    trade_date: NaiveDate,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    adj_factor: Option<f64>,
    vol: f64,
    turnover_rate: Option<f64>,
    db_factors: BTreeMap<String, Option<f64>>,
}

const DB_NATIVE_FACTOR_COLUMNS: &[&str] = &["amount"];

const DB_NATIVE_PICK_DATE_FACTOR_COLUMNS: &[&str] = &[
    "amount",
    "turnover_rate_f",
    "volume_ratio",
    "kdj_k_qfq",
    "kdj_d_qfq",
    "kdj_j_qfq",
    "rsi_qfq_6",
    "rsi_qfq_12",
    "rsi_qfq_24",
    "boll_upper_qfq",
    "boll_mid_qfq",
    "boll_lower_qfq",
    "dmi_adxr_qfq",
    "dmi_adx_qfq",
    "dmi_pdi_qfq",
    "dmi_mdi_qfq",
    "dmi_pdi_mdi_spread_qfq",
    "dmi_adx_adxr_gap_qfq",
    "wr_qfq",
    "mtm_qfq",
    "roc_qfq",
    "trix_qfq",
    "obv_qfq",
    "vr_qfq",
    "psy_qfq",
    "bias1_qfq",
    "tushare_macd_dif_qfq",
    "tushare_macd_dea_qfq",
    "tushare_macd_qfq",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "dv_ratio",
    "total_mv",
    "circ_mv",
    "total_share",
    "free_share",
    "macd_daily_dif",
    "macd_daily_dea",
    "macd_daily_hist",
    "macd_daily_dea_pctile",
    "macd_daily_period_count",
    "macd_weekly_dif",
    "macd_weekly_dea",
    "macd_weekly_hist",
    "macd_weekly_dea_pctile",
    "macd_weekly_period_count",
    "macd_monthly_dif",
    "macd_monthly_dea",
    "macd_monthly_hist",
    "macd_monthly_dea_pctile",
    "macd_monthly_period_count",
    "rolling_ma25_qfq",
    "rolling_ma144_qfq",
    "rolling_ma220_qfq",
    "rolling_high_20_qfq",
    "close_to_20d_max_close_pct",
    "rolling_high_90_qfq",
    "rolling_low_90_qfq",
    "rolling_high_120_qfq",
    "rolling_low_120_qfq",
    "rolling_position_90d",
    "rolling_position_120d",
    "rolling_volume_ma5",
    "rolling_volume_ma20",
    "rolling_volume_to_ma5_ratio",
    "rolling_volume_to_ma20_ratio",
    "rolling_volume_ma5_to_ma20_ratio",
    "rolling_turnover_rate_ma5",
    "rolling_turnover_to_ma5_ratio",
    "rolling_range_compression_20d",
    "rolling_range_compression_40d",
    "left_peak_high",
    "left_peak_breakout_close",
    "left_peak_breakout_body_above_flag",
    "left_peak_first_bear_open",
    "left_peak_first_bear_missing_flag",
    "left_peak_b_div_a",
    "left_peak_abs_ba_minus_1",
    "left_peak_a_lt_b",
    "left_peak_valid",
    "left_peak_days_since_peak",
    "left_peak_days_since_breakout",
    "left_peak_days_since_first_bear",
    "stock_mf_net_amount",
    "stock_mf_net_d5_amount",
    "stock_mf_buy_lg_amount",
    "stock_mf_buy_lg_amount_rate",
    "stock_mf_buy_md_amount",
    "stock_mf_buy_md_amount_rate",
    "stock_mf_buy_sm_amount",
    "stock_mf_buy_sm_amount_rate",
    "large_net_amount_to_amount_pct",
    "mid_net_amount_to_amount_pct",
    "small_net_amount_to_amount_pct",
    "net_mf_amount_to_amount_pct",
    "market_sse_ret5_pct",
    "market_sse_ret20_pct",
    "market_sse_ma20_bias_pct",
    "market_sse_volatility20_pct",
    "market_cn2000_ret5_pct",
    "market_cn2000_ret20_pct",
    "market_cn2000_ma20_bias_pct",
    "market_cn2000_volatility20_pct",
    "market_broad_ret5_pct",
    "market_broad_ret20_pct",
    "market_broad_ma20_bias_pct",
    "market_broad_volatility20_pct",
];

const DB_NATIVE_THS_SECTOR_FACTOR_COLUMNS: &[&str] = &[
    "ths_membership_current_flag",
    "ths_main_sector_rank",
    "ths_main_pct_change",
    "ths_main_vol",
    "ths_main_turnover_rate",
    "ths_main_total_mv",
    "ths_main_float_mv",
    "ths_main_net_amount",
    "ths_main_net_buy_amount",
    "ths_main_net_sell_amount",
    "ths_main_limit_up_count",
    "ths_main_limit_days",
    "ths_main_limit_pct_chg",
    "ths_main_limit_rank",
    "ths_main_lead_stock_pct_change",
    "ths_main_macd_daily_dif",
    "ths_main_macd_daily_dea",
    "ths_main_macd_daily_hist",
    "ths_main_macd_weekly_dif",
    "ths_main_macd_weekly_dea",
    "ths_main_macd_weekly_hist",
    "ths_main_macd_monthly_dif",
    "ths_main_macd_monthly_dea",
    "ths_main_macd_monthly_hist",
    "ths_sector_count",
    "ths_best_pct_change",
    "ths_avg_pct_change",
    "ths_best_net_amount",
    "ths_avg_net_amount",
    "ths_best_net_buy_amount",
    "ths_avg_net_buy_amount",
    "ths_best_net_sell_amount",
    "ths_avg_net_sell_amount",
    "ths_best_limit_up_count",
    "ths_avg_limit_up_count",
    "ths_any_limit_up_sector_flag",
    "ths_limit_up_sector_count",
    "ths_limit_up_sector_ratio",
    "ths_best_limit_days",
    "ths_best_limit_pct_chg",
    "ths_avg_limit_pct_chg",
    "ths_best_limit_rank",
    "stock_vs_ths_main_pct_change",
    "stock_vs_ths_avg_pct_change",
    "stock_env_sector_ret5_pct",
    "stock_env_sector_ret20_pct",
    "stock_env_sector_ma20_bias_pct",
    "stock_env_sector_vs_broad_ret5_pct",
    "stock_env_sector_vs_broad_ret20_pct",
    "stock_env_style_ret5_spread_pct",
    "stock_env_market_sector_ret5_sum_pct",
    "stock_env_market_score",
    "stock_env_sector_score",
    "stock_env_alignment_score",
    "stock_env_limit_heat_score",
    "stock_env_overall_score",
];

pub fn probe_db_native_coverage(
    dsn: &str,
    pick_date: NaiveDate,
) -> anyhow::Result<DbNativeCoverageProbe> {
    let mut client = Client::connect(dsn, NoTls)?;
    probe_db_native_coverage_with_client(&mut client, pick_date)
}

pub fn fetch_db_native_daily_window(
    dsn: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Vec<MarketRow>> {
    let mut client = Client::connect(dsn, NoTls)?;
    configure_daily_window_session(&mut client)?;
    let probe = probe_db_native_coverage_with_client(&mut client, end_date)?;
    ensure_db_native_required_coverage(&probe)?;

    let mut market_rows = Vec::new();
    {
        let mut rows = client.query_raw(DB_NATIVE_DAILY_WINDOW_QUERY, &[&start_date, &end_date])?;
        while let Some(row) = rows.next()? {
            market_rows.push(db_native_market_row_from_db_row(row)?);
        }
    }
    merge_pick_date_extras(&mut client, end_date, &mut market_rows)?;
    merge_ths_sector_extras(&mut client, end_date, &mut market_rows)?;
    Ok(market_rows)
}

pub fn fetch_stock_period_macd_states(
    dsn: &str,
    symbols: &[String],
    pick_date: NaiveDate,
) -> anyhow::Result<Vec<MacdPeriodState>> {
    if symbols.is_empty() {
        return Ok(Vec::new());
    }
    let mut client = Client::connect(dsn, NoTls)?;
    let rows = client.query(STOCK_PERIOD_MACD_STATE_QUERY, &[&symbols, &pick_date])?;
    rows.into_iter()
        .map(|row| {
            Ok(MacdPeriodState {
                ts_code: row.try_get("ts_code")?,
                period_type: row.try_get("period_type")?,
                ema12: optional_f64(&row, "ema12")?,
                ema26: optional_f64(&row, "ema26")?,
                dea: optional_f64(&row, "dea")?,
                period_count: row.try_get("period_count")?,
            })
        })
        .collect()
}

fn probe_db_native_coverage_with_client(
    client: &mut Client,
    pick_date: NaiveDate,
) -> anyhow::Result<DbNativeCoverageProbe> {
    let row = client.query_one(DB_NATIVE_COVERAGE_PROBE_QUERY, &[&pick_date])?;
    Ok(DbNativeCoverageProbe {
        pick_date,
        window_start_date: row.try_get("window_start_date")?,
        window_end_date: row.try_get("window_end_date")?,
        window_trade_dates: row.try_get("window_trade_dates")?,
        stock_factor_rows: row.try_get("stock_factor_rows")?,
        stock_macd_rows: row.try_get("stock_macd_rows")?,
        stock_rolling_rows: row.try_get("stock_rolling_rows")?,
        stock_left_peak_rows: row.try_get("stock_left_peak_rows")?,
        stock_moneyflow_rows: row.try_get("stock_moneyflow_rows")?,
        index_ths_daily_rows: row.try_get("index_ths_daily_rows")?,
        index_market_rows: row.try_get("index_market_rows")?,
        index_macd_rows: row.try_get("index_macd_rows")?,
        index_moneyflow_rows: row.try_get("index_moneyflow_rows")?,
        index_limit_rows: row.try_get("index_limit_rows")?,
    })
}

fn ensure_db_native_required_coverage(probe: &DbNativeCoverageProbe) -> anyhow::Result<()> {
    let mut missing = Vec::new();
    let requested_start = db_native_coverage_start_date(probe.pick_date);
    if !probe
        .window_start_date
        .is_some_and(|actual_start| actual_start >= requested_start)
        || probe.window_end_date != Some(probe.pick_date)
        || probe.window_trade_dates < MIN_DB_NATIVE_WINDOW_TRADE_DATES
    {
        missing.push("requested prepared window");
    }
    if probe.stock_factor_rows == 0 {
        missing.push("stock_stk_factor_pro pick-date rows");
    }
    if probe.stock_macd_rows == 0 {
        missing.push("stock_daily_asof_indicators calc_version macd_qfq_12_26_9_v1");
    }
    if probe.stock_rolling_rows == 0 {
        missing.push("stock_daily_rolling_factors calc_version rolling_qfq_v1");
    }
    if probe.stock_left_peak_rows == 0 {
        missing.push("stock_daily_left_peak calc_version left_peak_qfq_v1");
    }
    if probe.stock_moneyflow_rows == 0 {
        missing.push("stock_moneyflow_ths pick-date rows");
    }
    if probe.index_ths_daily_rows == 0 {
        missing.push("index_ths_daily pick-date rows");
    }
    if probe.index_market_rows < 2 {
        missing.push("index_idx_factor_pro pick-date rows for 000001.SH and 399303.SZ");
    }
    if probe.index_macd_rows == 0 {
        missing.push("index_daily_asof_indicators calc_version macd_qfq_12_26_9_v1");
    }
    if probe.index_moneyflow_rows == 0 {
        missing.push("index_moneyflow_cnt_ths pick-date rows");
    }
    if probe.index_limit_rows == 0 {
        missing.push("index_limit_cpt_list pick-date rows");
    }
    if missing.is_empty() {
        Ok(())
    } else {
        anyhow::bail!(
            "DB-native coverage missing for pick_date {}: {}",
            probe.pick_date,
            missing.join(", ")
        );
    }
}

fn db_native_coverage_start_date(pick_date: NaiveDate) -> NaiveDate {
    pick_date
        .with_year(pick_date.year() - 1)
        .unwrap_or_else(|| NaiveDate::from_ymd_opt(pick_date.year() - 1, 2, 28).unwrap())
}

fn db_native_market_row_from_db_row(row: postgres::Row) -> anyhow::Result<MarketRow> {
    let mut db_factors = BTreeMap::new();
    for column in DB_NATIVE_FACTOR_COLUMNS {
        db_factors.insert((*column).to_string(), optional_option_f64(&row, column)?);
    }
    db_native_market_row_from_values(DbNativeDailyRow {
        ts_code: row.try_get("ts_code")?,
        trade_date: row.try_get("trade_date")?,
        open: optional_f64(&row, "open")?,
        high: optional_f64(&row, "high")?,
        low: optional_f64(&row, "low")?,
        close: optional_f64(&row, "close")?,
        adj_factor: optional_option_f64(&row, "adj_factor")?,
        vol: optional_f64(&row, "vol")?,
        turnover_rate: optional_option_f64(&row, "turnover_rate")?,
        db_factors,
    })
}

fn merge_pick_date_extras(
    client: &mut Client,
    end_date: NaiveDate,
    market_rows: &mut [MarketRow],
) -> anyhow::Result<()> {
    let mut extras_by_key: BTreeMap<(String, NaiveDate), BTreeMap<String, f64>> = BTreeMap::new();
    let rows = client.query(DB_NATIVE_PICK_DATE_EXTRAS_QUERY, &[&end_date])?;
    for row in rows {
        let ts_code: String = row.try_get("ts_code")?;
        let trade_date: NaiveDate = row.try_get("trade_date")?;
        let mut factors = BTreeMap::new();
        for column in DB_NATIVE_PICK_DATE_FACTOR_COLUMNS {
            if let Some(value) = optional_option_f64(&row, column)? {
                if value.is_finite() {
                    factors.insert((*column).to_string(), value);
                }
            }
        }
        if !factors.is_empty() {
            extras_by_key.insert((ts_code, trade_date), factors);
        }
    }
    for row in market_rows.iter_mut().filter(|row| row.trade_date == end_date) {
        if let Some(extras) = extras_by_key.remove(&(row.ts_code.clone(), row.trade_date)) {
            row.db_factors.extend(extras);
        }
    }
    Ok(())
}

fn merge_ths_sector_extras(
    client: &mut Client,
    end_date: NaiveDate,
    market_rows: &mut [MarketRow],
) -> anyhow::Result<()> {
    let mut extras_by_key: BTreeMap<(String, NaiveDate), BTreeMap<String, f64>> = BTreeMap::new();
    let rows = client.query(DB_NATIVE_THS_SECTOR_EXTRAS_QUERY, &[&end_date])?;
    for row in rows {
        let ts_code: String = row.try_get("ts_code")?;
        let trade_date: NaiveDate = row.try_get("trade_date")?;
        let mut factors = BTreeMap::new();
        for column in DB_NATIVE_THS_SECTOR_FACTOR_COLUMNS {
            if let Some(value) = optional_option_f64(&row, column)? {
                if value.is_finite() {
                    factors.insert((*column).to_string(), value);
                }
            }
        }
        if !factors.is_empty() {
            extras_by_key.insert((ts_code, trade_date), factors);
        }
    }
    for row in market_rows {
        if let Some(extras) = extras_by_key.remove(&(row.ts_code.clone(), row.trade_date)) {
            row.db_factors.extend(extras);
        }
    }
    Ok(())
}

fn db_native_market_row_from_values(row: DbNativeDailyRow) -> anyhow::Result<MarketRow> {
    Ok(MarketRow {
        ts_code: row.ts_code,
        trade_date: row.trade_date,
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close,
        vol: row.vol,
        turnover_rate: row.turnover_rate,
        adj_factor: row.adj_factor,
        db_factors: db_factor_values_iter(row.db_factors),
    })
}

fn configure_daily_window_session(client: &mut Client) -> anyhow::Result<()> {
    client.batch_execute(DAILY_WINDOW_SESSION_SETTINGS_SQL)?;
    Ok(())
}

pub fn fetch_index_history(
    dsn: &str,
    ts_code: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Vec<MarketRow>> {
    let mut client = Client::connect(dsn, NoTls)?;
    let rows = client.query(
        "
        SELECT
            ts_code,
            trade_date,
            open::double precision AS open,
            high::double precision AS high,
            low::double precision AS low,
            close::double precision AS close,
            vol::double precision AS vol
        FROM daily_index
        WHERE ts_code = $1
          AND trade_date BETWEEN $2 AND $3
        ORDER BY trade_date ASC
        ",
        &[&ts_code, &start_date, &end_date],
    )?;
    rows.into_iter()
        .map(|row| {
            Ok(MarketRow {
                ts_code: row.try_get("ts_code")?,
                trade_date: row.try_get("trade_date")?,
                open: optional_f64(&row, "open")?,
                high: optional_f64(&row, "high")?,
                low: optional_f64(&row, "low")?,
                close: optional_f64(&row, "close")?,
                vol: optional_f64(&row, "vol")?,
                turnover_rate: None,
                adj_factor: None,
                db_factors: BTreeMap::new(),
            })
        })
        .collect()
}

pub fn resolve_previous_trade_date(dsn: &str, trade_date: NaiveDate) -> anyhow::Result<NaiveDate> {
    let mut client = Client::connect(dsn, NoTls)?;
    let row = client.query_one(PREVIOUS_TRADE_DATE_QUERY, &[&trade_date])?;
    row.try_get::<_, Option<NaiveDate>>("trade_date")?
        .ok_or_else(|| anyhow::anyhow!("No previous trade date found before {trade_date}."))
}

pub fn fetch_instrument_info(
    dsn: &str,
    symbols: &[String],
) -> anyhow::Result<BTreeMap<String, InstrumentInfo>> {
    if symbols.is_empty() {
        return Ok(BTreeMap::new());
    }

    let mut client = Client::connect(dsn, NoTls)?;
    let rows = client.query(INSTRUMENT_INFO_QUERY, &[&symbols])?;
    let mut instruments = BTreeMap::new();
    for row in rows {
        let code: String = row.try_get("ts_code")?;
        let name: Option<String> = row.try_get("name")?;
        let industry: Option<String> = row.try_get("industry")?;
        let info = InstrumentInfo {
            name: clean_optional_text(name),
            industry: clean_optional_text(industry),
        };
        if info.name.is_some() || info.industry.is_some() {
            instruments.insert(code, info);
        }
    }
    Ok(instruments)
}

fn clean_optional_text(value: Option<String>) -> Option<String> {
    value
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn optional_f64(row: &postgres::Row, column: &str) -> anyhow::Result<f64> {
    Ok(row.try_get::<_, Option<f64>>(column)?.unwrap_or(f64::NAN))
}

fn optional_option_f64(row: &postgres::Row, column: &str) -> anyhow::Result<Option<f64>> {
    Ok(row.try_get::<_, Option<f64>>(column)?)
}

fn db_factor_values_iter<I, K>(values: I) -> BTreeMap<String, f64>
where
    I: IntoIterator<Item = (K, Option<f64>)>,
    K: Into<String>,
{
    values
        .into_iter()
        .filter_map(|(key, value)| {
            value
                .filter(|value| value.is_finite())
                .map(|value| (key.into(), value))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn db_native_daily_window_query_maps_stock_cache_contract_fields() {
        for fragment in [
            "SELECT $1::date AS start_date, $2::date AS end_date",
            "FROM stock_stk_factor_pro s",
            "s.trade_date BETWEEN (SELECT start_date FROM query_params) AND (SELECT end_date FROM query_params)",
            "s.open::double precision AS open",
            "s.high::double precision AS high",
            "s.low::double precision AS low",
            "s.close::double precision AS close",
            "s.adj_factor::double precision AS adj_factor",
            "s.vol::double precision AS vol",
            "s.amount::double precision AS amount",
            "s.turnover_rate::double precision AS turnover_rate",
        ] {
            assert!(
                DB_NATIVE_DAILY_WINDOW_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        for fragment in [
            "stock_moneyflow_ths",
            "index_market_base AS",
            "stock_daily_asof_indicators",
            "stock_daily_rolling_factors",
            "stock_daily_left_peak",
            "kdj_k_qfq",
            "large_net_amount_to_amount_pct",
            "market_sse_ret5_pct",
        ] {
            assert!(
                !DB_NATIVE_DAILY_WINDOW_QUERY.contains(fragment),
                "main prepared stock window should not contain pick-date extra fragment {fragment}"
            );
        }
        assert!(
            !DB_NATIVE_DAILY_WINDOW_QUERY.contains("ORDER BY s.ts_code"),
            "main DB-native window should not force a database sort; Rust prepare_rows sorts per symbol"
        );
        for fragment in [
            "s.open_qfq::double precision AS open",
            "s.high_qfq::double precision AS high",
            "s.low_qfq::double precision AS low",
            "s.close_qfq::double precision AS close",
        ] {
            assert!(
                !DB_NATIVE_DAILY_WINDOW_QUERY.contains(fragment),
                "main DB-native window must feed raw prices into Rust front-adjustment, not pre-adjusted prices: {fragment}"
            );
        }
    }

    #[test]
    fn db_native_pick_date_extras_query_maps_wide_db_native_factors() {
        for fragment in [
            "WHERE s.trade_date = $1",
            "s.kdj_k_qfq::double precision AS kdj_k_qfq",
            "s.kdj_d_qfq::double precision AS kdj_d_qfq",
            "s.dmi_adxr_qfq::double precision AS dmi_adxr_qfq",
            "s.dmi_pdi_qfq::double precision - s.dmi_mdi_qfq::double precision AS dmi_pdi_mdi_spread_qfq",
            "s.dmi_adx_qfq::double precision - s.dmi_adxr_qfq::double precision AS dmi_adx_adxr_gap_qfq",
            "s.trix_qfq::double precision AS trix_qfq",
            "LEFT JOIN stock_moneyflow_ths smf",
            "smf.net_amount::double precision AS stock_mf_net_amount",
            "smf.buy_lg_amount::double precision AS stock_mf_buy_lg_amount",
            "THEN smf.buy_lg_amount::double precision / s.amount::double precision * 100.0",
            "THEN smf.buy_md_amount::double precision / s.amount::double precision * 100.0",
            "THEN smf.buy_sm_amount::double precision / s.amount::double precision * 100.0",
            "WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.net_amount IS NOT NULL",
            "THEN smf.net_amount::double precision / s.amount::double precision * 100.0",
            "index_market_base AS",
            "lag(i.close, 5) OVER (PARTITION BY i.ts_code ORDER BY i.trade_date)::double precision AS close_5_ago",
            "index_market_raw AS",
            "FROM index_idx_factor_pro i",
            "WHERE i.ts_code IN ('000001.SH', '399303.SZ')",
            "index_market_factors AS",
            "max(ret5_pct) FILTER (WHERE ts_code = '000001.SH')::double precision AS market_sse_ret5_pct",
            "max(ret5_pct) FILTER (WHERE ts_code = '399303.SZ')::double precision AS market_cn2000_ret5_pct",
            "CASE WHEN count(ret5_pct) = 2 THEN avg(ret5_pct)::double precision END AS market_broad_ret5_pct",
            "LEFT JOIN index_market_factors imf",
            "LEFT JOIN stock_daily_asof_indicators a",
            "LEFT JOIN stock_daily_rolling_factors r",
            "LEFT JOIN stock_daily_left_peak l",
            "a.calc_version = 'macd_qfq_12_26_9_v1'",
            "a.daily_hist_x2_asof::double precision / 2.0 AS macd_daily_hist",
            "a.weekly_hist_x2_asof::double precision / 2.0 AS macd_weekly_hist",
            "a.monthly_hist_x2_asof::double precision / 2.0 AS macd_monthly_hist",
            "r.calc_version = 'rolling_qfq_v1'",
            "r.position_90d::double precision AS rolling_position_90d",
            "r.close_to_20d_max_close_pct::double precision AS close_to_20d_max_close_pct",
            "l.calc_version = 'left_peak_qfq_v1'",
            "(CASE WHEN l.is_valid THEN 1.0 ELSE 0.0 END)::double precision AS left_peak_valid",
        ] {
            assert!(
                DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        assert!(!DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("s.kdj_j_qfq"));
        assert!(DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("CASE"));
        assert!(DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains(
            "WHEN s.kdj_k_qfq IS NOT NULL AND s.kdj_d_qfq IS NOT NULL"
        ));
        assert!(DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains(
            "THEN 3.0 * s.kdj_k_qfq::double precision - 2.0 * s.kdj_d_qfq::double precision"
        ));
        for factor in [
            "amount",
            "kdj_k_qfq",
            "dmi_adx_qfq",
            "trix_qfq",
            "stock_mf_net_amount",
            "large_net_amount_to_amount_pct",
            "mid_net_amount_to_amount_pct",
            "small_net_amount_to_amount_pct",
            "net_mf_amount_to_amount_pct",
            "market_sse_ret5_pct",
            "market_cn2000_ret5_pct",
            "market_broad_ret5_pct",
            "close_to_20d_max_close_pct",
        ] {
            assert!(
                DB_NATIVE_PICK_DATE_FACTOR_COLUMNS.contains(&factor),
                "missing pick-date factor column {factor}"
            );
        }
    }

    #[test]
    fn db_native_daily_window_query_uses_requested_prepared_range() {
        let query_head = DB_NATIVE_DAILY_WINDOW_QUERY
            .split("current_ths_membership AS")
            .next()
            .expect("query should define main stock window first");

        assert!(query_head.contains("SELECT $1::date AS start_date, $2::date AS end_date"));
        assert!(query_head.contains(
            "s.trade_date BETWEEN (SELECT start_date FROM query_params) AND (SELECT end_date FROM query_params)"
        ));
        assert!(!query_head.contains("LIMIT 252"));
    }

    #[test]
    fn db_module_no_longer_exposes_legacy_daily_market_loader() {
        let source = include_str!("db.rs")
            .split("#[cfg(test)]")
            .next()
            .unwrap_or_default();

        assert!(!source.contains("const DAILY_WINDOW_QUERY"));
        assert!(!source.contains("pub fn fetch_daily_window"));
    }

    #[test]
    fn db_native_coverage_probe_query_checks_required_versions_without_exposing_dsn() {
        for fragment in [
            "stock_stk_factor_pro",
            "stock_daily_asof_indicators",
            "stock_daily_rolling_factors",
            "stock_daily_left_peak",
            "index_ths_daily",
            "stock_moneyflow_ths",
            "index_idx_factor_pro",
            "index_daily_asof_indicators",
            "index_moneyflow_cnt_ths",
            "index_limit_cpt_list",
            "macd_qfq_12_26_9_v1",
            "rolling_qfq_v1",
            "left_peak_qfq_v1",
        ] {
            assert!(
                DB_NATIVE_COVERAGE_PROBE_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        assert!(!DB_NATIVE_COVERAGE_PROBE_QUERY.contains("POSTGRES_DSN"));
        assert!(!DB_NATIVE_COVERAGE_PROBE_QUERY.contains("postgres://"));
        assert!(!DB_NATIVE_COVERAGE_PROBE_QUERY.contains("postgresql://"));
    }

    #[test]
    fn db_native_daily_window_query_maps_current_ths_sector_factors_without_row_duplication() {
        assert!(
            !DB_NATIVE_DAILY_WINDOW_QUERY.contains("stock_ths_sector_candidates AS"),
            "THS sector extras should not be part of the main prepared stock window query"
        );
        assert!(
            DB_NATIVE_THS_SECTOR_EXTRAS_QUERY.contains("stock_ths_sector_candidates AS"),
            "THS sector extras should be loaded by a separate query and merged into db_factors"
        );
        for fragment in [
            "current_ths_membership AS",
            "FROM index_ths_member",
            "index_market_factors AS",
            "max(ret5_pct) FILTER (WHERE ts_code = '000001.SH')::double precision AS market_sse_ret5_pct",
            "max(ret5_pct) FILTER (WHERE ts_code = '399303.SZ')::double precision AS market_cn2000_ret5_pct",
            "ths_sector_daily AS",
            "FROM index_ths_daily d",
            "lag(d.close, 5) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date)::double precision AS ths_close_5_ago",
            "LEFT JOIN index_moneyflow_cnt_ths mf",
            "index_limit_cpt_daily AS",
            "FROM index_limit_cpt_list",
            "GROUP BY ts_code, trade_date",
            "LEFT JOIN index_limit_cpt_daily il",
            "LEFT JOIN index_daily_asof_indicators ia",
            "stock_ths_sector_candidates AS",
            "ROW_NUMBER() OVER (",
            "PARTITION BY s.ts_code, s.trade_date",
            "ORDER BY ths_sector_rank ASC NULLS LAST, ths_net_amount DESC NULLS LAST, ths_pct_change DESC NULLS LAST, ths_ts_code ASC",
            "stock_ths_sector_agg AS",
            "COUNT(*)::double precision AS ths_sector_count",
            "MAX(ths_pct_change) AS ths_best_pct_change",
            "AVG(ths_pct_change) AS ths_avg_pct_change",
            "MAX(ths_net_buy_amount) AS ths_best_net_buy_amount",
            "MAX(ths_limit_up_count) AS ths_best_limit_up_count",
            "ths_any_limit_up_sector_flag",
            "ths_limit_up_sector_count",
            "ths_limit_up_sector_ratio",
            "MIN(ths_limit_rank) AS ths_best_limit_rank",
            "m.ths_ts_code AS ths_main_sector_code",
            "m.ths_limit_up_count AS ths_main_limit_up_count",
            "ta.ths_sector_count::double precision AS ths_sector_count",
            "ta.ths_best_net_buy_amount AS ths_best_net_buy_amount",
            "m.stock_pct_chg - m.ths_pct_change AS stock_vs_ths_main_pct_change",
            "m.stock_pct_chg - ta.ths_avg_pct_change AS stock_vs_ths_avg_pct_change",
            "m.ths_ret5_pct - imf.market_broad_ret5_pct AS stock_env_sector_vs_broad_ret5_pct",
            "m.ths_ret20_pct - imf.market_broad_ret20_pct AS stock_env_sector_vs_broad_ret20_pct",
            "imf.market_cn2000_ret5_pct - imf.market_sse_ret5_pct AS stock_env_style_ret5_spread_pct",
            "m.ths_ret5_pct + imf.market_broad_ret5_pct AS stock_env_market_sector_ret5_sum_pct",
            "stock_env_market_score",
            "stock_env_sector_score",
            "stock_env_alignment_score",
            "stock_env_limit_heat_score",
            "stock_env_overall_score",
        ] {
            assert!(
                DB_NATIVE_THS_SECTOR_EXTRAS_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        assert!(DB_NATIVE_THS_SECTOR_EXTRAS_QUERY.contains("cm.con_code = s.ts_code"));
        assert!(!DB_NATIVE_THS_SECTOR_EXTRAS_QUERY.contains("cm.trade_date"));
        assert!(!DB_NATIVE_THS_SECTOR_EXTRAS_QUERY.contains("index_ths_member_history"));
        for factor in [
            "ths_membership_current_flag",
            "ths_main_sector_rank",
            "ths_main_pct_change",
            "ths_main_net_amount",
            "ths_main_limit_up_count",
            "ths_main_macd_daily_hist",
            "ths_sector_count",
            "ths_best_pct_change",
            "ths_avg_pct_change",
            "ths_best_net_buy_amount",
            "ths_best_limit_up_count",
            "ths_any_limit_up_sector_flag",
            "ths_limit_up_sector_count",
            "ths_limit_up_sector_ratio",
            "stock_vs_ths_main_pct_change",
            "stock_vs_ths_avg_pct_change",
            "stock_env_sector_ret5_pct",
            "stock_env_sector_ret20_pct",
            "stock_env_sector_ma20_bias_pct",
            "stock_env_sector_vs_broad_ret5_pct",
            "stock_env_sector_vs_broad_ret20_pct",
            "stock_env_style_ret5_spread_pct",
            "stock_env_market_sector_ret5_sum_pct",
            "stock_env_market_score",
            "stock_env_sector_score",
            "stock_env_alignment_score",
            "stock_env_limit_heat_score",
            "stock_env_overall_score",
        ] {
            assert!(
                DB_NATIVE_THS_SECTOR_FACTOR_COLUMNS.contains(&factor),
                "missing factor column {factor}"
            );
        }
    }

    #[test]
    fn resolve_previous_trade_date_query_uses_stock_cache_trade_dates() {
        for fragment in [
            "SELECT max(trade_date) AS trade_date",
            "FROM stock_stk_factor_pro",
            "WHERE trade_date < $1",
        ] {
            assert!(
                PREVIOUS_TRADE_DATE_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        assert!(!PREVIOUS_TRADE_DATE_QUERY.contains("daily_market"));
        assert!(!PREVIOUS_TRADE_DATE_QUERY.contains("POSTGRES_DSN"));
        assert!(!PREVIOUS_TRADE_DATE_QUERY.contains("postgres://"));
        assert!(!PREVIOUS_TRADE_DATE_QUERY.contains("postgresql://"));
    }

    #[test]
    fn stock_period_macd_state_query_reads_completed_period_states_only() {
        for fragment in [
            "FROM stock_period_indicator_state p",
            "p.period_type IN ('daily', 'weekly', 'monthly')",
            "p.period_end_date < $2",
            "p.calc_version = 'macd_qfq_12_26_9_v1'",
            "p.period_count IS NOT NULL",
            "ORDER BY p.ts_code, p.period_type, p.period_end_date DESC",
        ] {
            assert!(
                STOCK_PERIOD_MACD_STATE_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        assert!(!STOCK_PERIOD_MACD_STATE_QUERY.contains("daily_asof"));
        assert!(!STOCK_PERIOD_MACD_STATE_QUERY.contains("stock_daily_asof_indicators"));
        assert!(!STOCK_PERIOD_MACD_STATE_QUERY.contains("POSTGRES_DSN"));
        assert!(!STOCK_PERIOD_MACD_STATE_QUERY.contains("postgres://"));
        assert!(!STOCK_PERIOD_MACD_STATE_QUERY.contains("postgresql://"));
    }

    #[test]
    fn instrument_info_query_uses_stock_cache_membership_table() {
        for fragment in [
            "FROM index_ths_member",
            "con_code AS ts_code",
            "max(con_name) AS name",
            "NULL::text AS industry",
            "WHERE con_code = ANY($1)",
        ] {
            assert!(INSTRUMENT_INFO_QUERY.contains(fragment), "missing {fragment}");
        }
        assert!(!INSTRUMENT_INFO_QUERY.contains("FROM instruments"));
    }

    #[test]
    fn db_native_fixture_row_maps_stock_cache_values_to_market_row() {
        let trade_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
        let row = DbNativeDailyRow {
            ts_code: "000001.SZ".to_string(),
            trade_date,
            open: 10.1,
            high: 10.8,
            low: 9.9,
            close: 10.5,
            adj_factor: Some(1.25),
            vol: 123456.0,
            turnover_rate: Some(2.5),
            db_factors: [
                ("kdj_k_qfq".to_string(), Some(61.0)),
                ("kdj_d_qfq".to_string(), Some(52.0)),
                ("kdj_j_qfq".to_string(), Some(79.0)),
                ("dmi_adxr_qfq".to_string(), Some(22.0)),
                ("dmi_adx_qfq".to_string(), Some(25.0)),
                ("dmi_pdi_qfq".to_string(), Some(31.0)),
                ("dmi_mdi_qfq".to_string(), Some(19.0)),
                ("dmi_pdi_mdi_spread_qfq".to_string(), Some(12.0)),
                ("dmi_adx_adxr_gap_qfq".to_string(), Some(3.0)),
                ("wr_qfq".to_string(), Some(-12.5)),
                ("mtm_qfq".to_string(), Some(1.8)),
                ("roc_qfq".to_string(), Some(4.2)),
                ("trix_qfq".to_string(), Some(0.35)),
                ("obv_qfq".to_string(), Some(123456.0)),
                ("vr_qfq".to_string(), Some(135.0)),
                ("psy_qfq".to_string(), Some(66.7)),
                ("bias1_qfq".to_string(), Some(2.4)),
                ("macd_daily_dif".to_string(), Some(0.42)),
                ("macd_daily_dea".to_string(), Some(0.30)),
                ("macd_daily_hist".to_string(), Some(0.12)),
                ("macd_weekly_hist".to_string(), Some(0.34)),
                ("macd_monthly_hist".to_string(), Some(-0.08)),
                ("rolling_ma25_qfq".to_string(), Some(10.2)),
                ("rolling_position_90d".to_string(), Some(0.72)),
                ("close_to_20d_max_close_pct".to_string(), Some(-1.8)),
                ("rolling_range_compression_20d".to_string(), Some(0.16)),
                ("left_peak_high".to_string(), Some(11.8)),
                ("left_peak_valid".to_string(), Some(1.0)),
                ("left_peak_b_div_a".to_string(), Some(1.03)),
                ("left_peak_days_since_peak".to_string(), Some(17.0)),
                ("ths_membership_current_flag".to_string(), Some(1.0)),
                ("ths_main_sector_rank".to_string(), Some(3.0)),
                ("ths_main_pct_change".to_string(), Some(2.4)),
                ("ths_main_net_amount".to_string(), Some(1.2)),
                ("ths_main_limit_up_count".to_string(), Some(8.0)),
                ("ths_main_limit_days".to_string(), Some(2.0)),
                ("ths_main_limit_pct_chg".to_string(), Some(5.6)),
                ("ths_main_limit_rank".to_string(), Some(4.0)),
                ("ths_main_macd_daily_hist".to_string(), Some(0.06)),
                ("ths_sector_count".to_string(), Some(4.0)),
                ("ths_best_pct_change".to_string(), Some(3.1)),
                ("ths_avg_pct_change".to_string(), Some(1.7)),
                ("ths_best_net_buy_amount".to_string(), Some(2.2)),
                ("ths_avg_net_buy_amount".to_string(), Some(1.1)),
                ("ths_best_net_sell_amount".to_string(), Some(0.9)),
                ("ths_avg_net_sell_amount".to_string(), Some(0.4)),
                ("ths_best_limit_up_count".to_string(), Some(12.0)),
                ("ths_avg_limit_up_count".to_string(), Some(6.0)),
                ("ths_any_limit_up_sector_flag".to_string(), Some(1.0)),
                ("ths_limit_up_sector_count".to_string(), Some(3.0)),
                ("ths_limit_up_sector_ratio".to_string(), Some(0.75)),
                ("ths_best_limit_days".to_string(), Some(3.0)),
                ("ths_best_limit_pct_chg".to_string(), Some(7.8)),
                ("ths_avg_limit_pct_chg".to_string(), Some(4.9)),
                ("ths_best_limit_rank".to_string(), Some(2.0)),
                ("stock_vs_ths_main_pct_change".to_string(), Some(0.8)),
                ("stock_vs_ths_avg_pct_change".to_string(), Some(1.5)),
                ("stock_env_sector_ret5_pct".to_string(), Some(6.2)),
                ("stock_env_sector_ret20_pct".to_string(), Some(12.4)),
                ("stock_env_sector_ma20_bias_pct".to_string(), Some(3.3)),
                ("stock_env_sector_vs_broad_ret5_pct".to_string(), Some(4.8)),
                ("stock_env_sector_vs_broad_ret20_pct".to_string(), Some(9.6)),
                ("stock_env_style_ret5_spread_pct".to_string(), Some(0.6)),
                ("stock_env_market_sector_ret5_sum_pct".to_string(), Some(7.6)),
                ("stock_env_market_score".to_string(), Some(1.05)),
                ("stock_env_sector_score".to_string(), Some(3.4)),
                ("stock_env_alignment_score".to_string(), Some(1.0)),
                ("stock_env_limit_heat_score".to_string(), Some(1.75)),
                ("stock_env_overall_score".to_string(), Some(2.05)),
                ("stock_mf_net_amount".to_string(), Some(900.0)),
                ("stock_mf_net_d5_amount".to_string(), Some(1500.0)),
                ("stock_mf_buy_lg_amount".to_string(), Some(500.0)),
                ("stock_mf_buy_lg_amount_rate".to_string(), Some(5.0)),
                ("stock_mf_buy_md_amount".to_string(), Some(250.0)),
                ("stock_mf_buy_md_amount_rate".to_string(), Some(2.5)),
                ("stock_mf_buy_sm_amount".to_string(), Some(-100.0)),
                ("stock_mf_buy_sm_amount_rate".to_string(), Some(-1.0)),
                ("large_net_amount_to_amount_pct".to_string(), Some(1.5)),
                ("mid_net_amount_to_amount_pct".to_string(), Some(0.75)),
                ("small_net_amount_to_amount_pct".to_string(), Some(-0.3)),
                ("net_mf_amount_to_amount_pct".to_string(), Some(2.7)),
                ("market_sse_ret5_pct".to_string(), Some(1.1)),
                ("market_sse_ret20_pct".to_string(), Some(2.2)),
                ("market_sse_ma20_bias_pct".to_string(), Some(0.3)),
                ("market_sse_volatility20_pct".to_string(), Some(0.9)),
                ("market_cn2000_ret5_pct".to_string(), Some(1.7)),
                ("market_cn2000_ret20_pct".to_string(), Some(3.4)),
                ("market_cn2000_ma20_bias_pct".to_string(), Some(0.6)),
                ("market_cn2000_volatility20_pct".to_string(), Some(1.3)),
                ("market_broad_ret5_pct".to_string(), Some(1.4)),
                ("market_broad_ret20_pct".to_string(), Some(2.8)),
                ("market_broad_ma20_bias_pct".to_string(), Some(0.45)),
                ("market_broad_volatility20_pct".to_string(), Some(1.1)),
                ("ignored_nan".to_string(), Some(f64::NAN)),
                ("ignored_null".to_string(), None),
            ]
            .into_iter()
            .collect(),
        };

        let mapped = db_native_market_row_from_values(row).unwrap();

        assert_eq!(mapped.ts_code, "000001.SZ");
        assert_eq!(mapped.trade_date, trade_date);
        assert_eq!(mapped.open, 10.1);
        assert_eq!(mapped.high, 10.8);
        assert_eq!(mapped.low, 9.9);
        assert_eq!(mapped.close, 10.5);
        assert_eq!(mapped.vol, 123456.0);
        assert_eq!(mapped.turnover_rate, Some(2.5));
        assert_eq!(mapped.adj_factor, Some(1.25));
        assert_eq!(mapped.db_factors["kdj_k_qfq"], 61.0);
        assert_eq!(mapped.db_factors["kdj_d_qfq"], 52.0);
        assert_eq!(mapped.db_factors["kdj_j_qfq"], 79.0);
        assert_eq!(mapped.db_factors["dmi_adxr_qfq"], 22.0);
        assert_eq!(mapped.db_factors["dmi_adx_qfq"], 25.0);
        assert_eq!(mapped.db_factors["dmi_pdi_qfq"], 31.0);
        assert_eq!(mapped.db_factors["dmi_mdi_qfq"], 19.0);
        assert_eq!(mapped.db_factors["dmi_pdi_mdi_spread_qfq"], 12.0);
        assert_eq!(mapped.db_factors["dmi_adx_adxr_gap_qfq"], 3.0);
        assert_eq!(mapped.db_factors["wr_qfq"], -12.5);
        assert_eq!(mapped.db_factors["mtm_qfq"], 1.8);
        assert_eq!(mapped.db_factors["roc_qfq"], 4.2);
        assert_eq!(mapped.db_factors["trix_qfq"], 0.35);
        assert_eq!(mapped.db_factors["obv_qfq"], 123456.0);
        assert_eq!(mapped.db_factors["vr_qfq"], 135.0);
        assert_eq!(mapped.db_factors["psy_qfq"], 66.7);
        assert_eq!(mapped.db_factors["bias1_qfq"], 2.4);
        assert_eq!(mapped.db_factors["macd_daily_dif"], 0.42);
        assert_eq!(mapped.db_factors["macd_daily_dea"], 0.30);
        assert_eq!(mapped.db_factors["macd_daily_hist"], 0.12);
        assert_eq!(mapped.db_factors["macd_weekly_hist"], 0.34);
        assert_eq!(mapped.db_factors["macd_monthly_hist"], -0.08);
        assert_eq!(mapped.db_factors["rolling_ma25_qfq"], 10.2);
        assert_eq!(mapped.db_factors["rolling_position_90d"], 0.72);
        assert_eq!(mapped.db_factors["close_to_20d_max_close_pct"], -1.8);
        assert_eq!(mapped.db_factors["rolling_range_compression_20d"], 0.16);
        assert_eq!(mapped.db_factors["left_peak_high"], 11.8);
        assert_eq!(mapped.db_factors["left_peak_valid"], 1.0);
        assert_eq!(mapped.db_factors["left_peak_b_div_a"], 1.03);
        assert_eq!(mapped.db_factors["left_peak_days_since_peak"], 17.0);
        assert_eq!(mapped.db_factors["ths_membership_current_flag"], 1.0);
        assert_eq!(mapped.db_factors["ths_main_sector_rank"], 3.0);
        assert_eq!(mapped.db_factors["ths_main_pct_change"], 2.4);
        assert_eq!(mapped.db_factors["ths_main_net_amount"], 1.2);
        assert_eq!(mapped.db_factors["ths_main_limit_up_count"], 8.0);
        assert_eq!(mapped.db_factors["ths_main_limit_days"], 2.0);
        assert_eq!(mapped.db_factors["ths_main_limit_pct_chg"], 5.6);
        assert_eq!(mapped.db_factors["ths_main_limit_rank"], 4.0);
        assert_eq!(mapped.db_factors["ths_main_macd_daily_hist"], 0.06);
        assert_eq!(mapped.db_factors["ths_sector_count"], 4.0);
        assert_eq!(mapped.db_factors["ths_best_pct_change"], 3.1);
        assert_eq!(mapped.db_factors["ths_avg_pct_change"], 1.7);
        assert_eq!(mapped.db_factors["ths_best_net_buy_amount"], 2.2);
        assert_eq!(mapped.db_factors["ths_avg_net_buy_amount"], 1.1);
        assert_eq!(mapped.db_factors["ths_best_net_sell_amount"], 0.9);
        assert_eq!(mapped.db_factors["ths_avg_net_sell_amount"], 0.4);
        assert_eq!(mapped.db_factors["ths_best_limit_up_count"], 12.0);
        assert_eq!(mapped.db_factors["ths_avg_limit_up_count"], 6.0);
        assert_eq!(mapped.db_factors["ths_any_limit_up_sector_flag"], 1.0);
        assert_eq!(mapped.db_factors["ths_limit_up_sector_count"], 3.0);
        assert_eq!(mapped.db_factors["ths_limit_up_sector_ratio"], 0.75);
        assert_eq!(mapped.db_factors["ths_best_limit_days"], 3.0);
        assert_eq!(mapped.db_factors["ths_best_limit_pct_chg"], 7.8);
        assert_eq!(mapped.db_factors["ths_avg_limit_pct_chg"], 4.9);
        assert_eq!(mapped.db_factors["ths_best_limit_rank"], 2.0);
        assert_eq!(mapped.db_factors["stock_vs_ths_main_pct_change"], 0.8);
        assert_eq!(mapped.db_factors["stock_vs_ths_avg_pct_change"], 1.5);
        assert_eq!(mapped.db_factors["stock_env_sector_ret5_pct"], 6.2);
        assert_eq!(mapped.db_factors["stock_env_sector_ret20_pct"], 12.4);
        assert_eq!(mapped.db_factors["stock_env_sector_ma20_bias_pct"], 3.3);
        assert_eq!(mapped.db_factors["stock_env_sector_vs_broad_ret5_pct"], 4.8);
        assert_eq!(mapped.db_factors["stock_env_sector_vs_broad_ret20_pct"], 9.6);
        assert_eq!(mapped.db_factors["stock_env_style_ret5_spread_pct"], 0.6);
        assert_eq!(mapped.db_factors["stock_env_market_sector_ret5_sum_pct"], 7.6);
        assert_eq!(mapped.db_factors["stock_env_market_score"], 1.05);
        assert_eq!(mapped.db_factors["stock_env_sector_score"], 3.4);
        assert_eq!(mapped.db_factors["stock_env_alignment_score"], 1.0);
        assert_eq!(mapped.db_factors["stock_env_limit_heat_score"], 1.75);
        assert_eq!(mapped.db_factors["stock_env_overall_score"], 2.05);
        assert_eq!(mapped.db_factors["stock_mf_net_amount"], 900.0);
        assert_eq!(mapped.db_factors["stock_mf_net_d5_amount"], 1500.0);
        assert_eq!(mapped.db_factors["stock_mf_buy_lg_amount"], 500.0);
        assert_eq!(mapped.db_factors["stock_mf_buy_lg_amount_rate"], 5.0);
        assert_eq!(mapped.db_factors["stock_mf_buy_md_amount"], 250.0);
        assert_eq!(mapped.db_factors["stock_mf_buy_md_amount_rate"], 2.5);
        assert_eq!(mapped.db_factors["stock_mf_buy_sm_amount"], -100.0);
        assert_eq!(mapped.db_factors["stock_mf_buy_sm_amount_rate"], -1.0);
        assert_eq!(mapped.db_factors["large_net_amount_to_amount_pct"], 1.5);
        assert_eq!(mapped.db_factors["mid_net_amount_to_amount_pct"], 0.75);
        assert_eq!(mapped.db_factors["small_net_amount_to_amount_pct"], -0.3);
        assert_eq!(mapped.db_factors["net_mf_amount_to_amount_pct"], 2.7);
        assert_eq!(mapped.db_factors["market_sse_ret5_pct"], 1.1);
        assert_eq!(mapped.db_factors["market_sse_ret20_pct"], 2.2);
        assert_eq!(mapped.db_factors["market_sse_ma20_bias_pct"], 0.3);
        assert_eq!(mapped.db_factors["market_sse_volatility20_pct"], 0.9);
        assert_eq!(mapped.db_factors["market_cn2000_ret5_pct"], 1.7);
        assert_eq!(mapped.db_factors["market_cn2000_ret20_pct"], 3.4);
        assert_eq!(mapped.db_factors["market_cn2000_ma20_bias_pct"], 0.6);
        assert_eq!(mapped.db_factors["market_cn2000_volatility20_pct"], 1.3);
        assert_eq!(mapped.db_factors["market_broad_ret5_pct"], 1.4);
        assert_eq!(mapped.db_factors["market_broad_ret20_pct"], 2.8);
        assert_eq!(mapped.db_factors["market_broad_ma20_bias_pct"], 0.45);
        assert_eq!(mapped.db_factors["market_broad_volatility20_pct"], 1.1);
        assert!(!mapped.db_factors.contains_key("ignored_nan"));
        assert!(!mapped.db_factors.contains_key("ignored_null"));
    }

    #[test]
    fn db_native_required_coverage_fails_fast_when_calc_versions_are_missing() {
        let probe = DbNativeCoverageProbe {
            pick_date: NaiveDate::from_ymd_opt(2026, 6, 15).unwrap(),
            window_start_date: Some(NaiveDate::from_ymd_opt(2025, 6, 13).unwrap()),
            window_end_date: Some(NaiveDate::from_ymd_opt(2026, 6, 15).unwrap()),
            window_trade_dates: 252,
            stock_factor_rows: 5000,
            stock_macd_rows: 0,
            stock_rolling_rows: 0,
            stock_left_peak_rows: 0,
            stock_moneyflow_rows: 0,
            index_ths_daily_rows: 0,
            index_market_rows: 0,
            index_macd_rows: 0,
            index_moneyflow_rows: 0,
            index_limit_rows: 0,
        };

        let err = ensure_db_native_required_coverage(&probe)
            .expect_err("missing calc_version coverage should fail fast");
        let message = err.to_string();
        assert!(message.contains("stock_daily_asof_indicators"));
        assert!(message.contains("macd_qfq_12_26_9_v1"));
        assert!(message.contains("stock_daily_rolling_factors"));
        assert!(message.contains("rolling_qfq_v1"));
        assert!(message.contains("stock_daily_left_peak"));
        assert!(message.contains("left_peak_qfq_v1"));
        assert!(message.contains("stock_moneyflow_ths"));
        assert!(message.contains("index_ths_daily"));
        assert!(message.contains("index_idx_factor_pro"));
        assert!(message.contains("index_daily_asof_indicators"));
        assert!(message.contains("index_moneyflow_cnt_ths"));
        assert!(message.contains("index_limit_cpt_list"));
        assert!(!message.contains("POSTGRES_DSN"));
        assert!(!message.contains("postgres://"));
        assert!(!message.contains("postgresql://"));
    }

    #[test]
    fn db_native_required_coverage_fails_without_requested_prepared_window() {
        let probe = DbNativeCoverageProbe {
            pick_date: NaiveDate::from_ymd_opt(2026, 6, 15).unwrap(),
            window_start_date: Some(NaiveDate::from_ymd_opt(2023, 6, 16).unwrap()),
            window_end_date: Some(NaiveDate::from_ymd_opt(2026, 6, 15).unwrap()),
            window_trade_dates: 700,
            stock_factor_rows: 5000,
            stock_macd_rows: 5000,
            stock_rolling_rows: 5000,
            stock_left_peak_rows: 5000,
            stock_moneyflow_rows: 5000,
            index_ths_daily_rows: 0,
            index_market_rows: 2,
            index_macd_rows: 0,
            index_moneyflow_rows: 0,
            index_limit_rows: 0,
        };

        let err = ensure_db_native_required_coverage(&probe)
            .expect_err("DB-native loader requires the requested prepared window start");

        assert!(err.to_string().contains("requested prepared window"));
    }

    #[test]
    fn db_native_required_coverage_allows_long_holiday_start_when_window_has_enough_trade_dates() {
        let probe = DbNativeCoverageProbe {
            pick_date: NaiveDate::from_ymd_opt(2026, 1, 28).unwrap(),
            window_start_date: Some(NaiveDate::from_ymd_opt(2025, 2, 5).unwrap()),
            window_end_date: Some(NaiveDate::from_ymd_opt(2026, 1, 28).unwrap()),
            window_trade_dates: 243,
            stock_factor_rows: 5000,
            stock_macd_rows: 5000,
            stock_rolling_rows: 5000,
            stock_left_peak_rows: 5000,
            stock_moneyflow_rows: 5000,
            index_ths_daily_rows: 5000,
            index_market_rows: 2,
            index_macd_rows: 5000,
            index_moneyflow_rows: 5000,
            index_limit_rows: 5000,
        };

        ensure_db_native_required_coverage(&probe).unwrap();
    }

    #[test]
    fn db_native_required_coverage_rejects_short_actual_window_even_after_requested_start() {
        let probe = DbNativeCoverageProbe {
            pick_date: NaiveDate::from_ymd_opt(2026, 1, 28).unwrap(),
            window_start_date: Some(NaiveDate::from_ymd_opt(2025, 3, 20).unwrap()),
            window_end_date: Some(NaiveDate::from_ymd_opt(2026, 1, 28).unwrap()),
            window_trade_dates: 200,
            stock_factor_rows: 5000,
            stock_macd_rows: 5000,
            stock_rolling_rows: 5000,
            stock_left_peak_rows: 5000,
            stock_moneyflow_rows: 5000,
            index_ths_daily_rows: 5000,
            index_market_rows: 2,
            index_macd_rows: 5000,
            index_moneyflow_rows: 5000,
            index_limit_rows: 5000,
        };

        let err = ensure_db_native_required_coverage(&probe)
            .expect_err("short actual DB-native window should fail");

        assert!(err.to_string().contains("requested prepared window"));
    }

    #[test]
    fn db_native_coverage_probe_checks_local_stock_cache_when_dsn_is_available() {
        let Ok(dsn) = std::env::var("POSTGRES_DSN") else {
            eprintln!("skipping local stock-cache coverage probe: POSTGRES_DSN is not set");
            return;
        };
        let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();

        let probe = probe_db_native_coverage(&dsn, pick_date).unwrap();

        assert!(probe.window_trade_dates > 0);
        assert!(probe.window_start_date.is_some());
        assert_eq!(probe.window_end_date, Some(pick_date));
        assert!(probe.stock_factor_rows > 0);
        assert!(probe.stock_macd_rows > 0);
        assert!(probe.stock_rolling_rows > 0);
        assert!(probe.stock_left_peak_rows > 0);
        assert!(probe.index_ths_daily_rows > 0);
        assert!(probe.index_macd_rows > 0);
        assert!(probe.index_moneyflow_rows > 0);
        assert!(probe.index_limit_rows > 0);
    }

    #[test]
    fn db_native_loader_reads_local_stock_cache_when_dsn_is_available() {
        let Ok(dsn) = std::env::var("POSTGRES_DSN") else {
            eprintln!("skipping local stock-cache DB-native loader probe: POSTGRES_DSN is not set");
            return;
        };
        let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();

        let rows = fetch_db_native_daily_window(&dsn, pick_date, pick_date).unwrap();

        assert!(!rows.is_empty());
        let row = rows
            .iter()
            .find(|row| row.trade_date == pick_date)
            .expect("loader should return pick-date rows");
        assert!(row.open.is_finite());
        assert!(row.high.is_finite());
        assert!(row.low.is_finite());
        assert!(row.close.is_finite());
        assert!(row.db_factors.contains_key("kdj_k_qfq"));
        assert!(row.db_factors.contains_key("kdj_d_qfq"));
        assert!(row.db_factors.contains_key("kdj_j_qfq"));
        assert!(row.db_factors.contains_key("dmi_adx_qfq"));
        assert!(row.db_factors.contains_key("dmi_pdi_mdi_spread_qfq"));
        assert!(row.db_factors.contains_key("trix_qfq"));
        assert!(row.db_factors.contains_key("macd_daily_hist"));
        assert!(row.db_factors.contains_key("macd_weekly_hist"));
        assert!(row.db_factors.contains_key("macd_monthly_hist"));
        assert!(row.db_factors.contains_key("rolling_position_90d"));
        assert!(row.db_factors.contains_key("close_to_20d_max_close_pct"));
        assert!(row.db_factors.contains_key("left_peak_valid"));
        assert!(row.db_factors.contains_key("stock_mf_net_amount"));
        assert!(row.db_factors.contains_key("large_net_amount_to_amount_pct"));
        assert!(row.db_factors.contains_key("mid_net_amount_to_amount_pct"));
        assert!(row.db_factors.contains_key("small_net_amount_to_amount_pct"));
        assert!(row.db_factors.contains_key("net_mf_amount_to_amount_pct"));
        assert!(row.db_factors.contains_key("ths_main_limit_up_count"));
        assert!(row.db_factors.contains_key("ths_best_limit_up_count"));
        assert!(row.db_factors.contains_key("ths_any_limit_up_sector_flag"));
        assert!(row.db_factors.contains_key("ths_limit_up_sector_count"));
        assert!(row.db_factors.contains_key("ths_limit_up_sector_ratio"));
        assert!(row.db_factors.contains_key("stock_env_sector_ret5_pct"));
        assert!(row.db_factors.contains_key("stock_env_sector_vs_broad_ret5_pct"));
        assert!(row.db_factors.contains_key("stock_env_style_ret5_spread_pct"));
        assert!(row.db_factors.contains_key("stock_env_market_score"));
        assert!(row.db_factors.contains_key("stock_env_sector_score"));
        assert!(row.db_factors.contains_key("stock_env_alignment_score"));
        assert!(row.db_factors.contains_key("stock_env_limit_heat_score"));
        assert!(row.db_factors.contains_key("stock_env_overall_score"));
        assert!(row.db_factors.contains_key("market_sse_ret5_pct"));
        assert!(row.db_factors.contains_key("market_cn2000_ret5_pct"));
        assert!(row.db_factors.contains_key("market_broad_ret5_pct"));
    }

    #[test]
    fn db_native_window_session_settings_allow_parallel_query_and_larger_work_mem() {
        assert!(DAILY_WINDOW_SESSION_SETTINGS_SQL.contains("max_parallel_workers_per_gather = 2"));
        assert!(DAILY_WINDOW_SESSION_SETTINGS_SQL.contains("work_mem = '64MB'"));
    }
}
