use std::collections::{BTreeMap, BTreeSet};

use chrono::NaiveDate;

use crate::cache::MIN_DB_NATIVE_WINDOW_TRADING_DAYS;
use crate::db::{DuckDbConnection, DuckDbParameter, DuckDbRow};
use crate::model::{DbDataGap, DbDataGapReason, db_data_gap_warning_message};

const RELATION_INSPECTION_QUERY: &str = "
    SELECT
        c.table_schema AS schema_name,
        c.table_name AS relation_name,
        t.table_type AS relation_kind,
        c.column_name
    FROM information_schema.columns c
    JOIN information_schema.tables t
      ON t.table_schema = c.table_schema
     AND t.table_name = c.table_name
    WHERE c.table_name = $1
    ORDER BY
        CASE WHEN c.table_schema = current_schema() THEN 0 ELSE 1 END,
        c.table_schema,
        c.ordinal_position
";

type DbColumnSpec = (&'static str, &'static str);

#[derive(Debug, Clone, Copy)]
struct DbTableSpec {
    name: &'static str,
    columns: &'static [DbColumnSpec],
}

#[cfg(test)]
fn table_spec(name: &str) -> Option<&'static DbTableSpec> {
    DB_TABLE_SPECS.iter().find(|spec| spec.name == name)
}

const STOCK_STK_FACTOR_PRO_COLUMNS: &[DbColumnSpec] = &[
    ("ts_code", "text"),
    ("trade_date", "date"),
    ("open", "double precision"),
    ("high", "double precision"),
    ("low", "double precision"),
    ("close", "double precision"),
    ("close_qfq", "double precision"),
    ("adj_factor", "double precision"),
    ("vol", "double precision"),
    ("amount", "double precision"),
    ("turnover_rate", "double precision"),
    ("turnover_rate_f", "double precision"),
    ("volume_ratio", "double precision"),
    ("kdj_k_qfq", "double precision"),
    ("kdj_d_qfq", "double precision"),
    ("rsi_qfq_6", "double precision"),
    ("rsi_qfq_12", "double precision"),
    ("rsi_qfq_24", "double precision"),
    ("boll_upper_qfq", "double precision"),
    ("boll_mid_qfq", "double precision"),
    ("boll_lower_qfq", "double precision"),
    ("dmi_adxr_qfq", "double precision"),
    ("dmi_adx_qfq", "double precision"),
    ("dmi_pdi_qfq", "double precision"),
    ("dmi_mdi_qfq", "double precision"),
    ("wr_qfq", "double precision"),
    ("mtm_qfq", "double precision"),
    ("roc_qfq", "double precision"),
    ("trix_qfq", "double precision"),
    ("obv_qfq", "double precision"),
    ("vr_qfq", "double precision"),
    ("psy_qfq", "double precision"),
    ("bias1_qfq", "double precision"),
    ("macd_dif_qfq", "double precision"),
    ("macd_dea_qfq", "double precision"),
    ("macd_qfq", "double precision"),
    ("pe", "double precision"),
    ("pe_ttm", "double precision"),
    ("pb", "double precision"),
    ("ps", "double precision"),
    ("ps_ttm", "double precision"),
    ("dv_ratio", "double precision"),
    ("total_mv", "double precision"),
    ("circ_mv", "double precision"),
    ("total_share", "double precision"),
    ("free_share", "double precision"),
    ("pct_chg", "double precision"),
    ("asi_qfq", "double precision"),
    ("asit_qfq", "double precision"),
    ("bias2_qfq", "double precision"),
    ("bias3_qfq", "double precision"),
    ("brar_ar_qfq", "double precision"),
    ("brar_br_qfq", "double precision"),
    ("cci_qfq", "double precision"),
    ("cr_qfq", "double precision"),
    ("emv_qfq", "double precision"),
    ("maemv_qfq", "double precision"),
    ("mass_qfq", "double precision"),
    ("ma_mass_qfq", "double precision"),
    ("mfi_qfq", "double precision"),
    ("psyma_qfq", "double precision"),
    ("maroc_qfq", "double precision"),
    ("trma_qfq", "double precision"),
    ("wr1_qfq", "double precision"),
    ("updays", "double precision"),
    ("downdays", "double precision"),
    ("lowdays", "double precision"),
    ("topdays", "double precision"),
    ("dv_ttm", "double precision"),
    ("float_share", "double precision"),
    ("bbi_qfq", "double precision"),
    ("ma_qfq_5", "double precision"),
    ("ma_qfq_10", "double precision"),
    ("ma_qfq_20", "double precision"),
    ("ma_qfq_30", "double precision"),
    ("ma_qfq_60", "double precision"),
    ("ma_qfq_90", "double precision"),
    ("ma_qfq_250", "double precision"),
    ("ema_qfq_5", "double precision"),
    ("ema_qfq_10", "double precision"),
    ("ema_qfq_20", "double precision"),
    ("ema_qfq_30", "double precision"),
    ("ema_qfq_60", "double precision"),
    ("ema_qfq_90", "double precision"),
    ("ema_qfq_250", "double precision"),
    ("expma_12_qfq", "double precision"),
    ("expma_50_qfq", "double precision"),
    ("ktn_upper_qfq", "double precision"),
    ("ktn_mid_qfq", "double precision"),
    ("ktn_down_qfq", "double precision"),
    ("taq_up_qfq", "double precision"),
    ("taq_mid_qfq", "double precision"),
    ("taq_down_qfq", "double precision"),
    ("xsii_td1_qfq", "double precision"),
    ("xsii_td2_qfq", "double precision"),
    ("xsii_td3_qfq", "double precision"),
    ("xsii_td4_qfq", "double precision"),
    ("atr_qfq", "double precision"),
    ("dfma_dif_qfq", "double precision"),
    ("dfma_difma_qfq", "double precision"),
    ("dpo_qfq", "double precision"),
    ("madpo_qfq", "double precision"),
    ("mtmma_qfq", "double precision"),
];

