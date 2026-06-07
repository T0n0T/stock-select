use chrono::NaiveDate;
use postgres::{Client, NoTls};
use std::collections::BTreeMap;

use crate::model::{InstrumentInfo, MarketRow};

const DAILY_WINDOW_SESSION_SETTINGS_SQL: &str = "
    SET max_parallel_workers_per_gather = 0;
    SET work_mem = '16MB';
";

const DAILY_WINDOW_QUERY: &str = "
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
            END AS cyq_cost_90_width_pct
        FROM daily_market m
        LEFT JOIN daily_indicators i
          ON i.ts_code = m.ts_code
         AND i.trade_date = $2
         AND m.trade_date = $2
        LEFT JOIN daily_cyq_perf c
          ON c.ts_code = m.ts_code
         AND c.trade_date = $2
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
    let rows = client.query(DAILY_WINDOW_QUERY, &[&start_date, &end_date])?;
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
                turnover_rate: optional_option_f64(&row, "turnover_rate")?,
                db_factors: db_factor_values([
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
                ]),
            })
        })
        .collect()
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
    fn daily_window_query_avoids_database_global_ordering() {
        assert!(!DAILY_WINDOW_QUERY.contains("ORDER BY"));
    }

    #[test]
    fn db_factor_values_collects_selected_finite_aliases() {
        let factors = db_factor_values([
            ("boll_width_pct", Some(12.5)),
            ("wr_qfq", Some(-87.0)),
            ("turnover_rate_f", None),
            ("dist_to_up_limit_pct", Some(f64::NAN)),
        ]);

        assert_eq!(factors.len(), 2);
        assert_eq!(factors["boll_width_pct"], 12.5);
        assert_eq!(factors["wr_qfq"], -87.0);
        assert!(!factors.contains_key("turnover_rate_f"));
        assert!(!factors.contains_key("dist_to_up_limit_pct"));
    }

    #[test]
    fn daily_window_session_settings_disable_parallel_query_memory_pressure() {
        assert!(DAILY_WINDOW_SESSION_SETTINGS_SQL.contains("max_parallel_workers_per_gather = 0"));
        assert!(DAILY_WINDOW_SESSION_SETTINGS_SQL.contains("work_mem = '16MB'"));
    }
}
