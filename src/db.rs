use chrono::NaiveDate;
use postgres::{Client, IsolationLevel, NoTls, fallible_iterator::FallibleIterator};
use std::collections::BTreeMap;

use crate::config::resolve_db_check_tables;
use crate::db_check::preflight_db_native_load;
use crate::intraday::MacdPeriodState;
use crate::model::{InstrumentInfo, MarketDataset, MarketRow};

const DAILY_WINDOW_SESSION_SETTINGS_SQL: &str = "
    SET max_parallel_workers_per_gather = 0;
    SET work_mem = '16MB';
";

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
            s.close_qfq::double precision AS _source_close_qfq,
            s.adj_factor::double precision AS adj_factor,
            s.vol::double precision AS vol,
            s.amount::double precision AS amount,
            s.turnover_rate::double precision AS turnover_rate,
            CASE WHEN c.ts_code IS NOT NULL THEN 1.0 ELSE 0.0 END::double precision AS _czsc_snapshot_available,
            CASE WHEN c.source_bar_valid THEN 1.0 WHEN c.source_bar_valid = false THEN 0.0 END::double precision AS _czsc_source_bar_valid,
            CASE c.status
                WHEN 'invalid_source_bar' THEN 0.0
                WHEN 'no_finished_bi' THEN 1.0
                WHEN 'insufficient_bis_for_zs' THEN 2.0
                WHEN 'no_valid_zs' THEN 3.0
                WHEN 'ok' THEN 4.0
            END::double precision AS _czsc_status_code,
            c.available_finished_bi_count::double precision AS _czsc_available_finished_bi_count,
            c.recent_bi_count::double precision AS _czsc_recent_bi_count,
            CASE c.last_bi_direction WHEN 'up' THEN 1.0 WHEN 'down' THEN -1.0 END::double precision AS _czsc_last_bi_direction_code,
            (c.last_bi_start_date - DATE '1970-01-01')::double precision AS _czsc_last_bi_start_day,
            (c.last_bi_end_date - DATE '1970-01-01')::double precision AS _czsc_last_bi_end_day,
            c.last_bi_high::double precision AS _czsc_last_bi_high,
            c.last_bi_low::double precision AS _czsc_last_bi_low,
            c.last_bi_mid::double precision AS _czsc_last_bi_mid,
            (c.latest_zs_start_date - DATE '1970-01-01')::double precision AS _czsc_latest_zs_start_day,
            (c.latest_zs_end_date - DATE '1970-01-01')::double precision AS _czsc_latest_zs_end_day,
            c.latest_zs_bi_count::double precision AS _czsc_latest_zs_bi_count,
            c.latest_zs_zg::double precision AS _czsc_latest_zs_zg,
            c.latest_zs_zd::double precision AS _czsc_latest_zs_zd,
            c.latest_zs_zz::double precision AS _czsc_latest_zs_zz,
            (c.recent_peak_date - DATE '1970-01-01')::double precision AS _czsc_recent_peak_day,
            c.recent_peak_high::double precision AS _czsc_recent_peak_high,
            (c.post_peak_first_bear_date - DATE '1970-01-01')::double precision AS _czsc_post_peak_first_bear_day,
            c.post_peak_first_bear_open::double precision AS _czsc_post_peak_first_bear_open,
            c.post_peak_first_bear_high::double precision AS _czsc_post_peak_first_bear_high,
            c.post_peak_first_bear_low::double precision AS _czsc_post_peak_first_bear_low,
            c.post_peak_first_bear_close::double precision AS _czsc_post_peak_first_bear_close,
            CASE WHEN c.post_peak_first_bear_missing THEN 1.0 WHEN c.post_peak_first_bear_missing = false THEN 0.0 END::double precision AS _czsc_post_peak_first_bear_missing
        FROM {{stock_stk_factor_pro}} s
        LEFT JOIN {{stock_daily_czsc_structure}} c
          ON c.ts_code = s.ts_code
         AND c.trade_date = s.trade_date
         AND c.calc_version = 'czsc_structure_qfq_min6_r7_v1'
        WHERE s.trade_date BETWEEN (SELECT start_date FROM query_params) AND (SELECT end_date FROM query_params)
        ";