#[cfg(test)]
#[test]
fn stk_factor_pro_preflight_preserves_extended_snapshot_columns() {
    for column in crate::factors::stk_factor_pro::SOURCE_COLUMNS {
        assert!(
            STOCK_STK_FACTOR_PRO_COLUMNS
                .iter()
                .any(|(name, _)| name == column),
            "{column}"
        );
    }
}

const CALC_DAILY_INDICATORS_COLUMNS: &[DbColumnSpec] = &[
    ("source_dataset", "text"),
    ("ts_code", "text"),
    ("trade_date", "date"),
    ("calc_version", "text"),
    ("daily_macd_dif_asof", "double precision"),
    ("daily_macd_dea_asof", "double precision"),
    ("daily_macd_hist_x2_asof", "double precision"),
    ("daily_macd_dea_pctile_asof", "double precision"),
    ("daily_macd_period_count", "bigint"),
    ("weekly_macd_dif_asof", "double precision"),
    ("weekly_macd_dea_asof", "double precision"),
    ("weekly_macd_hist_x2_asof", "double precision"),
    ("weekly_macd_dea_pctile_asof", "double precision"),
    ("weekly_macd_period_count", "bigint"),
    ("monthly_macd_dif_asof", "double precision"),
    ("monthly_macd_dea_asof", "double precision"),
    ("monthly_macd_hist_x2_asof", "double precision"),
    ("monthly_macd_dea_pctile_asof", "double precision"),
    ("monthly_macd_period_count", "bigint"),
    ("weekly_kdj_k_asof", "double precision"),
    ("weekly_kdj_d_asof", "double precision"),
    ("weekly_kdj_j_asof", "double precision"),
    ("monthly_kdj_k_asof", "double precision"),
    ("monthly_kdj_d_asof", "double precision"),
    ("monthly_kdj_j_asof", "double precision"),
];

const CALC_DAILY_ROLLING_FACTORS_COLUMNS: &[DbColumnSpec] = &[
    ("source_dataset", "text"),
    ("ts_code", "text"),
    ("trade_date", "date"),
    ("calc_version", "text"),
    ("ma25_qfq", "double precision"),
    ("ma144_qfq", "double precision"),
    ("ma220_qfq", "double precision"),
    ("high_20_qfq", "double precision"),
    ("close_to_20d_max_close_pct", "double precision"),
    ("high_90_qfq", "double precision"),
    ("low_90_qfq", "double precision"),
    ("high_120_qfq", "double precision"),
    ("low_120_qfq", "double precision"),
    ("position_90d", "double precision"),
    ("position_120d", "double precision"),
    ("volume_ma5", "double precision"),
    ("volume_ma20", "double precision"),
    ("volume_to_ma5_ratio", "double precision"),
    ("volume_to_ma20_ratio", "double precision"),
    ("volume_ma5_to_ma20_ratio", "double precision"),
    ("turnover_rate_ma5", "double precision"),
    ("turnover_to_ma5_ratio", "double precision"),
    ("range_compression_20d", "double precision"),
    ("range_compression_40d", "double precision"),
];

const CALC_DAILY_CZSC_STRUCTURE_COLUMNS: &[DbColumnSpec] = &[
    ("source_dataset", "text"),
    ("ts_code", "text"),
    ("trade_date", "date"),
    ("calc_version", "text"),
    ("daily_period_complete", "boolean"),
    ("weekly_period_complete", "boolean"),
    ("monthly_period_complete", "boolean"),
    ("daily_source_bar_valid", "boolean"),
    ("daily_status", "text"),
    ("daily_available_finished_bi_count", "integer"),
    ("daily_recent_bi_count", "integer"),
    ("daily_last_bi_direction", "text"),
    ("daily_last_bi_start_date", "date"),
    ("daily_last_bi_end_date", "date"),
    ("daily_last_bi_high", "double precision"),
    ("daily_last_bi_low", "double precision"),
    ("daily_last_bi_mid", "double precision"),
    ("daily_latest_zs_start_date", "date"),
    ("daily_latest_zs_end_date", "date"),
    ("daily_latest_zs_bi_count", "integer"),
    ("daily_latest_zs_zg", "double precision"),
    ("daily_latest_zs_zd", "double precision"),
    ("daily_latest_zs_zz", "double precision"),
    ("daily_recent_peak_date", "date"),
    ("daily_recent_peak_high", "double precision"),
    ("daily_post_peak_first_bear_date", "date"),
    ("daily_post_peak_first_bear_open", "double precision"),
    ("daily_post_peak_first_bear_high", "double precision"),
    ("daily_post_peak_first_bear_low", "double precision"),
    ("daily_post_peak_first_bear_close", "double precision"),
    ("daily_post_peak_first_bear_missing", "boolean"),
    ("weekly_source_bar_valid", "boolean"),
    ("weekly_status", "text"),
    ("weekly_available_finished_bi_count", "integer"),
    ("weekly_recent_bi_count", "integer"),
    ("weekly_last_bi_direction", "text"),
    ("weekly_last_bi_start_date", "date"),
    ("weekly_last_bi_end_date", "date"),
    ("weekly_last_bi_high", "double precision"),
    ("weekly_last_bi_low", "double precision"),
    ("weekly_last_bi_mid", "double precision"),
    ("weekly_latest_zs_start_date", "date"),
    ("weekly_latest_zs_end_date", "date"),
    ("weekly_latest_zs_bi_count", "integer"),
    ("weekly_latest_zs_zg", "double precision"),
    ("weekly_latest_zs_zd", "double precision"),
    ("weekly_latest_zs_zz", "double precision"),
    ("weekly_recent_peak_date", "date"),
    ("weekly_recent_peak_high", "double precision"),
    ("weekly_post_peak_first_bear_date", "date"),
    ("weekly_post_peak_first_bear_open", "double precision"),
    ("weekly_post_peak_first_bear_high", "double precision"),
    ("weekly_post_peak_first_bear_low", "double precision"),
    ("weekly_post_peak_first_bear_close", "double precision"),
    ("weekly_post_peak_first_bear_missing", "boolean"),
    ("monthly_source_bar_valid", "boolean"),
    ("monthly_status", "text"),
    ("monthly_available_finished_bi_count", "integer"),
    ("monthly_recent_bi_count", "integer"),
    ("monthly_last_bi_direction", "text"),
    ("monthly_last_bi_start_date", "date"),
    ("monthly_last_bi_end_date", "date"),
    ("monthly_last_bi_high", "double precision"),
    ("monthly_last_bi_low", "double precision"),
    ("monthly_last_bi_mid", "double precision"),
    ("monthly_latest_zs_start_date", "date"),
    ("monthly_latest_zs_end_date", "date"),
    ("monthly_latest_zs_bi_count", "integer"),
    ("monthly_latest_zs_zg", "double precision"),
    ("monthly_latest_zs_zd", "double precision"),
    ("monthly_latest_zs_zz", "double precision"),
    ("monthly_recent_peak_date", "date"),
    ("monthly_recent_peak_high", "double precision"),
    ("monthly_post_peak_first_bear_date", "date"),
    ("monthly_post_peak_first_bear_open", "double precision"),
    ("monthly_post_peak_first_bear_high", "double precision"),
    ("monthly_post_peak_first_bear_low", "double precision"),
    ("monthly_post_peak_first_bear_close", "double precision"),
    ("monthly_post_peak_first_bear_missing", "boolean"),
];

