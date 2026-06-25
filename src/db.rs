use chrono::NaiveDate;
use postgres::{Client, NoTls, fallible_iterator::FallibleIterator};
use std::collections::BTreeMap;

use crate::model::{InstrumentInfo, MarketRow};

const DAILY_WINDOW_SESSION_SETTINGS_SQL: &str = "
    SET max_parallel_workers_per_gather = 2;
    SET work_mem = '64MB';
";

const DAILY_WINDOW_QUERY: &str = "
        WITH index_returns AS (
            SELECT
                ts_code,
                group_name,
                trade_date,
                close::double precision AS close,
                lag(close::double precision, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) AS close_1d,
                lag(close::double precision, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) AS close_5d,
                lag(close::double precision, 20) OVER (PARTITION BY ts_code ORDER BY trade_date) AS close_20d
            FROM daily_index
            WHERE trade_date BETWEEN $1 AND $2
              AND group_name IN ('major', 'sw_secondary')
              AND close IS NOT NULL
        ),
        index_base AS (
            SELECT
                ts_code,
                group_name,
                trade_date,
                close,
                CASE
                    WHEN close_1d IS NOT NULL AND close_1d != 0
                    THEN (close - close_1d) / close_1d * 100.0
                END AS ret_1d_pct,
                CASE
                    WHEN close_5d IS NOT NULL AND close_5d != 0
                    THEN (close - close_5d) / close_5d * 100.0
                END AS ret5_pct,
                CASE
                    WHEN close_20d IS NOT NULL AND close_20d != 0
                    THEN (close - close_20d) / close_20d * 100.0
                END AS ret20_pct
            FROM index_returns
        ),
        index_features AS (
            SELECT
                ts_code,
                group_name,
                trade_date,
                ret5_pct,
                ret20_pct,
                CASE
                    WHEN ma20_count = 20 AND ma20 != 0
                    THEN (close - ma20) / ma20 * 100.0
                END AS ma20_bias_pct,
                CASE
                    WHEN ret20_count >= 20
                    THEN ret20_std
                END AS volatility20_pct
            FROM (
                SELECT
                    index_base.*,
                    avg(close) OVER index_win20 AS ma20,
                    count(close) OVER index_win20 AS ma20_count,
                    stddev_samp(ret_1d_pct) OVER index_win20 AS ret20_std,
                    count(ret_1d_pct) OVER index_win20 AS ret20_count
                FROM index_base
                WINDOW index_win20 AS (
                    PARTITION BY ts_code
                    ORDER BY trade_date
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                )
            ) indexed
        ),
        market_broad_features AS (
            SELECT
                trade_date,
                CASE WHEN count(ret5_pct) = 2 THEN avg(ret5_pct) END AS market_broad_ret5_pct,
                CASE WHEN count(ret20_pct) = 2 THEN avg(ret20_pct) END AS market_broad_ret20_pct,
                CASE WHEN count(ma20_bias_pct) = 2 THEN avg(ma20_bias_pct) END AS market_broad_ma20_bias_pct,
                CASE WHEN count(volatility20_pct) = 2 THEN avg(volatility20_pct) END AS market_broad_volatility20_pct
            FROM index_features
            WHERE group_name = 'major'
              AND ts_code IN ('000001.SH', '399303.SZ')
            GROUP BY trade_date
        ),
        sw_member_raw AS (
            SELECT
                ts_code,
                l2_code
            FROM sw_industry_member
            WHERE src = 'SW2021'
              AND l2_code IS NOT NULL
        ),
        sw_member AS (
            SELECT
                ts_code,
                min(l2_code) AS l2_code
            FROM sw_member_raw
            GROUP BY ts_code
            HAVING count(DISTINCT l2_code) = 1
        ),
        sw_l2_ret5_ranks AS (
            SELECT
                ts_code,
                trade_date,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY ret5_pct) * 100.0 AS sw_l2_ret5_rank_pct
            FROM index_features
            WHERE group_name = 'sw_secondary'
              AND ret5_pct IS NOT NULL
        ),
        sw_l2_ret20_ranks AS (
            SELECT
                ts_code,
                trade_date,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY ret20_pct) * 100.0 AS sw_l2_ret20_rank_pct
            FROM index_features
            WHERE group_name = 'sw_secondary'
              AND ret20_pct IS NOT NULL
        ),
        sw_l2_features AS (
            SELECT
                f.ts_code,
                f.trade_date,
                f.ret5_pct,
                f.ret20_pct,
                f.ma20_bias_pct,
                f.volatility20_pct,
                r5.sw_l2_ret5_rank_pct,
                r20.sw_l2_ret20_rank_pct
            FROM index_features f
            LEFT JOIN sw_l2_ret5_ranks r5
              ON r5.ts_code = f.ts_code
             AND r5.trade_date = f.trade_date
            LEFT JOIN sw_l2_ret20_ranks r20
              ON r20.ts_code = f.ts_code
             AND r20.trade_date = f.trade_date
            WHERE f.group_name = 'sw_secondary'
        ),
        stock_industry_base AS (
            SELECT
                sim.l2_code,
                m.ts_code,
                m.trade_date,
                m.pct_chg::double precision AS pct_chg,
                m.close::double precision AS close,
                CASE
                    WHEN m.amount IS NOT NULL AND m.amount > 0
                    THEN m.amount::double precision
                END AS amount,
                m.net_mf_amount::double precision AS net_mf_amount,
                CASE
                    WHEN m.extra_market_jsonb ? 'up_limit'
                    THEN (m.extra_market_jsonb->>'up_limit')::double precision
                END AS up_limit,
                CASE
                    WHEN m.extra_market_jsonb ? 'down_limit'
                    THEN (m.extra_market_jsonb->>'down_limit')::double precision
                END AS down_limit
            FROM daily_market m
            INNER JOIN sw_member sim
              ON sim.ts_code = m.ts_code
            WHERE m.trade_date BETWEEN $1 AND $2
        ),
        market_daily_amount AS (
            SELECT
                trade_date,
                sum(amount) AS market_amount,
                sum(amount) FILTER (
                    WHERE net_mf_amount IS NOT NULL AND amount IS NOT NULL
                ) AS market_net_mf_amount_base
            FROM stock_industry_base
            GROUP BY trade_date
        ),
        stock_industry_ranked AS (
            SELECT
                stock_industry_base.*,
                row_number() OVER (
                    PARTITION BY trade_date, l2_code
                    ORDER BY amount DESC NULLS LAST
                ) AS amount_rank
            FROM stock_industry_base
        ),
        industry_daily AS (
            SELECT
                trade_date,
                l2_code,
                count(pct_chg) AS pct_count,
                count(*) FILTER (
                    WHERE close IS NOT NULL AND close != 0 AND up_limit IS NOT NULL
                ) AS limit_up_base_count,
                count(*) FILTER (
                    WHERE close IS NOT NULL AND close != 0 AND down_limit IS NOT NULL
                ) AS limit_down_base_count,
                count(*) FILTER (WHERE pct_chg > 0.0) AS up_count,
                count(*) FILTER (WHERE pct_chg >= 5.0) AS ge5_count,
                count(*) FILTER (
                    WHERE close IS NOT NULL
                      AND close != 0
                      AND up_limit IS NOT NULL
                      AND close <= up_limit
                      AND (up_limit - close) / close * 100.0 <= 0.2
                ) AS limit_up_count,
                count(*) FILTER (
                    WHERE close IS NOT NULL
                      AND close != 0
                      AND down_limit IS NOT NULL
                      AND close >= down_limit
                      AND (close - down_limit) / close * 100.0 <= 0.2
                ) AS limit_down_count,
                sum(amount) AS industry_amount,
                sum(net_mf_amount) FILTER (
                    WHERE net_mf_amount IS NOT NULL AND amount IS NOT NULL
                ) AS industry_net_mf_amount,
                sum(amount) FILTER (
                    WHERE net_mf_amount IS NOT NULL AND amount IS NOT NULL
                ) AS industry_net_mf_amount_base,
                sum(CASE WHEN amount_rank <= 1 THEN amount ELSE 0.0 END) AS top1_amount,
                sum(CASE WHEN amount_rank <= 3 THEN amount ELSE 0.0 END) AS top3_amount,
                sum(CASE WHEN amount_rank <= 5 THEN amount ELSE 0.0 END) AS top5_amount
            FROM stock_industry_ranked
            GROUP BY trade_date, l2_code
        ),
        industry_enriched AS (
            SELECT
                d.trade_date,
                d.l2_code,
                d.industry_amount,
                d.industry_net_mf_amount_base,
                CASE WHEN d.pct_count > 0 THEN d.up_count::double precision / d.pct_count::double precision END AS sw_l2_up_ratio,
                CASE WHEN d.pct_count > 0 THEN d.ge5_count::double precision / d.pct_count::double precision END AS sw_l2_ge5_ratio,
                CASE WHEN d.limit_up_base_count > 0 THEN d.limit_up_count::double precision / d.limit_up_base_count::double precision END AS sw_l2_limit_up_ratio,
                CASE WHEN d.limit_down_base_count > 0 THEN d.limit_down_count::double precision / d.limit_down_base_count::double precision END AS sw_l2_limit_down_ratio,
                CASE
                    WHEN a.market_amount IS NOT NULL AND a.market_amount != 0
                    THEN d.industry_amount / a.market_amount * 100.0
                END AS sw_l2_amount_share_pct,
                CASE
                    WHEN d.industry_amount IS NOT NULL AND d.industry_amount != 0
                    THEN d.top1_amount / d.industry_amount * 100.0
                END AS sw_l2_top1_amount_share_pct,
                CASE
                    WHEN d.industry_amount IS NOT NULL AND d.industry_amount != 0
                    THEN d.top3_amount / d.industry_amount * 100.0
                END AS sw_l2_top3_amount_share_pct,
                CASE
                    WHEN d.industry_amount IS NOT NULL AND d.industry_amount != 0
                    THEN d.top5_amount / d.industry_amount * 100.0
                END AS sw_l2_top5_amount_share_pct,
                CASE
                    WHEN d.industry_net_mf_amount_base IS NOT NULL AND d.industry_net_mf_amount_base != 0
                    THEN d.industry_net_mf_amount / d.industry_net_mf_amount_base * 100.0
                END AS sw_l2_net_mf_to_amount_pct,
                CASE
                    WHEN a.market_net_mf_amount_base IS NOT NULL AND a.market_net_mf_amount_base != 0
                    THEN d.industry_net_mf_amount / a.market_net_mf_amount_base * 100.0
                END AS sw_l2_net_mf_market_share_pct
            FROM industry_daily d
            LEFT JOIN market_daily_amount a
              ON a.trade_date = d.trade_date
        ),
        industry_windowed AS (
            SELECT
                enriched.*,
                CASE
                    WHEN amount_share_ma5_count = 5 AND amount_share_ma5 != 0
                    THEN sw_l2_amount_share_pct / amount_share_ma5
                END AS sw_l2_amount_share_ma5_ratio
            FROM (
                SELECT
                    industry_enriched.*,
                    avg(sw_l2_amount_share_pct) OVER industry_win5 AS amount_share_ma5,
                    count(sw_l2_amount_share_pct) OVER industry_win5 AS amount_share_ma5_count
                FROM industry_enriched
                WINDOW industry_win5 AS (
                    PARTITION BY l2_code
                    ORDER BY trade_date
                    ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
                )
            ) enriched
        ),
        industry_amount_ranks AS (
            SELECT
                l2_code,
                trade_date,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY sw_l2_amount_share_pct) * 100.0 AS sw_l2_amount_share_rank_pct
            FROM industry_windowed
            WHERE sw_l2_amount_share_pct IS NOT NULL
        ),
        industry_net_mf_ranks AS (
            SELECT
                l2_code,
                trade_date,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY sw_l2_net_mf_to_amount_pct) * 100.0 AS sw_l2_net_mf_rank_pct
            FROM industry_windowed
            WHERE sw_l2_net_mf_to_amount_pct IS NOT NULL
        ),
        industry_features AS (
            SELECT
                w.*,
                amount_ranks.sw_l2_amount_share_rank_pct,
                net_mf_ranks.sw_l2_net_mf_rank_pct
            FROM industry_windowed w
            LEFT JOIN industry_amount_ranks amount_ranks
              ON amount_ranks.l2_code = w.l2_code
             AND amount_ranks.trade_date = w.trade_date
            LEFT JOIN industry_net_mf_ranks net_mf_ranks
              ON net_mf_ranks.l2_code = w.l2_code
             AND net_mf_ranks.trade_date = w.trade_date
        )
        SELECT
            m.ts_code,
            m.trade_date,
            m.open::double precision AS open,
            m.high::double precision AS high,
            m.low::double precision AS low,
            m.close::double precision AS close,
            m.vol::double precision AS vol,
            m.turnover_rate::double precision AS turnover_rate,
            CASE
                WHEN m.extra_market_jsonb ? 'adj_factor'
                THEN (m.extra_market_jsonb->>'adj_factor')::double precision
            END AS adj_factor,
            CASE
                WHEN m.amount IS NOT NULL AND m.amount != 0
                 AND m.vol IS NOT NULL AND m.vol != 0
                THEN m.amount::double precision * 10.0 / m.vol::double precision
            END AS chip_vwap,
            CASE
                WHEN m.turnover_rate_f IS NOT NULL
                THEN m.turnover_rate_f::double precision / 100.0
                WHEN m.turnover_rate IS NOT NULL
                THEN m.turnover_rate::double precision / 100.0
            END AS chip_turnover,
            CASE
                WHEN m.trade_date = $2
                THEN m.turnover_rate_f::double precision
            END AS turnover_rate_f,
            CASE
                WHEN m.trade_date = $2 AND i.boll_mid IS NOT NULL AND i.boll_mid != 0
                THEN (i.boll_upper - i.boll_lower)::double precision / i.boll_mid::double precision * 100.0
            END AS boll_width_pct,
            CASE
                WHEN m.trade_date = $2
                THEN (i.extra_factors_jsonb->>'dmi_adxr_qfq')::double precision
            END AS dmi_adxr_qfq,
            CASE
                WHEN m.trade_date = $2
                THEN (i.extra_factors_jsonb->>'dmi_adx_qfq')::double precision
            END AS dmi_adx_qfq,
            CASE
                WHEN m.trade_date = $2
                THEN (i.extra_factors_jsonb->>'dmi_pdi_qfq')::double precision
            END AS dmi_pdi_qfq,
            CASE
                WHEN m.trade_date = $2
                THEN (i.extra_factors_jsonb->>'dmi_mdi_qfq')::double precision
            END AS dmi_mdi_qfq,
            CASE
                WHEN m.trade_date = $2
                 AND i.extra_factors_jsonb ? 'dmi_pdi_qfq'
                 AND i.extra_factors_jsonb ? 'dmi_mdi_qfq'
                THEN (i.extra_factors_jsonb->>'dmi_pdi_qfq')::double precision
                   - (i.extra_factors_jsonb->>'dmi_mdi_qfq')::double precision
            END AS dmi_pdi_mdi_spread_qfq,
            CASE
                WHEN m.trade_date = $2
                 AND i.extra_factors_jsonb ? 'dmi_adx_qfq'
                 AND i.extra_factors_jsonb ? 'dmi_adxr_qfq'
                THEN (i.extra_factors_jsonb->>'dmi_adx_qfq')::double precision
                   - (i.extra_factors_jsonb->>'dmi_adxr_qfq')::double precision
            END AS dmi_adx_adxr_gap_qfq,
            CASE
                WHEN m.trade_date = $2
                THEN (i.extra_factors_jsonb->>'wr_qfq')::double precision
            END AS wr_qfq,
            CASE
                WHEN m.trade_date = $2
                THEN (i.extra_factors_jsonb->>'mtm_qfq')::double precision
            END AS mtm_qfq,
            CASE
                WHEN m.trade_date = $2
                THEN (i.extra_factors_jsonb->>'roc_qfq')::double precision
            END AS roc_qfq,
            CASE
                WHEN m.trade_date = $2
                THEN (i.extra_factors_jsonb->>'trix_qfq')::double precision
            END AS trix_qfq,
            CASE
                WHEN m.trade_date = $2
                THEN (i.extra_factors_jsonb->>'obv_qfq')::double precision
            END AS obv_qfq,
            CASE
                WHEN m.trade_date = $2
                THEN (i.extra_factors_jsonb->>'vr_qfq')::double precision
            END AS vr_qfq,
            CASE
                WHEN m.trade_date = $2
                THEN (i.extra_factors_jsonb->>'psy_qfq')::double precision
            END AS psy_qfq,
            CASE
                WHEN m.trade_date = $2
                THEN (i.extra_factors_jsonb->>'bias1_qfq')::double precision
            END AS bias1_qfq,
            CASE
                WHEN m.trade_date = $2
                  AND m.close IS NOT NULL AND m.close != 0
                  AND m.extra_market_jsonb ? 'up_limit'
                THEN ((m.extra_market_jsonb->>'up_limit')::double precision - m.close::double precision)
                     / m.close::double precision * 100.0
            END AS dist_to_up_limit_pct,
            CASE
                WHEN m.trade_date = $2
                  AND m.close IS NOT NULL AND m.close != 0
                  AND m.extra_market_jsonb ? 'down_limit'
                THEN (m.close::double precision - (m.extra_market_jsonb->>'down_limit')::double precision)
                     / m.close::double precision * 100.0
            END AS dist_to_down_limit_pct,
            CASE
                WHEN m.trade_date = $2
                  AND m.amount IS NOT NULL AND m.amount != 0
                THEN m.net_mf_amount::double precision / m.amount::double precision * 100.0
            END AS net_mf_amount_to_amount_pct,
            CASE
                WHEN m.trade_date = $2
                  AND m.amount IS NOT NULL AND m.amount != 0
                THEN (
                    COALESCE((m.extra_market_jsonb->>'buy_elg_amount')::double precision, 0.0)
                    + COALESCE((m.extra_market_jsonb->>'buy_lg_amount')::double precision, 0.0)
                    - COALESCE((m.extra_market_jsonb->>'sell_elg_amount')::double precision, 0.0)
                    - COALESCE((m.extra_market_jsonb->>'sell_lg_amount')::double precision, 0.0)
                ) / m.amount::double precision * 100.0
            END AS large_net_amount_to_amount_pct,
            CASE
                WHEN m.trade_date = $2
                  AND m.amount IS NOT NULL AND m.amount != 0
                THEN (
                    COALESCE((m.extra_market_jsonb->>'buy_sm_amount')::double precision, 0.0)
                    - COALESCE((m.extra_market_jsonb->>'sell_sm_amount')::double precision, 0.0)
                ) / m.amount::double precision * 100.0
            END AS small_net_amount_to_amount_pct,
            CASE
                WHEN m.trade_date = $2
                THEN c.winner_rate::double precision
            END AS cyq_winner_rate,
            CASE
                WHEN m.trade_date = $2
                  AND m.close IS NOT NULL AND m.close != 0
                THEN (c.cost_50pct::double precision - m.close::double precision)
                     / m.close::double precision * 100.0
            END AS cyq_cost_50_to_close_pct,
            CASE
                WHEN m.trade_date = $2
                  AND m.close IS NOT NULL AND m.close != 0
                THEN (c.cost_85pct::double precision - m.close::double precision)
                     / m.close::double precision * 100.0
            END AS cyq_cost_85_to_close_pct,
            CASE
                WHEN m.trade_date = $2
                  AND m.close IS NOT NULL AND m.close != 0
                THEN (c.weight_avg::double precision - m.close::double precision)
                     / m.close::double precision * 100.0
            END AS cyq_weight_avg_to_close_pct,
            CASE
                WHEN m.trade_date = $2
                  AND m.close IS NOT NULL AND m.close != 0
                THEN (c.cost_85pct::double precision - c.cost_15pct::double precision)
                     / m.close::double precision * 100.0
            END AS cyq_cost_70_width_pct,
            CASE
                WHEN m.trade_date = $2
                  AND m.close IS NOT NULL AND m.close != 0
                THEN (c.cost_95pct::double precision - c.cost_5pct::double precision)
                     / m.close::double precision * 100.0
            END AS cyq_cost_90_width_pct,
            CASE WHEN m.trade_date = $2 THEN sse.ret5_pct END AS market_sse_ret5_pct,
            CASE WHEN m.trade_date = $2 THEN sse.ret20_pct END AS market_sse_ret20_pct,
            CASE WHEN m.trade_date = $2 THEN sse.ma20_bias_pct END AS market_sse_ma20_bias_pct,
            CASE WHEN m.trade_date = $2 THEN sse.volatility20_pct END AS market_sse_volatility20_pct,
            CASE WHEN m.trade_date = $2 THEN cn2000.ret5_pct END AS market_cn2000_ret5_pct,
            CASE WHEN m.trade_date = $2 THEN cn2000.ret20_pct END AS market_cn2000_ret20_pct,
            CASE WHEN m.trade_date = $2 THEN cn2000.ma20_bias_pct END AS market_cn2000_ma20_bias_pct,
            CASE WHEN m.trade_date = $2 THEN cn2000.volatility20_pct END AS market_cn2000_volatility20_pct,
            CASE WHEN m.trade_date = $2 THEN broad.market_broad_ret5_pct END AS market_broad_ret5_pct,
            CASE WHEN m.trade_date = $2 THEN broad.market_broad_ret20_pct END AS market_broad_ret20_pct,
            CASE WHEN m.trade_date = $2 THEN broad.market_broad_ma20_bias_pct END AS market_broad_ma20_bias_pct,
            CASE WHEN m.trade_date = $2 THEN broad.market_broad_volatility20_pct END AS market_broad_volatility20_pct,
            CASE WHEN m.trade_date = $2 THEN sw.ret5_pct END AS sw_l2_ret5_pct,
            CASE WHEN m.trade_date = $2 THEN sw.ret20_pct END AS sw_l2_ret20_pct,
            CASE WHEN m.trade_date = $2 THEN sw.ma20_bias_pct END AS sw_l2_ma20_bias_pct,
            CASE WHEN m.trade_date = $2 THEN sw.volatility20_pct END AS sw_l2_volatility20_pct,
            CASE WHEN m.trade_date = $2 THEN sw.sw_l2_ret5_rank_pct END AS sw_l2_ret5_rank_pct,
            CASE WHEN m.trade_date = $2 THEN sw.sw_l2_ret20_rank_pct END AS sw_l2_ret20_rank_pct,
            CASE
                WHEN m.trade_date = $2
                 AND sw.ret5_pct IS NOT NULL
                 AND broad.market_broad_ret5_pct IS NOT NULL
                THEN sw.ret5_pct - broad.market_broad_ret5_pct
            END AS sw_l2_vs_market_ret5_pct,
            CASE
                WHEN m.trade_date = $2
                 AND sw.ret20_pct IS NOT NULL
                 AND broad.market_broad_ret20_pct IS NOT NULL
                THEN sw.ret20_pct - broad.market_broad_ret20_pct
            END AS sw_l2_vs_market_ret20_pct,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_up_ratio END AS sw_l2_up_ratio,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_ge5_ratio END AS sw_l2_ge5_ratio,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_limit_up_ratio END AS sw_l2_limit_up_ratio,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_limit_down_ratio END AS sw_l2_limit_down_ratio,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_amount_share_pct END AS sw_l2_amount_share_pct,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_amount_share_rank_pct END AS sw_l2_amount_share_rank_pct,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_amount_share_ma5_ratio END AS sw_l2_amount_share_ma5_ratio,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_top1_amount_share_pct END AS sw_l2_top1_amount_share_pct,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_top3_amount_share_pct END AS sw_l2_top3_amount_share_pct,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_top5_amount_share_pct END AS sw_l2_top5_amount_share_pct,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_net_mf_to_amount_pct END AS sw_l2_net_mf_to_amount_pct,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_net_mf_market_share_pct END AS sw_l2_net_mf_market_share_pct,
            CASE WHEN m.trade_date = $2 THEN industry.sw_l2_net_mf_rank_pct END AS sw_l2_net_mf_rank_pct,
            CASE
                WHEN m.trade_date = $2
                 AND m.amount IS NOT NULL
                 AND industry.industry_amount IS NOT NULL
                 AND industry.industry_amount != 0
                THEN m.amount::double precision / industry.industry_amount * 100.0
            END AS stock_amount_to_sw_l2_amount_pct,
            CASE
                WHEN m.trade_date = $2
                 AND m.net_mf_amount IS NOT NULL
                 AND m.amount IS NOT NULL
                 AND m.amount > 0
                 AND industry.industry_net_mf_amount_base IS NOT NULL
                 AND industry.industry_net_mf_amount_base != 0
                THEN m.net_mf_amount::double precision / industry.industry_net_mf_amount_base * 100.0
            END AS stock_net_mf_to_sw_l2_amount_pct
        FROM daily_market m
        LEFT JOIN daily_indicators i
          ON i.ts_code = m.ts_code
         AND i.trade_date = $2
         AND m.trade_date = $2
        LEFT JOIN daily_cyq_perf c
          ON c.ts_code = m.ts_code
         AND c.trade_date = $2
         AND m.trade_date = $2
        LEFT JOIN sw_member sim
          ON sim.ts_code = m.ts_code
         AND m.trade_date = $2
        LEFT JOIN index_features sse
          ON sse.group_name = 'major'
         AND sse.ts_code = '000001.SH'
         AND sse.trade_date = m.trade_date
         AND m.trade_date = $2
        LEFT JOIN index_features cn2000
          ON cn2000.group_name = 'major'
         AND cn2000.ts_code = '399303.SZ'
         AND cn2000.trade_date = m.trade_date
         AND m.trade_date = $2
        LEFT JOIN market_broad_features broad
          ON broad.trade_date = m.trade_date
         AND m.trade_date = $2
        LEFT JOIN sw_l2_features sw
          ON sw.ts_code = sim.l2_code
         AND sw.trade_date = m.trade_date
         AND m.trade_date = $2
        LEFT JOIN industry_features industry
          ON industry.l2_code = sim.l2_code
         AND industry.trade_date = m.trade_date
         AND m.trade_date = $2
        WHERE m.trade_date BETWEEN $1 AND $2
        ";