const DB_NATIVE_PICK_DATE_EXTRAS_QUERY: &str = "
        WITH recent_trade_dates AS (
            SELECT trade_date
            FROM (
                SELECT DISTINCT trade_date
                FROM {{stock_stk_factor_pro}}
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
            FROM {{index_idx_factor_pro}} i
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
        FROM {{stock_stk_factor_pro}} s
        LEFT JOIN {{stock_daily_asof_indicators}} a
          ON a.ts_code = s.ts_code
         AND a.trade_date = s.trade_date
         AND a.calc_version = 'macd_qfq_12_26_9_v1'
        LEFT JOIN {{stock_daily_rolling_factors}} r
          ON r.ts_code = s.ts_code
         AND r.trade_date = s.trade_date
         AND r.calc_version = 'rolling_qfq_v1'
        LEFT JOIN {{stock_moneyflow_ths}} smf
          ON smf.ts_code = s.ts_code
         AND smf.trade_date = s.trade_date
        LEFT JOIN index_market_factors imf
          ON imf.trade_date = s.trade_date
        WHERE s.trade_date = $1
        ";

const DB_NATIVE_PREVIOUS_MONTH_MACD_QUERY: &str = "
        SELECT DISTINCT ON (a.ts_code)
            a.ts_code,
            a.trade_date,
            a.monthly_hist_x2_asof::double precision / 2.0 AS macd_monthly_hist
        FROM {{stock_daily_asof_indicators}} a
        WHERE a.trade_date >= (date_trunc('month', $1::date) - INTERVAL '1 month')::date
          AND a.trade_date < date_trunc('month', $1::date)::date
          AND a.calc_version = 'macd_qfq_12_26_9_v1'
        ORDER BY a.ts_code, a.trade_date DESC
        ";

const DB_NATIVE_THS_SECTOR_EXTRAS_QUERY: &str = "
        WITH recent_trade_dates AS (
            SELECT trade_date
            FROM (
                SELECT DISTINCT trade_date
                FROM {{stock_stk_factor_pro}}
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
            FROM {{index_idx_factor_pro}} i
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
            FROM {{index_limit_cpt_list}}
            WHERE trade_date = $1
            GROUP BY ts_code, trade_date
        ),
        current_ths_membership AS (
            SELECT
                ts_code,
                con_code
            FROM {{index_ths_member}}
        ),
        ths_sector_base AS (
            SELECT
                d.ts_code,
                d.trade_date,
                d.close::double precision AS close,
                lag(d.close, 5) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date)::double precision AS ths_close_5_ago,
                lag(d.close, 20) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date)::double precision AS ths_close_20_ago,
                avg(d.close::double precision) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ths_close_ma20
            FROM {{index_ths_daily}} d
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
            FROM {{index_ths_daily}} d
            LEFT JOIN {{index_moneyflow_cnt_ths}} mf
              ON mf.ts_code = d.ts_code
             AND mf.trade_date = d.trade_date
            LEFT JOIN index_limit_cpt_daily il
              ON il.ts_code = d.ts_code
             AND il.trade_date = d.trade_date
            LEFT JOIN {{index_daily_asof_indicators}} ia
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
            FROM {{stock_stk_factor_pro}} s
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
          AND (
              (p.period_type = 'daily' AND p.period_end_date < $2)
              OR (p.period_type = 'weekly' AND p.period_end_date < date_trunc('week', $2::date)::date)
              OR (p.period_type = 'monthly' AND p.period_end_date < date_trunc('month', $2::date)::date)
          )
          AND p.calc_version = 'macd_qfq_12_26_9_v1'
          AND p.period_count IS NOT NULL
        ORDER BY p.ts_code, p.period_type, p.period_end_date DESC
        ";

const INSTRUMENT_INFO_QUERY: &str = "
        WITH requested AS (
            SELECT unnest($1::text[]) AS ts_code
        ),
        ths_name AS (
            SELECT
                con_code AS ts_code,
                max(con_name) AS name
            FROM index_ths_member
            WHERE con_code = ANY($1)
            GROUP BY con_code
        ),
        ths_industry AS (
            SELECT DISTINCT ON (m.con_code)
                m.con_code AS ts_code,
                i.name AS industry
            FROM index_ths_member m
            JOIN index_ths i ON i.ts_code = m.ts_code
            WHERE m.con_code = ANY($1)
              AND i.type = 'I'
              AND NULLIF(btrim(i.name), '') IS NOT NULL
            ORDER BY
                m.con_code,
                CASE WHEN i.name LIKE '%(A股)' THEN 1 ELSE 0 END,
                i.count ASC NULLS LAST,
                i.name ASC
        )
        SELECT
            r.ts_code,
            COALESCE(NULLIF(btrim(s.name), ''), ths_name.name) AS name,
            COALESCE(NULLIF(btrim(s.industry), ''), ths_industry.industry) AS industry
        FROM requested r
        LEFT JOIN stock_basic s ON s.ts_code = r.ts_code
        LEFT JOIN ths_name ON ths_name.ts_code = r.ts_code
        LEFT JOIN ths_industry ON ths_industry.ts_code = r.ts_code
        ORDER BY r.ts_code ASC
        ";

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

const DB_NATIVE_FACTOR_COLUMNS: &[&str] = &[
    "_source_close_qfq",
    "amount",
    "_czsc_snapshot_available",
    "_czsc_source_bar_valid",
    "_czsc_status_code",
    "_czsc_available_finished_bi_count",
    "_czsc_recent_bi_count",
    "_czsc_last_bi_direction_code",
    "_czsc_last_bi_start_day",
    "_czsc_last_bi_end_day",
    "_czsc_last_bi_high",
    "_czsc_last_bi_low",
    "_czsc_last_bi_mid",
    "_czsc_latest_zs_start_day",
    "_czsc_latest_zs_end_day",
    "_czsc_latest_zs_bi_count",
    "_czsc_latest_zs_zg",
    "_czsc_latest_zs_zd",
    "_czsc_latest_zs_zz",
    "_czsc_recent_peak_day",
    "_czsc_recent_peak_high",
    "_czsc_post_peak_first_bear_day",
    "_czsc_post_peak_first_bear_open",
    "_czsc_post_peak_first_bear_high",
    "_czsc_post_peak_first_bear_low",
    "_czsc_post_peak_first_bear_close",
    "_czsc_post_peak_first_bear_missing",
];

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

pub fn fetch_db_native_daily_window(
    dsn: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Vec<MarketRow>> {
    Ok(fetch_db_native_daily_dataset(dsn, start_date, end_date)?.rows)
}

pub fn fetch_db_native_daily_dataset(
    dsn: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<MarketDataset> {
    fetch_db_native_daily_dataset_with_preflight(dsn, start_date, end_date)
}

pub fn fetch_db_native_daily_window_for_intraday(
    dsn: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Vec<MarketRow>> {
    Ok(fetch_db_native_daily_dataset_for_intraday(dsn, start_date, end_date)?.rows)
}

pub fn fetch_db_native_daily_dataset_for_intraday(
    dsn: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<MarketDataset> {
    fetch_db_native_daily_dataset_with_preflight(dsn, start_date, end_date)
}

fn fetch_db_native_daily_dataset_with_preflight(
    dsn: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<MarketDataset> {
    let strict_tables = resolve_db_check_tables()?;
    let mut client = Client::connect(dsn, NoTls)?;
    configure_daily_window_session(&mut client)?;
    let mut transaction = client
        .build_transaction()
        .isolation_level(IsolationLevel::RepeatableRead)
        .read_only(true)
        .start()?;
    let plan = preflight_db_native_load(&mut transaction, start_date, end_date, &strict_tables)?;

    let mut market_rows = Vec::new();
    {
        let query = plan.adapt_query(DB_NATIVE_DAILY_WINDOW_QUERY);
        let mut rows = transaction.query_raw(&query, &[&start_date, &end_date])?;
        while let Some(row) = rows.next()? {
            market_rows.push(db_native_market_row_from_db_row(row)?);
        }
    }
    let pick_date_extras_query = plan.adapt_query(DB_NATIVE_PICK_DATE_EXTRAS_QUERY);
    merge_pick_date_extras(
        &mut transaction,
        &pick_date_extras_query,
        end_date,
        &mut market_rows,
    )?;
    let previous_month_macd_query = plan.adapt_query(DB_NATIVE_PREVIOUS_MONTH_MACD_QUERY);
    merge_previous_month_macd(
        &mut transaction,
        &previous_month_macd_query,
        end_date,
        &mut market_rows,
    )?;
    let ths_sector_extras_query = plan.adapt_query(DB_NATIVE_THS_SECTOR_EXTRAS_QUERY);
    merge_ths_sector_extras(
        &mut transaction,
        &ths_sector_extras_query,
        end_date,
        &mut market_rows,
    )?;
    transaction.commit()?;
    Ok(MarketDataset {
        rows: market_rows,
        db_data_gaps: plan.db_data_gaps,
    })
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

fn merge_pick_date_extras<C: postgres::GenericClient>(
    client: &mut C,
    query: &str,
    end_date: NaiveDate,
    market_rows: &mut [MarketRow],
) -> anyhow::Result<()> {
    let mut extras_by_key: BTreeMap<(String, NaiveDate), BTreeMap<String, f64>> = BTreeMap::new();
    let rows = client.query(query, &[&end_date])?;
    for row in rows {
        let ts_code: String = row.try_get("ts_code")?;
        let trade_date: NaiveDate = row.try_get("trade_date")?;
        let mut factors = BTreeMap::new();
        for column in DB_NATIVE_PICK_DATE_FACTOR_COLUMNS {
            if let Some(value) = optional_option_f64(&row, column)?
                && value.is_finite()
            {
                factors.insert((*column).to_string(), value);
            }
        }
        if !factors.is_empty() {
            extras_by_key.insert((ts_code, trade_date), factors);
        }
    }
    for row in market_rows
        .iter_mut()
        .filter(|row| row.trade_date == end_date)
    {
        if let Some(extras) = extras_by_key.remove(&(row.ts_code.clone(), row.trade_date)) {
            row.db_factors.extend(extras);
        }
    }
    Ok(())
}

fn merge_previous_month_macd<C: postgres::GenericClient>(
    client: &mut C,
    query: &str,
    end_date: NaiveDate,
    market_rows: &mut [MarketRow],
) -> anyhow::Result<()> {
    let mut previous_by_code = BTreeMap::new();
    for row in client.query(query, &[&end_date])? {
        let ts_code: String = row.try_get("ts_code")?;
        let trade_date: NaiveDate = row.try_get("trade_date")?;
        if let Some(histogram) =
            optional_option_f64(&row, "macd_monthly_hist")?.filter(|value| value.is_finite())
        {
            previous_by_code.insert(ts_code, (trade_date, histogram));
        }
    }
    // 挂在原日期上，由 prepare_rows 与本月柱一起换算到选股日的前复权基准。
    for row in market_rows {
        if let Some(&(trade_date, histogram)) = previous_by_code.get(row.ts_code.as_str())
            && row.trade_date == trade_date
        {
            row.db_factors
                .insert("macd_monthly_hist".to_string(), histogram);
        }
    }
    Ok(())
}

fn merge_ths_sector_extras<C: postgres::GenericClient>(
    client: &mut C,
    query: &str,
    end_date: NaiveDate,
    market_rows: &mut [MarketRow],
) -> anyhow::Result<()> {
    let mut extras_by_key: BTreeMap<(String, NaiveDate), BTreeMap<String, f64>> = BTreeMap::new();
    let rows = client.query(query, &[&end_date])?;
    for row in rows {
        let ts_code: String = row.try_get("ts_code")?;
        let trade_date: NaiveDate = row.try_get("trade_date")?;
        let mut factors = BTreeMap::new();
        for column in DB_NATIVE_THS_SECTOR_FACTOR_COLUMNS {
            if let Some(value) = optional_option_f64(&row, column)?
                && value.is_finite()
            {
                factors.insert((*column).to_string(), value);
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
    let source_close_qfq = row.db_factors.get("_source_close_qfq").copied();
    let mut db_factors = db_factor_values_iter(row.db_factors);
    if let Some(reference) = source_close_qfq {
        db_factors.insert(
            "_source_close_qfq".to_string(),
            reference.unwrap_or(f64::NAN),
        );
    }
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
        db_factors,
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
            "FROM {{stock_stk_factor_pro}} s",
            "s.trade_date BETWEEN (SELECT start_date FROM query_params) AND (SELECT end_date FROM query_params)",
            "s.open::double precision AS open",
            "s.high::double precision AS high",
            "s.low::double precision AS low",
            "s.close::double precision AS close",
            "s.adj_factor::double precision AS adj_factor",
            "s.vol::double precision AS vol",
            "s.amount::double precision AS amount",
            "s.turnover_rate::double precision AS turnover_rate",
            "LEFT JOIN {{stock_daily_czsc_structure}} c",
            "c.ts_code = s.ts_code",
            "c.trade_date = s.trade_date",
            "c.calc_version = 'czsc_structure_qfq_min6_r7_v1'",
            "c.source_bar_valid",
            "c.available_finished_bi_count",
            "c.last_bi_direction",
            "c.latest_zs_zg",
            "c.latest_zs_zd",
            "c.latest_zs_zz",
            "c.recent_peak_high",
            "c.post_peak_first_bear_open",
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
        assert!(!DB_NATIVE_DAILY_WINDOW_QUERY.contains("left_peak_qfq_v1"));
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
    fn db_native_daily_window_keeps_raw_ohlc_and_carries_qfq_reference_for_alignment() {
        assert!(DB_NATIVE_DAILY_WINDOW_QUERY.contains("s.close::double precision AS close"));
        assert!(
            DB_NATIVE_DAILY_WINDOW_QUERY
                .contains("s.close_qfq::double precision AS _source_close_qfq")
        );
        assert!(DB_NATIVE_FACTOR_COLUMNS.contains(&"_source_close_qfq"));
    }

    #[test]
    fn db_native_row_preserves_missing_qfq_reference_for_price_basis_validation() {
        for reference in [None, Some(f64::NAN), Some(5.0)] {
            let mapped = db_native_market_row_from_values(DbNativeDailyRow {
                ts_code: "000001.SZ".to_string(),
                trade_date: NaiveDate::from_ymd_opt(2026, 1, 30).unwrap(),
                open: 10.0,
                high: 11.0,
                low: 9.0,
                close: 10.0,
                adj_factor: Some(1.0),
                vol: 100.0,
                turnover_rate: None,
                db_factors: BTreeMap::from([("_source_close_qfq".to_string(), reference)]),
            })
            .unwrap();
            let actual = mapped
                .db_factors
                .get("_source_close_qfq")
                .copied()
                .expect("reference must remain present even when missing");
            if reference.is_some_and(f64::is_finite) {
                assert_eq!(Some(actual), reference);
            } else {
                assert!(actual.is_nan());
            }
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
            "LEFT JOIN {{stock_moneyflow_ths}} smf",
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
            "FROM {{index_idx_factor_pro}} i",
            "WHERE i.ts_code IN ('000001.SH', '399303.SZ')",
            "index_market_factors AS",
            "max(ret5_pct) FILTER (WHERE ts_code = '000001.SH')::double precision AS market_sse_ret5_pct",
            "max(ret5_pct) FILTER (WHERE ts_code = '399303.SZ')::double precision AS market_cn2000_ret5_pct",
            "CASE WHEN count(ret5_pct) = 2 THEN avg(ret5_pct)::double precision END AS market_broad_ret5_pct",
            "LEFT JOIN index_market_factors imf",
            "LEFT JOIN {{stock_daily_asof_indicators}} a",
            "LEFT JOIN {{stock_daily_rolling_factors}} r",
            "a.calc_version = 'macd_qfq_12_26_9_v1'",
            "a.daily_hist_x2_asof::double precision / 2.0 AS macd_daily_hist",
            "a.weekly_hist_x2_asof::double precision / 2.0 AS macd_weekly_hist",
            "a.monthly_hist_x2_asof::double precision / 2.0 AS macd_monthly_hist",
            "r.calc_version = 'rolling_qfq_v1'",
            "r.position_90d::double precision AS rolling_position_90d",
            "r.close_to_20d_max_close_pct::double precision AS close_to_20d_max_close_pct",
        ] {
            assert!(
                DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        assert!(!DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("stock_daily_left_peak"));
        assert!(!DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("left_peak_"));
        assert!(!DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("prev_hist"));
        assert!(
            !DB_NATIVE_PICK_DATE_FACTOR_COLUMNS
                .iter()
                .any(|column| column.ends_with("_prev_hist"))
        );
        assert!(!DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("s.kdj_j_qfq"));
        assert!(DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("CASE"));
        assert!(
            DB_NATIVE_PICK_DATE_EXTRAS_QUERY
                .contains("WHEN s.kdj_k_qfq IS NOT NULL AND s.kdj_d_qfq IS NOT NULL")
        );
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
    fn db_native_queries_consume_all_relation_placeholders() {
        let plan = crate::db_check::plan_from_inspections(&BTreeMap::new());

        for query in [
            DB_NATIVE_DAILY_WINDOW_QUERY,
            DB_NATIVE_PICK_DATE_EXTRAS_QUERY,
            DB_NATIVE_PREVIOUS_MONTH_MACD_QUERY,
            DB_NATIVE_THS_SECTOR_EXTRAS_QUERY,
        ] {
            let adapted = plan.adapt_query(query);
            assert!(!adapted.contains("{{"), "unresolved relation placeholder");
        }
    }

    #[test]
    fn db_module_no_longer_exposes_legacy_daily_market_loader() {
        let source = include_str!("db.rs")
            .split("#[cfg(test)]")
            .next()
            .unwrap_or_default();

        assert!(!source.contains("const DAILY_WINDOW_QUERY"));
        assert!(!source.contains("pub fn fetch_daily_window"));
        assert!(!source.contains("DB_NATIVE_COVERAGE_PROBE_QUERY"));
        assert!(!source.contains("probe_db_native_coverage"));
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
            "FROM {{index_ths_member}}",
            "index_market_factors AS",
            "max(ret5_pct) FILTER (WHERE ts_code = '000001.SH')::double precision AS market_sse_ret5_pct",
            "max(ret5_pct) FILTER (WHERE ts_code = '399303.SZ')::double precision AS market_cn2000_ret5_pct",
            "ths_sector_daily AS",
            "FROM {{index_ths_daily}} d",
            "lag(d.close, 5) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date)::double precision AS ths_close_5_ago",
            "LEFT JOIN {{index_moneyflow_cnt_ths}} mf",
            "index_limit_cpt_daily AS",
            "FROM {{index_limit_cpt_list}}",
            "GROUP BY ts_code, trade_date",
            "LEFT JOIN index_limit_cpt_daily il",
            "LEFT JOIN {{index_daily_asof_indicators}} ia",
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
            "p.period_type = 'daily' AND p.period_end_date < $2",
            "p.period_type = 'weekly' AND p.period_end_date < date_trunc('week', $2::date)::date",
            "p.period_type = 'monthly' AND p.period_end_date < date_trunc('month', $2::date)::date",
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
    fn instrument_info_query_uses_stock_basic_with_ths_industry_fallback() {
        for fragment in [
            "WITH requested AS",
            "SELECT unnest($1::text[]) AS ts_code",
            "LEFT JOIN stock_basic s ON s.ts_code = r.ts_code",
            "COALESCE(NULLIF(btrim(s.name), ''), ths_name.name) AS name",
            "FROM index_ths_member m",
            "JOIN index_ths i",
            "i.type = 'I'",
            "COALESCE(NULLIF(btrim(s.industry), ''), ths_industry.industry) AS industry",
        ] {
            assert!(
                INSTRUMENT_INFO_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        assert!(!INSTRUMENT_INFO_QUERY.contains("NULL::text AS industry"));
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
                ("_czsc_snapshot_available".to_string(), Some(1.0)),
                ("_czsc_status_code".to_string(), Some(4.0)),
                ("_czsc_recent_peak_high".to_string(), Some(11.8)),
                ("_czsc_post_peak_first_bear_open".to_string(), Some(11.2)),
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
                (
                    "stock_env_market_sector_ret5_sum_pct".to_string(),
                    Some(7.6),
                ),
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
        assert_eq!(mapped.db_factors["_czsc_snapshot_available"], 1.0);
        assert_eq!(mapped.db_factors["_czsc_status_code"], 4.0);
        assert_eq!(mapped.db_factors["_czsc_recent_peak_high"], 11.8);
        assert_eq!(mapped.db_factors["_czsc_post_peak_first_bear_open"], 11.2);
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
        assert_eq!(
            mapped.db_factors["stock_env_sector_vs_broad_ret20_pct"],
            9.6
        );
        assert_eq!(mapped.db_factors["stock_env_style_ret5_spread_pct"], 0.6);
        assert_eq!(
            mapped.db_factors["stock_env_market_sector_ret5_sum_pct"],
            7.6
        );
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
    #[ignore = "需本地 .env 数据库；只读核对 2026-11-13 的 17 只 SCM 样本，使用临时 runtime"]
    fn scm_previous_month_macd_database_regression() -> anyhow::Result<()> {
        use crate::cache::prepared_cache_start_date;
        use crate::model::Method;
        use crate::screening::{
            PoolSource, ScreenRequest, run_db_native_screen_with_dataset_loader,
        };

        let codes = [
            "688475.SH",
            "601985.SH",
            "601668.SH",
            "601288.SH",
            "601077.SH",
            "600993.SH",
            "600900.SH",
            "600377.SH",
            "600028.SH",
            "600019.SH",
            "300138.SZ",
            "003816.SZ",
            "002299.SZ",
            "000999.SZ",
            "000895.SZ",
            "000429.SZ",
            "000423.SZ",
        ];
        let pick_date = NaiveDate::from_ymd_opt(2026, 11, 13).unwrap();
        let start_date = prepared_cache_start_date(pick_date);
        let dsn = crate::config::resolve_dsn_from_env(None)?;
        let mut client = Client::connect(&dsn, NoTls)?;
        configure_daily_window_session(&mut client)?;
        let mut transaction = client
            .build_transaction()
            .isolation_level(IsolationLevel::RepeatableRead)
            .read_only(true)
            .start()?;
        transaction.batch_execute("SET LOCAL statement_timeout = '60s'")?;
        let plan = preflight_db_native_load(
            &mut transaction,
            start_date,
            pick_date,
            &resolve_db_check_tables()?,
        )?;
        let code_filter = codes.map(|code| format!("'{code}'")).join(", ");
        let scope_query = |query: &str| {
            format!(
                "SELECT sampled.* FROM ({}) sampled WHERE sampled.ts_code IN ({code_filter})",
                plan.adapt_query(query)
            )
        };
        let mut rows = transaction
            .query(
                &scope_query(DB_NATIVE_DAILY_WINDOW_QUERY),
                &[&start_date, &pick_date],
            )?
            .into_iter()
            .map(db_native_market_row_from_db_row)
            .collect::<anyhow::Result<Vec<_>>>()?;
        merge_pick_date_extras(
            &mut transaction,
            &scope_query(DB_NATIVE_PICK_DATE_EXTRAS_QUERY),
            pick_date,
            &mut rows,
        )?;
        merge_previous_month_macd(
            &mut transaction,
            &scope_query(DB_NATIVE_PREVIOUS_MONTH_MACD_QUERY),
            pick_date,
            &mut rows,
        )?;
        transaction.commit()?;

        let root = tempfile::tempdir()?;
        let request = ScreenRequest {
            method: Method::Scm,
            pick_date,
            runtime_root: root.path().to_path_buf(),
            dsn,
            recompute: false,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        };
        let output = run_db_native_screen_with_dataset_loader(request, |_, _, _| {
            Ok(MarketDataset {
                rows,
                db_data_gaps: plan.db_data_gaps,
            })
        })?;
        let result: serde_json::Value = serde_json::from_slice(&std::fs::read(output)?)?;
        assert_eq!(result["stats"]["total_symbols"], 17);
        assert_eq!(result["stats"]["fail_macd"], 0, "{result}");
        assert!(
            result["candidates"]
                .as_array()
                .unwrap()
                .iter()
                .any(|row| row["code"] == "601985.SH")
        );
        println!("SCM_MONTHLY_DATABASE_PROBE {}", result["stats"]);
        Ok(())
    }

    #[test]
    #[ignore = "需本地 .env 数据库；仅四只股票并使用临时 runtime"]
    fn historical_qfq_price_basis_samples_match_formal_czsc_and_reuse_cache() {
        let samples = [
            ("603409.SH", (2026, 1, 30)),
            ("003026.SZ", (2026, 2, 25)),
            ("301328.SZ", (2026, 2, 11)),
            ("688268.SH", (2026, 4, 20)),
        ];
        std::thread::scope(|scope| {
            let workers = samples
                .into_iter()
                .map(|(code, (year, month, day))| {
                    scope.spawn(move || {
                        historical_qfq_price_basis_probe(
                            code,
                            NaiveDate::from_ymd_opt(year, month, day).unwrap(),
                        )
                    })
                })
                .collect::<Vec<_>>();
            for worker in workers {
                let report = worker
                    .join()
                    .expect("price basis worker panicked")
                    .expect("price basis probe failed");
                println!("PRICE_BASIS_PROBE {report}");
            }
        });
    }

    fn historical_qfq_price_basis_probe(
        code: &str,
        pick_date: NaiveDate,
    ) -> anyhow::Result<serde_json::Value> {
        use crate::cache::{
            load_prepared_cache, prepared_cache_data_path, prepared_cache_meta_path,
            prepared_cache_start_date,
        };
        use crate::factors::registry::build_candidate_factor_rows;
        use crate::factors::types::FactorValue;
        use crate::model::{Candidate, Method};
        use crate::screening::{
            PoolSource, ScreenRequest, run_db_native_screen_with_dataset_loader,
        };

        let dsn = crate::config::resolve_dsn_from_env(None)?;
        let root = tempfile::tempdir()?;
        let start_date = prepared_cache_start_date(pick_date);
        let mut client = Client::connect(&dsn, NoTls)?;
        configure_daily_window_session(&mut client)?;
        let mut transaction = client
            .build_transaction()
            .isolation_level(IsolationLevel::RepeatableRead)
            .read_only(true)
            .start()?;
        transaction.batch_execute("SET LOCAL statement_timeout = '60s'")?;
        let plan = preflight_db_native_load(
            &mut transaction,
            start_date,
            pick_date,
            &resolve_db_check_tables()?,
        )?;
        let scope_query = |query: &str| {
            format!(
                "SELECT sampled.* FROM ({}) sampled WHERE sampled.ts_code IN ('{code}', '000001.SZ')",
                plan.adapt_query(query)
            )
        };
        let mut rows = transaction
            .query(
                &scope_query(DB_NATIVE_DAILY_WINDOW_QUERY),
                &[&start_date, &pick_date],
            )?
            .into_iter()
            .map(db_native_market_row_from_db_row)
            .collect::<anyhow::Result<Vec<_>>>()?;
        merge_pick_date_extras(
            &mut transaction,
            &scope_query(DB_NATIVE_PICK_DATE_EXTRAS_QUERY),
            pick_date,
            &mut rows,
        )?;
        merge_ths_sector_extras(
            &mut transaction,
            &scope_query(DB_NATIVE_THS_SECTOR_EXTRAS_QUERY),
            pick_date,
            &mut rows,
        )?;
        transaction.commit()?;
        rows.sort_by_key(|row| row.trade_date);
        let latest = rows
            .iter()
            .rev()
            .find(|row| row.ts_code == code)
            .expect("sample history is empty");
        assert_eq!(latest.trade_date, pick_date);
        let close = latest.close;
        let qfq_close = latest.db_factors["_source_close_qfq"];
        let qfq_peak = latest.db_factors["_czsc_recent_peak_high"];
        let peak_day = latest.db_factors["_czsc_recent_peak_day"];
        let qfq_ma25 = latest.db_factors["rolling_ma25_qfq"];
        let qfq_dif = latest.db_factors["macd_daily_dif"];
        let expected_distance = 100.0 * (qfq_close / qfq_peak - 1.0);
        let multiplier = close / qfq_close;
        let expected_turnover = rows
            .iter()
            .rev()
            .filter(|row| row.ts_code == code)
            .take(43)
            .map(|row| (row.open + row.close) / 2.0 * row.vol)
            .sum::<f64>();
        let loaded_rows = rows.len();
        let request = |method| ScreenRequest {
            method,
            pick_date,
            runtime_root: root.path().to_path_buf(),
            dsn: dsn.clone(),
            recompute: false,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: true,
            environment_state: Some("weak".to_string()),
        };
        let candidate_path =
            run_db_native_screen_with_dataset_loader(request(Method::Scm), |_, _, _| {
                Ok(MarketDataset {
                    rows,
                    db_data_gaps: plan.db_data_gaps,
                })
            })?;
        let selected_scm: serde_json::Value =
            serde_json::from_slice(&std::fs::read(candidate_path)?)?;
        let prepared =
            load_prepared_cache(root.path(), Method::Scm, pick_date, start_date, pick_date)?
                .unwrap();
        let latest = prepared
            .iter()
            .rev()
            .find(|row| row.ts_code == code)
            .unwrap();
        assert_eq!(latest.close, close);
        assert!((latest.ma25.unwrap() - qfq_ma25 * multiplier).abs() < 1e-8);
        assert!((latest.dif - qfq_dif * multiplier).abs() < 1e-8);
        assert!((latest.turnover_n / expected_turnover - 1.0).abs() < 1e-10);
        assert!(
            prepared
                .iter()
                .all(|row| !row.db_factors.contains_key("_source_close_qfq"))
        );
        let local_ma25 = prepared
            .iter()
            .rev()
            .filter(|row| row.ts_code == code)
            .take(25)
            .map(|row| row.close)
            .sum::<f64>()
            / 25.0;
        assert!((latest.ma25.unwrap() - local_ma25).abs() < 0.0001 * multiplier);
        let factors = build_candidate_factor_rows(
            &[Candidate {
                code: code.to_string(),
                pick_date,
                close,
                turnover_n: latest.turnover_n,
                signal: Some("SCM".to_string()),
                yellow_b1: Some(false),
            }],
            &prepared,
            Method::Scm,
            Some("weak"),
        );
        let FactorValue::Number(actual_distance) =
            factors[0].factors["czsc_close_to_recent_peak_pct"]
        else {
            panic!("formal peak distance is missing");
        };
        assert!(
            (100.0 * (latest.close / latest.db_factors["_czsc_recent_peak_high"] - 1.0)
                - expected_distance)
                .abs()
                < 1e-9
        );
        assert!(
            (actual_distance - expected_distance).abs() < 0.00005,
            "{code}: exported={actual_distance} expected={expected_distance}"
        );
        let data_path = prepared_cache_data_path(root.path(), pick_date);
        let meta_path = prepared_cache_meta_path(root.path(), pick_date);
        let data_before = std::fs::read(&data_path)?;
        let meta_before = std::fs::read(&meta_path)?;
        let data_modified = std::fs::metadata(&data_path)?.modified()?;
        let meta_modified = std::fs::metadata(&meta_path)?.modified()?;
        let pbm_path =
            run_db_native_screen_with_dataset_loader(request(Method::Pbm), |_, _, _| {
                panic!("PBM must reuse the corrected SCM cache without loading the database")
            })?;
        let selected_pbm: serde_json::Value = serde_json::from_slice(&std::fs::read(pbm_path)?)?;
        assert_eq!(std::fs::read(&data_path)?, data_before);
        assert_eq!(std::fs::read(&meta_path)?, meta_before);
        assert_eq!(std::fs::metadata(data_path)?.modified()?, data_modified);
        assert_eq!(std::fs::metadata(meta_path)?.modified()?, meta_modified);
        Ok(serde_json::json!({
            "code": code, "pick_date": pick_date, "rows_loaded": loaded_rows,
            "raw_close": close, "source_close_qfq": qfq_close,
            "peak_day": peak_day, "source_peak_qfq": qfq_peak,
            "aligned_peak": latest.db_factors["_czsc_recent_peak_high"],
            "old_distance_pct": 100.0 * (close / qfq_peak - 1.0),
            "new_distance_pct": actual_distance, "expected_distance_pct": expected_distance,
            "old_ma25_distance_pct": 100.0 * (close / qfq_ma25 - 1.0),
            "new_ma25_distance_pct": 100.0 * (close / latest.ma25.unwrap() - 1.0),
            "ma25_after": latest.ma25, "local_ma25": local_ma25,
            "dif_before": qfq_dif, "dif_after": latest.dif,
            "selected_scm": selected_scm["candidates"].as_array().unwrap().iter().any(|row| row["code"] == code),
            "selected_pbm": selected_pbm["candidates"].as_array().unwrap().iter().any(|row| row["code"] == code),
            "shared_cache_untouched": true,
        }))
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
        assert!(row.db_factors.contains_key("_czsc_snapshot_available"));
        assert!(row.db_factors.contains_key("_czsc_status_code"));
        assert!(
            !row.db_factors
                .keys()
                .any(|key| key.starts_with("left_peak_"))
        );
        assert!(row.db_factors.contains_key("stock_mf_net_amount"));
        assert!(
            row.db_factors
                .contains_key("large_net_amount_to_amount_pct")
        );
        assert!(row.db_factors.contains_key("mid_net_amount_to_amount_pct"));
        assert!(
            row.db_factors
                .contains_key("small_net_amount_to_amount_pct")
        );
        assert!(row.db_factors.contains_key("net_mf_amount_to_amount_pct"));
        assert!(row.db_factors.contains_key("ths_main_limit_up_count"));
        assert!(row.db_factors.contains_key("ths_best_limit_up_count"));
        assert!(row.db_factors.contains_key("ths_any_limit_up_sector_flag"));
        assert!(row.db_factors.contains_key("ths_limit_up_sector_count"));
        assert!(row.db_factors.contains_key("ths_limit_up_sector_ratio"));
        assert!(row.db_factors.contains_key("stock_env_sector_ret5_pct"));
        assert!(
            row.db_factors
                .contains_key("stock_env_sector_vs_broad_ret5_pct")
        );
        assert!(
            row.db_factors
                .contains_key("stock_env_style_ret5_spread_pct")
        );
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
    fn db_native_window_session_settings_avoid_parallel_dsm_with_bounded_work_mem() {
        assert!(DAILY_WINDOW_SESSION_SETTINGS_SQL.contains("max_parallel_workers_per_gather = 0"));
        assert!(DAILY_WINDOW_SESSION_SETTINGS_SQL.contains("work_mem = '16MB'"));
    }
}