const CALC_INDICATOR_STATE_COLUMNS: &[DbColumnSpec] = &[
    ("source_dataset", "text"),
    ("ts_code", "text"),
    ("period_type", "text"),
    ("period_start_date", "date"),
    ("period_end_date", "date"),
    ("calc_version", "text"),
    ("macd_ema12", "double precision"),
    ("macd_ema26", "double precision"),
    ("macd_dea", "double precision"),
    ("macd_period_count", "bigint"),
    ("kdj_k", "double precision"),
    ("kdj_d", "double precision"),
    ("kdj_period_count", "bigint"),
];

const STOCK_MONEYFLOW_COLUMNS: &[DbColumnSpec] = &[
    ("ts_code", "text"),
    ("trade_date", "date"),
    ("buy_sm_vol", "double precision"),
    ("buy_sm_amount", "double precision"),
    ("sell_sm_vol", "double precision"),
    ("sell_sm_amount", "double precision"),
    ("buy_md_vol", "double precision"),
    ("buy_md_amount", "double precision"),
    ("sell_md_vol", "double precision"),
    ("sell_md_amount", "double precision"),
    ("buy_lg_vol", "double precision"),
    ("buy_lg_amount", "double precision"),
    ("sell_lg_vol", "double precision"),
    ("sell_lg_amount", "double precision"),
    ("buy_elg_vol", "double precision"),
    ("buy_elg_amount", "double precision"),
    ("sell_elg_vol", "double precision"),
    ("sell_elg_amount", "double precision"),
    ("net_mf_vol", "double precision"),
    ("net_mf_amount", "double precision"),
];

const INDEX_SW_MEMBER_COLUMNS: &[DbColumnSpec] = &[
    ("l1_code", "text"),
    ("l1_name", "text"),
    ("l2_code", "text"),
    ("l2_name", "text"),
    ("l3_code", "text"),
    ("l3_name", "text"),
    ("ts_code", "text"),
    ("name", "text"),
    ("in_date", "date"),
    ("out_date", "date"),
    ("is_new", "boolean"),
];

const INDEX_WEIGHT_COLUMNS: &[DbColumnSpec] = &[
    ("index_code", "text"),
    ("con_code", "text"),
    ("trade_date", "date"),
    ("weight", "double precision"),
];

const CALC_DAILY_INDUSTRY_MONEYFLOW_COLUMNS: &[DbColumnSpec] = &[
    ("source_dataset", "text"),
    ("industry_code", "text"),
    ("industry_name", "text"),
    ("trade_date", "date"),
    ("stock_count", "bigint"),
    ("buy_sm_amount", "double precision"),
    ("sell_sm_amount", "double precision"),
    ("net_sm_amount", "double precision"),
    ("buy_md_amount", "double precision"),
    ("sell_md_amount", "double precision"),
    ("net_md_amount", "double precision"),
    ("buy_lg_amount", "double precision"),
    ("sell_lg_amount", "double precision"),
    ("net_lg_amount", "double precision"),
    ("buy_elg_amount", "double precision"),
    ("sell_elg_amount", "double precision"),
    ("net_elg_amount", "double precision"),
    ("main_net_amount", "double precision"),
    ("net_mf_vol", "double precision"),
    ("net_mf_amount", "double precision"),
    ("calc_version", "text"),
];