pub fn fetch_daily_window(
    dsn: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Vec<MarketRow>> {
    let mut client = Client::connect(dsn, NoTls)?;
    configure_daily_window_session(&mut client)?;
    let mut rows = client.query_raw(DAILY_WINDOW_QUERY, &[&start_date, &end_date])?;
    let mut market_rows = Vec::new();
    while let Some(row) = rows.next()? {
        market_rows.push(market_row_from_db_row(row)?);
    }
    Ok(market_rows)
}

fn market_row_from_db_row(row: postgres::Row) -> anyhow::Result<MarketRow> {
    Ok(MarketRow {
        ts_code: row.try_get("ts_code")?,
        trade_date: row.try_get("trade_date")?,
        open: optional_f64(&row, "open")?,
        high: optional_f64(&row, "high")?,
        low: optional_f64(&row, "low")?,
        close: optional_f64(&row, "close")?,
        vol: optional_f64(&row, "vol")?,
        turnover_rate: optional_option_f64(&row, "turnover_rate")?,
        adj_factor: optional_option_f64(&row, "adj_factor")?,
        db_factors: db_factor_values([
            ("chip_vwap", optional_option_f64(&row, "chip_vwap")?),
            ("chip_turnover", optional_option_f64(&row, "chip_turnover")?),
            (
                "turnover_rate_f",
                optional_option_f64(&row, "turnover_rate_f")?,
            ),
            (
                "boll_width_pct",
                optional_option_f64(&row, "boll_width_pct")?,
            ),
            ("dmi_adxr_qfq", optional_option_f64(&row, "dmi_adxr_qfq")?),
            ("dmi_adx_qfq", optional_option_f64(&row, "dmi_adx_qfq")?),
            ("dmi_pdi_qfq", optional_option_f64(&row, "dmi_pdi_qfq")?),
            ("dmi_mdi_qfq", optional_option_f64(&row, "dmi_mdi_qfq")?),
            (
                "dmi_pdi_mdi_spread_qfq",
                optional_option_f64(&row, "dmi_pdi_mdi_spread_qfq")?,
            ),
            (
                "dmi_adx_adxr_gap_qfq",
                optional_option_f64(&row, "dmi_adx_adxr_gap_qfq")?,
            ),
            ("wr_qfq", optional_option_f64(&row, "wr_qfq")?),
            ("mtm_qfq", optional_option_f64(&row, "mtm_qfq")?),
            ("roc_qfq", optional_option_f64(&row, "roc_qfq")?),
            ("trix_qfq", optional_option_f64(&row, "trix_qfq")?),
            ("obv_qfq", optional_option_f64(&row, "obv_qfq")?),
            ("vr_qfq", optional_option_f64(&row, "vr_qfq")?),
            ("psy_qfq", optional_option_f64(&row, "psy_qfq")?),
            ("bias1_qfq", optional_option_f64(&row, "bias1_qfq")?),
            (
                "dist_to_up_limit_pct",
                optional_option_f64(&row, "dist_to_up_limit_pct")?,
            ),
            (
                "dist_to_down_limit_pct",
                optional_option_f64(&row, "dist_to_down_limit_pct")?,
            ),
            (
                "net_mf_amount_to_amount_pct",
                optional_option_f64(&row, "net_mf_amount_to_amount_pct")?,
            ),
            (
                "large_net_amount_to_amount_pct",
                optional_option_f64(&row, "large_net_amount_to_amount_pct")?,
            ),
            (
                "small_net_amount_to_amount_pct",
                optional_option_f64(&row, "small_net_amount_to_amount_pct")?,
            ),
            (
                "cyq_winner_rate",
                optional_option_f64(&row, "cyq_winner_rate")?,
            ),
            (
                "cyq_cost_50_to_close_pct",
                optional_option_f64(&row, "cyq_cost_50_to_close_pct")?,
            ),
            (
                "cyq_cost_85_to_close_pct",
                optional_option_f64(&row, "cyq_cost_85_to_close_pct")?,
            ),
            (
                "cyq_weight_avg_to_close_pct",
                optional_option_f64(&row, "cyq_weight_avg_to_close_pct")?,
            ),
            (
                "cyq_cost_70_width_pct",
                optional_option_f64(&row, "cyq_cost_70_width_pct")?,
            ),
            (
                "cyq_cost_90_width_pct",
                optional_option_f64(&row, "cyq_cost_90_width_pct")?,
            ),
            (
                "market_sse_ret5_pct",
                optional_option_f64(&row, "market_sse_ret5_pct")?,
            ),
            (
                "market_sse_ret20_pct",
                optional_option_f64(&row, "market_sse_ret20_pct")?,
            ),
            (
                "market_sse_ma20_bias_pct",
                optional_option_f64(&row, "market_sse_ma20_bias_pct")?,
            ),
            (
                "market_sse_volatility20_pct",
                optional_option_f64(&row, "market_sse_volatility20_pct")?,
            ),
            (
                "market_cn2000_ret5_pct",
                optional_option_f64(&row, "market_cn2000_ret5_pct")?,
            ),
            (
                "market_cn2000_ret20_pct",
                optional_option_f64(&row, "market_cn2000_ret20_pct")?,
            ),
            (
                "market_cn2000_ma20_bias_pct",
                optional_option_f64(&row, "market_cn2000_ma20_bias_pct")?,
            ),
            (
                "market_cn2000_volatility20_pct",
                optional_option_f64(&row, "market_cn2000_volatility20_pct")?,
            ),
            (
                "market_broad_ret5_pct",
                optional_option_f64(&row, "market_broad_ret5_pct")?,
            ),
            (
                "market_broad_ret20_pct",
                optional_option_f64(&row, "market_broad_ret20_pct")?,
            ),
            (
                "market_broad_ma20_bias_pct",
                optional_option_f64(&row, "market_broad_ma20_bias_pct")?,
            ),
            (
                "market_broad_volatility20_pct",
                optional_option_f64(&row, "market_broad_volatility20_pct")?,
            ),
            (
                "sw_l2_ret5_pct",
                optional_option_f64(&row, "sw_l2_ret5_pct")?,
            ),
            (
                "sw_l2_ret20_pct",
                optional_option_f64(&row, "sw_l2_ret20_pct")?,
            ),
            (
                "sw_l2_ma20_bias_pct",
                optional_option_f64(&row, "sw_l2_ma20_bias_pct")?,
            ),
            (
                "sw_l2_volatility20_pct",
                optional_option_f64(&row, "sw_l2_volatility20_pct")?,
            ),
            (
                "sw_l2_ret5_rank_pct",
                optional_option_f64(&row, "sw_l2_ret5_rank_pct")?,
            ),
            (
                "sw_l2_ret20_rank_pct",
                optional_option_f64(&row, "sw_l2_ret20_rank_pct")?,
            ),
            (
                "sw_l2_vs_market_ret5_pct",
                optional_option_f64(&row, "sw_l2_vs_market_ret5_pct")?,
            ),
            (
                "sw_l2_vs_market_ret20_pct",
                optional_option_f64(&row, "sw_l2_vs_market_ret20_pct")?,
            ),
            (
                "sw_l2_up_ratio",
                optional_option_f64(&row, "sw_l2_up_ratio")?,
            ),
            (
                "sw_l2_ge5_ratio",
                optional_option_f64(&row, "sw_l2_ge5_ratio")?,
            ),
            (
                "sw_l2_limit_up_ratio",
                optional_option_f64(&row, "sw_l2_limit_up_ratio")?,
            ),
            (
                "sw_l2_limit_down_ratio",
                optional_option_f64(&row, "sw_l2_limit_down_ratio")?,
            ),
            (
                "sw_l2_amount_share_pct",
                optional_option_f64(&row, "sw_l2_amount_share_pct")?,
            ),
            (
                "sw_l2_amount_share_rank_pct",
                optional_option_f64(&row, "sw_l2_amount_share_rank_pct")?,
            ),
            (
                "sw_l2_amount_share_ma5_ratio",
                optional_option_f64(&row, "sw_l2_amount_share_ma5_ratio")?,
            ),
            (
                "sw_l2_top1_amount_share_pct",
                optional_option_f64(&row, "sw_l2_top1_amount_share_pct")?,
            ),
            (
                "sw_l2_top3_amount_share_pct",
                optional_option_f64(&row, "sw_l2_top3_amount_share_pct")?,
            ),
            (
                "sw_l2_top5_amount_share_pct",
                optional_option_f64(&row, "sw_l2_top5_amount_share_pct")?,
            ),
            (
                "sw_l2_net_mf_to_amount_pct",
                optional_option_f64(&row, "sw_l2_net_mf_to_amount_pct")?,
            ),
            (
                "sw_l2_net_mf_market_share_pct",
                optional_option_f64(&row, "sw_l2_net_mf_market_share_pct")?,
            ),
            (
                "sw_l2_net_mf_rank_pct",
                optional_option_f64(&row, "sw_l2_net_mf_rank_pct")?,
            ),
            (
                "stock_amount_to_sw_l2_amount_pct",
                optional_option_f64(&row, "stock_amount_to_sw_l2_amount_pct")?,
            ),
            (
                "stock_net_mf_to_sw_l2_amount_pct",
                optional_option_f64(&row, "stock_net_mf_to_sw_l2_amount_pct")?,
            ),
        ]),
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
    let row = client.query_one(
        "
        SELECT max(trade_date) AS trade_date
        FROM daily_market
        WHERE trade_date < $1
        ",
        &[&trade_date],
    )?;
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
    let rows = client.query(
        "
        SELECT ts_code, name, industry
        FROM instruments
        WHERE ts_code = ANY($1)
        ORDER BY ts_code ASC
        ",
        &[&symbols],
    )?;
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

fn db_factor_values<const N: usize>(values: [(&str, Option<f64>); N]) -> BTreeMap<String, f64> {
    values
        .into_iter()
        .filter_map(|(key, value)| {
            value
                .filter(|value| value.is_finite())
                .map(|value| (key.to_string(), value))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn daily_window_query_joins_indicator_extras_on_latest_date() {
        assert!(DAILY_WINDOW_QUERY.contains("LEFT JOIN daily_indicators i"));
        assert!(DAILY_WINDOW_QUERY.contains("i.trade_date = $2"));
        assert!(DAILY_WINDOW_QUERY.contains("m.trade_date = $2"));
        assert!(DAILY_WINDOW_QUERY.contains("WHERE m.trade_date BETWEEN $1 AND $2"));
    }

    #[test]
    fn daily_window_query_reads_indicator_extras_only_for_latest_date() {
        assert!(DAILY_WINDOW_QUERY.contains("i.trade_date = $2"));
        assert!(DAILY_WINDOW_QUERY.contains("m.trade_date = $2"));
        assert!(
            !DAILY_WINDOW_QUERY
                .contains("FROM daily_indicators\n            WHERE trade_date BETWEEN")
        );
    }

    #[test]
    fn daily_window_query_reads_next_indicator_factor_batch() {
        for key in [
            "dmi_adx_qfq",
            "dmi_pdi_qfq",
            "dmi_mdi_qfq",
            "dmi_pdi_mdi_spread_qfq",
            "dmi_adx_adxr_gap_qfq",
            "mtm_qfq",
            "roc_qfq",
            "trix_qfq",
            "obv_qfq",
            "vr_qfq",
            "psy_qfq",
            "bias1_qfq",
        ] {
            assert!(DAILY_WINDOW_QUERY.contains(key), "missing {key}");
        }
    }

    #[test]
    fn daily_window_query_reads_market_adj_factor_from_extra_market_jsonb() {
        assert!(DAILY_WINDOW_QUERY.contains("m.extra_market_jsonb ? 'adj_factor'"));
        assert!(DAILY_WINDOW_QUERY.contains("AS adj_factor"));
    }

    #[test]
    fn daily_window_query_reads_cyq_perf_factor_batch() {
        assert!(DAILY_WINDOW_QUERY.contains("LEFT JOIN daily_cyq_perf c"));
        assert!(DAILY_WINDOW_QUERY.contains("c.trade_date = $2"));
        for key in [
            "cyq_winner_rate",
            "cyq_cost_50_to_close_pct",
            "cyq_cost_85_to_close_pct",
            "cyq_weight_avg_to_close_pct",
            "cyq_cost_70_width_pct",
            "cyq_cost_90_width_pct",
        ] {
            assert!(DAILY_WINDOW_QUERY.contains(key), "missing {key}");
        }
    }

    #[test]
    fn daily_window_query_reads_market_and_sw_l2_relative_strength_factors() {
        assert!(DAILY_WINDOW_QUERY.contains("sw_industry_member"));
        assert!(DAILY_WINDOW_QUERY.contains("group_name = 'sw_secondary'"));
        assert!(DAILY_WINDOW_QUERY.contains("group_name = 'major'"));
        assert!(DAILY_WINDOW_QUERY.contains("000001.SH"));
        assert!(DAILY_WINDOW_QUERY.contains("399303.SZ"));
        for key in [
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
            "sw_l2_ret5_pct",
            "sw_l2_ret20_pct",
            "sw_l2_ma20_bias_pct",
            "sw_l2_volatility20_pct",
            "sw_l2_ret5_rank_pct",
            "sw_l2_ret20_rank_pct",
            "sw_l2_vs_market_ret5_pct",
            "sw_l2_vs_market_ret20_pct",
        ] {
            assert!(DAILY_WINDOW_QUERY.contains(key), "missing {key}");
        }
    }

    #[test]
    fn daily_window_query_deduplicates_sw_member_mapping_before_joins() {
        assert!(DAILY_WINDOW_QUERY.contains("sw_member_raw AS ("));
        assert!(DAILY_WINDOW_QUERY.contains("sw_member AS ("));
        assert!(DAILY_WINDOW_QUERY.contains("FROM sw_industry_member"));
        assert!(DAILY_WINDOW_QUERY.contains("src = 'SW2021'"));
        assert!(DAILY_WINDOW_QUERY.contains("l2_code IS NOT NULL"));
        assert!(DAILY_WINDOW_QUERY.contains("GROUP BY ts_code"));
        assert!(DAILY_WINDOW_QUERY.contains("HAVING count(DISTINCT l2_code) = 1"));
        assert!(DAILY_WINDOW_QUERY.contains("INNER JOIN sw_member sim"));
        assert!(DAILY_WINDOW_QUERY.contains("LEFT JOIN sw_member sim"));
        assert!(!DAILY_WINDOW_QUERY.contains("JOIN sw_industry_member sim"));
    }

    #[test]
    fn daily_window_query_requires_both_broad_market_indexes_for_average_features() {
        for metric in ["ret5_pct", "ret20_pct", "ma20_bias_pct", "volatility20_pct"] {
            assert!(
                DAILY_WINDOW_QUERY.contains(&format!("WHEN count({metric}) = 2")),
                "missing full broad-index guard for {metric}"
            );
        }
    }

    #[test]
    fn daily_window_query_reads_sw_l2_crowding_and_capital_concentration_factors() {
        assert!(DAILY_WINDOW_QUERY.contains("industry_daily"));
        assert!(DAILY_WINDOW_QUERY.contains("industry_amount_ranks"));
        assert!(DAILY_WINDOW_QUERY.contains("industry_net_mf_ranks"));
        assert!(DAILY_WINDOW_QUERY.contains("up_limit"));
        assert!(DAILY_WINDOW_QUERY.contains("down_limit"));
        assert!(DAILY_WINDOW_QUERY.contains("net_mf_amount"));
        for key in [
            "sw_l2_up_ratio",
            "sw_l2_ge5_ratio",
            "sw_l2_limit_up_ratio",
            "sw_l2_limit_down_ratio",
            "sw_l2_amount_share_pct",
            "sw_l2_amount_share_rank_pct",
            "sw_l2_amount_share_ma5_ratio",
            "sw_l2_top1_amount_share_pct",
            "sw_l2_top3_amount_share_pct",
            "sw_l2_top5_amount_share_pct",
            "sw_l2_net_mf_to_amount_pct",
            "sw_l2_net_mf_market_share_pct",
            "sw_l2_net_mf_rank_pct",
            "stock_amount_to_sw_l2_amount_pct",
            "stock_net_mf_to_sw_l2_amount_pct",
        ] {
            assert!(DAILY_WINDOW_QUERY.contains(key), "missing {key}");
        }
    }

    #[test]
    fn daily_window_query_uses_directional_limit_denominators() {
        assert!(DAILY_WINDOW_QUERY.contains("limit_up_base_count"));
        assert!(DAILY_WINDOW_QUERY.contains("limit_down_base_count"));
        assert!(DAILY_WINDOW_QUERY.contains("CASE WHEN d.limit_up_base_count > 0"));
        assert!(DAILY_WINDOW_QUERY.contains("CASE WHEN d.limit_down_base_count > 0"));
        assert!(!DAILY_WINDOW_QUERY.contains("CASE WHEN d.limit_count > 0"));
    }

    #[test]
    fn daily_window_query_uses_valid_net_mf_amount_as_capital_flow_denominator() {
        let normalized = DAILY_WINDOW_QUERY
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ");
        assert!(DAILY_WINDOW_QUERY.contains("market_net_mf_amount_base"));
        assert!(DAILY_WINDOW_QUERY.contains("industry_net_mf_amount_base"));
        assert!(normalized.contains(
            "sum(net_mf_amount) FILTER ( WHERE net_mf_amount IS NOT NULL AND amount IS NOT NULL ) AS industry_net_mf_amount"
        ));
        assert!(normalized.contains(
            "sum(amount) FILTER ( WHERE net_mf_amount IS NOT NULL AND amount IS NOT NULL ) AS industry_net_mf_amount_base"
        ));
        assert!(normalized.contains("d.industry_net_mf_amount_base, CASE WHEN d.pct_count > 0"));
        assert!(normalized.contains(
            "sum(amount) FILTER ( WHERE net_mf_amount IS NOT NULL AND amount IS NOT NULL ) AS market_net_mf_amount_base"
        ));
        assert!(
            DAILY_WINDOW_QUERY
                .contains("THEN d.industry_net_mf_amount / d.industry_net_mf_amount_base * 100.0")
        );
        assert!(
            DAILY_WINDOW_QUERY
                .contains("THEN d.industry_net_mf_amount / a.market_net_mf_amount_base * 100.0")
        );
        assert!(
            normalized.contains(
                "AND m.net_mf_amount IS NOT NULL AND m.amount IS NOT NULL AND m.amount > 0"
            )
        );
    }

    #[test]
    fn daily_window_query_derives_chip_age_inputs_for_every_history_row() {
        assert!(DAILY_WINDOW_QUERY.contains("END AS chip_vwap"));
        assert!(
            DAILY_WINDOW_QUERY
                .contains("m.amount::double precision * 10.0 / m.vol::double precision")
        );
        assert!(DAILY_WINDOW_QUERY.contains("END AS chip_turnover"));
        assert!(DAILY_WINDOW_QUERY.contains("m.turnover_rate_f::double precision / 100.0"));
        assert!(DAILY_WINDOW_QUERY.contains("m.turnover_rate::double precision / 100.0"));

        let chip_vwap_clause = DAILY_WINDOW_QUERY
            .split("END AS chip_vwap")
            .next()
            .unwrap_or_default()
            .rsplit("CASE")
            .next()
            .unwrap_or_default();
        let chip_turnover_clause = DAILY_WINDOW_QUERY
            .split("END AS chip_turnover")
            .next()
            .unwrap_or_default()
            .rsplit("CASE")
            .next()
            .unwrap_or_default();

        assert!(!chip_vwap_clause.contains("m.trade_date = $2"));
        assert!(!chip_turnover_clause.contains("m.trade_date = $2"));
    }

    #[test]
    fn daily_window_query_avoids_database_global_ordering() {
        let final_where = DAILY_WINDOW_QUERY
            .rsplit("WHERE m.trade_date BETWEEN $1 AND $2")
            .next()
            .unwrap_or_default();
        assert!(!final_where.contains("ORDER BY"));
    }

    #[test]
    fn fetch_daily_window_streams_rows_through_helper() {
        let source = include_str!("db.rs")
            .split("#[cfg(test)]")
            .next()
            .unwrap_or_default();

        assert!(source.contains("fn market_row_from_db_row("));
        assert!(
            source.contains("client.query_raw(DAILY_WINDOW_QUERY, &[&start_date, &end_date])?")
        );
        assert!(source.contains("market_row_from_db_row(row)?"));
        assert!(!source.contains("client.query(DAILY_WINDOW_QUERY, &[&start_date, &end_date])?"));
    }

    #[test]
    fn db_factor_values_collects_selected_finite_aliases() {
        let factors = db_factor_values([
            ("boll_width_pct", Some(12.5)),
            ("wr_qfq", Some(-87.0)),
            ("chip_vwap", Some(10.25)),
            ("chip_turnover", Some(0.034)),
            ("market_broad_ret5_pct", Some(3.25)),
            ("sw_l2_vs_market_ret5_pct", Some(1.75)),
            ("stock_vs_sw_l2_ret5_pct", Some(-0.4)),
            ("turnover_rate_f", None),
            ("dist_to_up_limit_pct", Some(f64::NAN)),
        ]);

        assert_eq!(factors.len(), 7);
        assert_eq!(factors["boll_width_pct"], 12.5);
        assert_eq!(factors["wr_qfq"], -87.0);
        assert_eq!(factors["chip_vwap"], 10.25);
        assert_eq!(factors["chip_turnover"], 0.034);
        assert_eq!(factors["market_broad_ret5_pct"], 3.25);
        assert_eq!(factors["sw_l2_vs_market_ret5_pct"], 1.75);
        assert_eq!(factors["stock_vs_sw_l2_ret5_pct"], -0.4);
        assert!(!factors.contains_key("turnover_rate_f"));
        assert!(!factors.contains_key("dist_to_up_limit_pct"));
    }

    #[test]
    fn daily_window_session_settings_allow_parallel_query_and_larger_work_mem() {
        assert!(DAILY_WINDOW_SESSION_SETTINGS_SQL.contains("max_parallel_workers_per_gather = 2"));
        assert!(DAILY_WINDOW_SESSION_SETTINGS_SQL.contains("work_mem = '64MB'"));
    }
}