const INDEX_IDX_FACTOR_PRO_COLUMNS: &[DbColumnSpec] = &[
    ("ts_code", "text"),
    ("trade_date", "date"),
    ("open", "double precision"),
    ("high", "double precision"),
    ("low", "double precision"),
    ("close", "double precision"),
    ("pre_close", "double precision"),
    ("change", "double precision"),
    ("pct_change", "double precision"),
    ("vol", "double precision"),
    ("amount", "double precision"),
    ("asi_bfq", "double precision"),
    ("asit_bfq", "double precision"),
    ("atr_bfq", "double precision"),
    ("bbi_bfq", "double precision"),
    ("bias1_bfq", "double precision"),
    ("bias2_bfq", "double precision"),
    ("bias3_bfq", "double precision"),
    ("boll_lower_bfq", "double precision"),
    ("boll_mid_bfq", "double precision"),
    ("boll_upper_bfq", "double precision"),
    ("brar_ar_bfq", "double precision"),
    ("brar_br_bfq", "double precision"),
    ("cci_bfq", "double precision"),
    ("cr_bfq", "double precision"),
    ("dfma_dif_bfq", "double precision"),
    ("dfma_difma_bfq", "double precision"),
    ("dmi_adx_bfq", "double precision"),
    ("dmi_adxr_bfq", "double precision"),
    ("dmi_mdi_bfq", "double precision"),
    ("dmi_pdi_bfq", "double precision"),
    ("downdays", "double precision"),
    ("updays", "double precision"),
    ("dpo_bfq", "double precision"),
    ("madpo_bfq", "double precision"),
    ("ema_bfq_10", "double precision"),
    ("ema_bfq_20", "double precision"),
    ("ema_bfq_250", "double precision"),
    ("ema_bfq_30", "double precision"),
    ("ema_bfq_5", "double precision"),
    ("ema_bfq_60", "double precision"),
    ("ema_bfq_90", "double precision"),
    ("emv_bfq", "double precision"),
    ("maemv_bfq", "double precision"),
    ("expma_12_bfq", "double precision"),
    ("expma_50_bfq", "double precision"),
    ("kdj_bfq", "double precision"),
    ("kdj_d_bfq", "double precision"),
    ("kdj_k_bfq", "double precision"),
    ("ktn_down_bfq", "double precision"),
    ("ktn_mid_bfq", "double precision"),
    ("ktn_upper_bfq", "double precision"),
    ("lowdays", "double precision"),
    ("topdays", "double precision"),
    ("ma_bfq_10", "double precision"),
    ("ma_bfq_20", "double precision"),
    ("ma_bfq_250", "double precision"),
    ("ma_bfq_30", "double precision"),
    ("ma_bfq_5", "double precision"),
    ("ma_bfq_60", "double precision"),
    ("ma_bfq_90", "double precision"),
    ("macd_bfq", "double precision"),
    ("macd_dea_bfq", "double precision"),
    ("macd_dif_bfq", "double precision"),
    ("mass_bfq", "double precision"),
    ("ma_mass_bfq", "double precision"),
    ("mfi_bfq", "double precision"),
    ("mtm_bfq", "double precision"),
    ("mtmma_bfq", "double precision"),
    ("obv_bfq", "double precision"),
    ("psy_bfq", "double precision"),
    ("psyma_bfq", "double precision"),
    ("roc_bfq", "double precision"),
    ("maroc_bfq", "double precision"),
    ("rsi_bfq_12", "double precision"),
    ("rsi_bfq_24", "double precision"),
    ("rsi_bfq_6", "double precision"),
    ("taq_down_bfq", "double precision"),
    ("taq_mid_bfq", "double precision"),
    ("taq_up_bfq", "double precision"),
    ("trix_bfq", "double precision"),
    ("trma_bfq", "double precision"),
    ("vr_bfq", "double precision"),
    ("wr_bfq", "double precision"),
    ("wr1_bfq", "double precision"),
    ("xsii_td1_bfq", "double precision"),
    ("xsii_td2_bfq", "double precision"),
    ("xsii_td3_bfq", "double precision"),
    ("xsii_td4_bfq", "double precision"),
];

const INDEX_LIMIT_CPT_LIST_COLUMNS: &[DbColumnSpec] = &[
    ("ts_code", "text"),
    ("trade_date", "date"),
    ("up_nums", "double precision"),
    ("days", "double precision"),
    ("pct_chg", "double precision"),
    ("rank", "double precision"),
];

const DB_TABLE_SPECS: &[DbTableSpec] = &[
    DbTableSpec {
        name: "stock_stk_factor_pro",
        columns: STOCK_STK_FACTOR_PRO_COLUMNS,
    },
    DbTableSpec {
        name: "calc_daily_indicators",
        columns: CALC_DAILY_INDICATORS_COLUMNS,
    },
    DbTableSpec {
        name: "calc_daily_rolling_factors",
        columns: CALC_DAILY_ROLLING_FACTORS_COLUMNS,
    },
    DbTableSpec {
        name: "calc_daily_czsc_structure",
        columns: CALC_DAILY_CZSC_STRUCTURE_COLUMNS,
    },
    DbTableSpec {
        name: "calc_indicator_state",
        columns: CALC_INDICATOR_STATE_COLUMNS,
    },
    DbTableSpec {
        name: "stock_moneyflow",
        columns: STOCK_MONEYFLOW_COLUMNS,
    },
    DbTableSpec {
        name: "index_idx_factor_pro",
        columns: INDEX_IDX_FACTOR_PRO_COLUMNS,
    },
    DbTableSpec {
        name: "index_weight",
        columns: INDEX_WEIGHT_COLUMNS,
    },
    DbTableSpec {
        name: "index_sw_member",
        columns: INDEX_SW_MEMBER_COLUMNS,
    },
    DbTableSpec {
        name: "calc_daily_industry_moneyflow",
        columns: CALC_DAILY_INDUSTRY_MONEYFLOW_COLUMNS,
    },
    DbTableSpec {
        name: "index_limit_cpt_list",
        columns: INDEX_LIMIT_CPT_LIST_COLUMNS,
    },
];

pub(crate) fn db_native_factor_source_columns(table: &str) -> Vec<&'static str> {
    DB_TABLE_SPECS
        .iter()
        .find(|spec| spec.name == table)
        .map(|spec| spec.columns.iter().map(|(column, _)| *column).collect())
        .unwrap_or_default()
}

pub(crate) fn db_native_numeric_factor_columns(table: &str) -> Vec<&'static str> {
    DB_TABLE_SPECS
        .iter()
        .find(|spec| spec.name == table)
        .map(|spec| {
            spec.columns
                .iter()
                .filter_map(|(name, sql_type)| {
                    let numeric = sql_type.contains("int")
                        || sql_type.contains("double")
                        || sql_type.contains("real")
                        || sql_type.contains("decimal")
                        || *sql_type == "boolean";
                    (numeric
                        && !matches!(
                            *name,
                            "ts_code" | "trade_date" | "source_dataset" | "calc_version"
                        ))
                    .then_some(*name)
                })
                .collect()
        })
        .unwrap_or_default()
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ResolvedRelation {
    schema: String,
    name: String,
}

impl ResolvedRelation {
    fn qualified_name(&self) -> String {
        format!(
            "{}.{}",
            quote_identifier(&self.schema),
            quote_identifier(&self.name)
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum DbTableSource {
    Relation(ResolvedRelation),
    Empty,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct DbRelationInspection {
    relation: Option<ResolvedRelation>,
    columns: BTreeSet<String>,
}

impl DbRelationInspection {
    pub(crate) fn missing() -> Self {
        Self {
            relation: None,
            columns: BTreeSet::new(),
        }
    }

    pub(crate) fn available_with_columns(
        schema: impl Into<String>,
        name: impl Into<String>,
        columns: impl IntoIterator<Item = impl Into<String>>,
    ) -> Self {
        Self {
            relation: Some(ResolvedRelation {
                schema: schema.into(),
                name: name.into(),
            }),
            columns: columns.into_iter().map(Into::into).collect(),
        }
    }

    #[cfg(test)]
    fn available_for_spec(table: &str) -> Self {
        let spec = table_spec(table).expect("registered table");
        Self::available_with_columns(
            "public",
            table,
            spec.columns.iter().map(|(column, _)| *column),
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct DbLoadPlan {
    sources: BTreeMap<&'static str, DbTableSource>,
    pub(crate) db_data_gaps: BTreeMap<String, DbDataGap>,
}

impl DbLoadPlan {
    pub(crate) fn adapt_query(&self, template: &str) -> String {
        let mut body = template.trim().to_string();
        let mut adapters = Vec::new();
        for spec in DB_TABLE_SPECS {
            let placeholder = relation_placeholder(spec.name);
            if !body.contains(&placeholder) {
                continue;
            }
            let alias = format!("db_src_{}", spec.name);
            let source = self
                .sources
                .get(spec.name)
                .cloned()
                .unwrap_or(DbTableSource::Empty);
            adapters.push(adapter_cte(spec, &alias, &source));
            body = body.replace(&placeholder, &alias);
        }
        if adapters.is_empty() {
            return body;
        }
        if let Some(rest) = body.strip_prefix("WITH ") {
            format!("WITH\n{},\n{}", adapters.join(",\n"), rest)
        } else {
            format!("WITH\n{}\n{}", adapters.join(",\n"), body)
        }
    }

    fn relation_sql(&self, table: &str) -> Option<String> {
        match self.sources.get(table) {
            Some(DbTableSource::Relation(relation)) => Some(relation.qualified_name()),
            _ => None,
        }
    }

    #[cfg(test)]
    fn for_test<'a>(sources: impl IntoIterator<Item = (&'a str, Option<&'a str>)>) -> Self {
        let mut resolved = DB_TABLE_SPECS
            .iter()
            .map(|spec| {
                (
                    spec.name,
                    DbTableSource::Relation(ResolvedRelation {
                        schema: "public".to_string(),
                        name: spec.name.to_string(),
                    }),
                )
            })
            .collect::<BTreeMap<_, _>>();
        for (table, relation) in sources {
            let Some(spec) = DB_TABLE_SPECS.iter().find(|spec| spec.name == table) else {
                continue;
            };
            let source = match relation {
                Some(relation) => {
                    let (schema, name) = relation.split_once('.').unwrap_or(("public", relation));
                    DbTableSource::Relation(ResolvedRelation {
                        schema: schema.to_string(),
                        name: name.to_string(),
                    })
                }
                None => DbTableSource::Empty,
            };
            resolved.insert(spec.name, source);
        }
        Self {
            sources: resolved,
            db_data_gaps: BTreeMap::new(),
        }
    }
}

pub(crate) fn preflight_db_native_load(
    client: &DuckDbConnection,
    start_date: NaiveDate,
    pick_date: NaiveDate,
    configured_strict_tables: &BTreeSet<String>,
) -> anyhow::Result<DbLoadPlan> {
    let mut strict_tables = configured_strict_tables.clone();
    strict_tables.insert("stock_stk_factor_pro".to_string());

    let mut inspections = BTreeMap::new();
    for spec in DB_TABLE_SPECS {
        inspections.insert(spec.name.to_string(), inspect_relation(client, spec)?);
    }
    let mut plan = plan_from_inspections(&inspections);
    probe_required_rows(client, &mut plan, start_date, pick_date, &strict_tables)?;
    let plan = finish_preflight(plan, &strict_tables, pick_date)?;
    for (table, gap) in &plan.db_data_gaps {
        eprintln!(
            "{}",
            db_data_gap_warning_message(pick_date, table, gap, None)
        );
    }
    Ok(plan)
}

fn inspect_relation(
    client: &DuckDbConnection,
    spec: &DbTableSpec,
) -> anyhow::Result<DbRelationInspection> {
    let rows = client.query_rows(
        RELATION_INSPECTION_QUERY,
        &[DuckDbParameter::Text(spec.name.to_string())],
    )?;
    let Some(first) = rows.first() else {
        return Ok(DbRelationInspection::missing());
    };
    let schema: String = first.try_get("schema_name")?;
    let name: String = first.try_get("relation_name")?;
    let relation_kind: String = first.try_get("relation_kind")?;
    if !matches!(relation_kind.as_str(), "BASE TABLE" | "VIEW") {
        return Ok(DbRelationInspection::missing());
    }
    let columns = rows
        .iter()
        .filter_map(|row| {
            let row_schema = row.try_get::<String>("schema_name").ok()?;
            let row_name = row.try_get::<String>("relation_name").ok()?;
            (row_schema == schema && row_name == name)
                .then(|| row.try_get::<String>("column_name").ok())
                .flatten()
        })
        .collect::<Vec<_>>();
    Ok(DbRelationInspection::available_with_columns(
        &schema, &name, columns,
    ))
}

fn index_factor_probe_spec() -> (&'static str, i64, &'static str) {
    ("count(DISTINCT ts_code)", 1, "AND ts_code = '000016.SH'")
}

fn probe_required_rows(
    client: &DuckDbConnection,
    plan: &mut DbLoadPlan,
    start_date: NaiveDate,
    pick_date: NaiveDate,
    strict_tables: &BTreeSet<String>,
) -> anyhow::Result<()> {
    if let Some(relation) = plan.relation_sql("stock_stk_factor_pro") {
        let row = query_one(
            client,
            &format!(
                "SELECT count(DISTINCT trade_date)::bigint AS window_trade_dates, count(*) FILTER (WHERE trade_date = $2)::bigint AS pick_date_rows FROM {relation} WHERE trade_date BETWEEN $1 AND $2"
            ),
            &[
                DuckDbParameter::Date(start_date),
                DuckDbParameter::Date(pick_date),
            ],
        )?;
        let window_trade_dates: i64 = row.try_get("window_trade_dates")?;
        let pick_date_rows: i64 = row.try_get("pick_date_rows")?;
        if pick_date_rows < 1 {
            record_missing_rows(plan, "stock_stk_factor_pro", 1, pick_date_rows);
        } else {
            record_missing_rows(
                plan,
                "stock_stk_factor_pro",
                i64::from(MIN_DB_NATIVE_WINDOW_TRADING_DAYS),
                window_trade_dates,
            );
        }
    }

    probe_pick_date_rows(
        client,
        plan,
        "stock_moneyflow",
        pick_date,
        "count(*)",
        1,
        None,
    )?;
    let (count_expression, expected_rows, predicate) = index_factor_probe_spec();
    probe_pick_date_rows(
        client,
        plan,
        "index_idx_factor_pro",
        pick_date,
        count_expression,
        expected_rows,
        Some(predicate),
    )?;
    probe_pick_date_rows(
        client,
        plan,
        "calc_daily_industry_moneyflow",
        pick_date,
        "count(*)",
        1,
        Some("AND source_dataset = 'stock_moneyflow' AND calc_version = 'sw2021-l2-v1'"),
    )?;
    probe_pick_date_rows(
        client,
        plan,
        "index_limit_cpt_list",
        pick_date,
        "count(*)",
        1,
        None,
    )?;
    if strict_tables.contains("index_sw_member")
        && let Some(relation) = plan.relation_sql("index_sw_member")
    {
        let query = sw_membership_probe_query(&relation);
        let row = query_one(client, &query, &[DuckDbParameter::Date(pick_date)])?;
        let actual_rows = row.try_get("actual_rows")?;
        record_missing_rows(plan, "index_sw_member", 1, actual_rows);
    }
    Ok(())
}

fn probe_pick_date_rows(
    client: &DuckDbConnection,
    plan: &mut DbLoadPlan,
    table: &str,
    pick_date: NaiveDate,
    count_expression: &str,
    expected_rows: i64,
    extra_predicate: Option<&str>,
) -> anyhow::Result<()> {
    let Some(relation) = plan.relation_sql(table) else {
        return Ok(());
    };
    let query = pick_date_probe_query(&relation, count_expression, extra_predicate);
    let row = query_one(client, &query, &[DuckDbParameter::Date(pick_date)])?;
    let actual_rows = row.try_get("actual_rows")?;
    record_missing_rows(plan, table, expected_rows, actual_rows);
    Ok(())
}

fn query_one(
    client: &DuckDbConnection,
    sql: &str,
    parameters: &[DuckDbParameter],
) -> anyhow::Result<DuckDbRow> {
    client
        .query_rows(sql, parameters)?
        .into_iter()
        .next()
        .ok_or_else(|| anyhow::anyhow!("DuckDB query returned no rows"))
}

fn pick_date_probe_query(
    relation: &str,
    count_expression: &str,
    extra_predicate: Option<&str>,
) -> String {
    let predicate = extra_predicate.unwrap_or("");
    format!(
        "SELECT {count_expression}::bigint AS actual_rows FROM {relation} WHERE trade_date = $1 {predicate}"
    )
}

fn sw_membership_probe_query(relation: &str) -> String {
    format!(
        "SELECT count(*)::bigint AS actual_rows FROM {relation} WHERE ts_code IS NOT NULL AND l2_code IS NOT NULL AND in_date IS NOT NULL AND trim(ts_code) <> '' AND trim(l2_code) <> '' AND in_date <= $1::date AND (out_date IS NULL OR $1::date < out_date)"
    )
}

pub(crate) fn plan_from_inspections(
    inspections: &BTreeMap<String, DbRelationInspection>,
) -> DbLoadPlan {
    let mut sources = BTreeMap::new();
    let mut db_data_gaps = BTreeMap::new();
    for spec in DB_TABLE_SPECS {
        let inspection = inspections.get(spec.name);
        let Some(relation) = inspection.and_then(|inspection| inspection.relation.clone()) else {
            sources.insert(spec.name, DbTableSource::Empty);
            db_data_gaps.insert(spec.name.to_string(), DbDataGap::missing_table());
            continue;
        };
        let missing_columns = spec
            .columns
            .iter()
            .map(|(column, _)| *column)
            .filter(|column| {
                !inspection.is_some_and(|inspection| inspection.columns.contains(*column))
            })
            .map(str::to_string)
            .collect::<Vec<_>>();
        if missing_columns.is_empty() {
            sources.insert(spec.name, DbTableSource::Relation(relation));
        } else {
            sources.insert(spec.name, DbTableSource::Empty);
            db_data_gaps.insert(
                spec.name.to_string(),
                DbDataGap::schema_mismatch(missing_columns),
            );
        }
    }
    DbLoadPlan {
        sources,
        db_data_gaps,
    }
}

pub(crate) fn record_missing_rows(
    plan: &mut DbLoadPlan,
    table: &str,
    expected_rows: i64,
    actual_rows: i64,
) {
    if actual_rows < expected_rows && !plan.db_data_gaps.contains_key(table) {
        plan.db_data_gaps.insert(
            table.to_string(),
            DbDataGap::missing_rows(expected_rows, actual_rows),
        );
    }
}

pub(crate) fn finish_preflight(
    mut plan: DbLoadPlan,
    strict_tables: &BTreeSet<String>,
    pick_date: NaiveDate,
) -> anyhow::Result<DbLoadPlan> {
    let strict_gaps = plan
        .db_data_gaps
        .iter()
        .filter(|(table, _)| strict_tables.contains(*table))
        .map(|(table, gap)| format_gap(table, gap))
        .collect::<Vec<_>>();
    if !strict_gaps.is_empty() {
        anyhow::bail!(
            "DB preflight failed for pick_date {pick_date}: {}",
            strict_gaps.join("; ")
        );
    }
    plan.db_data_gaps
        .retain(|table, _| !strict_tables.contains(table));
    Ok(plan)
}

fn format_gap(table: &str, gap: &DbDataGap) -> String {
    let mut message = format!("table={table} reason={}", gap.reason.as_str());
    match gap.reason {
        DbDataGapReason::SchemaMismatch if !gap.missing_columns.is_empty() => {
            message.push_str(&format!(
                " missing_columns={}",
                gap.missing_columns.join(",")
            ));
        }
        DbDataGapReason::MissingRows => {
            if let (Some(expected_rows), Some(actual_rows)) = (gap.expected_rows, gap.actual_rows) {
                message.push_str(&format!(
                    " expected_rows={expected_rows} actual_rows={actual_rows}"
                ));
            }
        }
        _ => {}
    }
    message
}

fn adapter_cte(spec: &DbTableSpec, alias: &str, source: &DbTableSource) -> String {
    let columns = spec
        .columns
        .iter()
        .map(|(column, _)| quote_identifier(column))
        .collect::<Vec<_>>()
        .join(", ");
    match source {
        DbTableSource::Relation(relation) => format!(
            "{alias} AS NOT MATERIALIZED (SELECT {columns} FROM {})",
            relation.qualified_name()
        ),
        DbTableSource::Empty => {
            let empty_columns = spec
                .columns
                .iter()
                .map(|(column, sql_type)| {
                    format!("NULL::{sql_type} AS {}", quote_identifier(column))
                })
                .collect::<Vec<_>>()
                .join(", ");
            format!("{alias} AS (SELECT {empty_columns} WHERE FALSE)")
        }
    }
}

fn quote_identifier(identifier: &str) -> String {
    format!("\"{}\"", identifier.replace('"', "\"\""))
}

fn relation_placeholder(table: &str) -> String {
    format!("{{{{{table}}}}}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn price_basis_reference_is_required_by_db_preflight() {
        let mut inspection = DbRelationInspection::available_for_spec("stock_stk_factor_pro");
        inspection.columns.remove("close_qfq");
        let plan = plan_from_inspections(&BTreeMap::from([(
            "stock_stk_factor_pro".to_string(),
            inspection,
        )]));
        let error = finish_preflight(
            plan,
            &BTreeSet::from(["stock_stk_factor_pro".to_string()]),
            test_pick_date(),
        )
        .expect_err("missing qfq reference must stop mixed-basis preparation")
        .to_string();
        assert!(error.contains("close_qfq"), "{error}");
    }

    #[test]
    fn adapted_query_uses_resolved_relations_and_typed_empty_ctes() {
        let plan = DbLoadPlan::for_test([
            (
                "stock_stk_factor_pro",
                Some("market_data.stock_stk_factor_pro"),
            ),
            ("calc_daily_industry_moneyflow", None),
        ]);
        let query = plan.adapt_query(
            "WITH selected AS (SELECT * FROM {{calc_daily_industry_moneyflow}}) SELECT s.ts_code FROM {{stock_stk_factor_pro}} s LEFT JOIN selected ON true",
        );

        assert!(query.contains("db_src_stock_stk_factor_pro AS NOT MATERIALIZED"));
        assert!(query.contains("FROM \"market_data\".\"stock_stk_factor_pro\""));
        assert!(query.contains("db_src_calc_daily_industry_moneyflow AS"));
        assert!(query.contains("NULL::text AS \"industry_code\""));
        assert!(query.contains("NULL::date AS \"trade_date\""));
        assert!(query.contains("NULL::double precision AS \"net_mf_amount\""));
        assert!(!query.contains("FROM calc_daily_industry_moneyflow"));
        assert!(!query.contains("{{"));
    }

    #[test]
    fn adapted_query_only_replaces_relation_references() {
        let plan = DbLoadPlan::for_test([("stock_moneyflow", None)]);
        let query = plan.adapt_query(
            "SELECT 'stock_moneyflow' AS source_name, stock_moneyflow_status FROM {{stock_moneyflow}}",
        );

        assert!(query.contains("'stock_moneyflow' AS source_name"));
        assert!(query.contains("stock_moneyflow_status"));
        assert!(query.contains("FROM db_src_stock_moneyflow"));
    }

    #[test]
    fn capability_gaps_take_priority_and_strict_failures_are_aggregated() {
        let inspections = BTreeMap::from([
            (
                "stock_stk_factor_pro".to_string(),
                DbRelationInspection::missing(),
            ),
            (
                "index_idx_factor_pro".to_string(),
                DbRelationInspection::available_with_columns(
                    "public",
                    "index_idx_factor_pro",
                    ["ts_code", "trade_date"],
                ),
            ),
        ]);
        let strict_tables = BTreeSet::from([
            "stock_stk_factor_pro".to_string(),
            "index_idx_factor_pro".to_string(),
        ]);

        let mut plan = plan_from_inspections(&inspections);
        record_missing_rows(&mut plan, "stock_stk_factor_pro", 235, 0);
        let error = finish_preflight(plan, &strict_tables, test_pick_date())
            .expect_err("strict capability gaps should stop the load")
            .to_string();

        assert!(error.contains("stock_stk_factor_pro"));
        assert!(error.contains("missing_table"));
        assert!(error.contains("index_idx_factor_pro"));
        assert!(error.contains("schema_mismatch"));
        assert!(error.contains("close"));
        assert!(!error.contains("expected_rows=235 actual_rows=0"));
    }

    #[test]
    fn non_strict_missing_rows_remain_readable_and_are_recorded() {
        let inspections = BTreeMap::from([
            (
                "stock_stk_factor_pro".to_string(),
                DbRelationInspection::available_for_spec("stock_stk_factor_pro"),
            ),
            (
                "calc_daily_industry_moneyflow".to_string(),
                DbRelationInspection::available_for_spec("calc_daily_industry_moneyflow"),
            ),
        ]);
        let mut plan = plan_from_inspections(&inspections);
        record_missing_rows(&mut plan, "calc_daily_industry_moneyflow", 1, 0);

        let plan = finish_preflight(
            plan,
            &BTreeSet::from(["stock_stk_factor_pro".to_string()]),
            test_pick_date(),
        )
        .unwrap();

        assert_eq!(
            plan.db_data_gaps["calc_daily_industry_moneyflow"].reason,
            DbDataGapReason::MissingRows
        );
        let query = plan.adapt_query(
            "WITH x AS (SELECT * FROM {{calc_daily_industry_moneyflow}}) SELECT * FROM x",
        );
        assert!(query.contains("FROM \"public\".\"calc_daily_industry_moneyflow\""));
    }

    #[test]
    fn non_strict_calculation_table_gap_uses_typed_empty_source() {
        let inspections = BTreeMap::from([
            (
                "stock_stk_factor_pro".to_string(),
                DbRelationInspection::available_for_spec("stock_stk_factor_pro"),
            ),
            (
                "calc_daily_czsc_structure".to_string(),
                DbRelationInspection::missing(),
            ),
        ]);

        let plan = finish_preflight(
            plan_from_inspections(&inspections),
            &BTreeSet::from(["stock_stk_factor_pro".to_string()]),
            test_pick_date(),
        )
        .unwrap();

        assert_eq!(
            plan.db_data_gaps["calc_daily_czsc_structure"].reason,
            DbDataGapReason::MissingTable
        );
        let query = plan.adapt_query(
            "SELECT c.daily_status, c.daily_source_bar_valid FROM {{stock_stk_factor_pro}} s LEFT JOIN {{calc_daily_czsc_structure}} c ON c.ts_code = s.ts_code",
        );
        assert!(query.contains("db_src_calc_daily_czsc_structure AS"));
        assert!(query.contains("NULL::text AS \"daily_status\""));
        assert!(query.contains("NULL::boolean AS \"daily_source_bar_valid\""));
        assert!(query.contains("WHERE FALSE"));
    }

    #[test]
    fn index_market_probe_requires_current_core_benchmark() {
        let (count_expression, expected_rows, predicate) = index_factor_probe_spec();
        assert_eq!(expected_rows, 1);

        let query = pick_date_probe_query(
            "\"public\".\"index_idx_factor_pro\"",
            count_expression,
            Some(predicate),
        );

        assert!(query.contains("count(DISTINCT ts_code)::bigint AS actual_rows"));
        assert!(query.contains("ts_code = '000016.SH'"));
        assert!(!query.contains("000001.SH"));
    }

    #[test]
    fn sw_membership_probe_rejects_blank_codes() {
        let query = sw_membership_probe_query("\"public\".\"index_sw_member\"");

        assert!(query.contains("trim(ts_code) <> ''"));
        assert!(query.contains("trim(l2_code) <> ''"));
        assert!(query.contains("in_date <= $1::date"));
        assert!(query.contains("out_date IS NULL OR $1::date < out_date"));
        assert!(!query.contains("btrim("));
    }

    fn test_pick_date() -> chrono::NaiveDate {
        chrono::NaiveDate::from_ymd_opt(2024, 5, 6).unwrap()
    }
}
