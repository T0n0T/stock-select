use arrow::array::{Array, Float64Array};
use chrono::{Datelike, NaiveDate};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde_json::json;
use std::fs::File;
use std::thread::sleep;
use std::time::Duration;
use stock_select::cache::{
    LOCAL_DERIVED_PREPARED_CACHE_SOURCE, PREPARED_CACHE_SCHEMA_VERSION, decode_prepared_cache_rows,
    history_payload_for_code, load_prepared_cache, load_prepared_cache_for_mode,
    load_prepared_dataset, prepared_cache_data_path, prepared_cache_meta_path,
    prepared_cache_paths, prepared_cache_retention_limit_from_sources,
    prune_eod_prepared_cache_to_limit, write_db_native_prepared_cache,
    write_db_native_prepared_dataset, write_prepared_cache, write_prepared_cache_for_mode,
};
use stock_select::model::{DbDataGap, DbDataGapReason, Method, PreparedDataset, PreparedRow};

#[test]
fn prepared_cache_schema_version_marks_parquet_format() {
    assert_eq!(PREPARED_CACHE_SCHEMA_VERSION, 21);
}

#[test]
fn prepared_cache_rejects_versions_without_multiperiod_factor_inputs() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 6, 13).unwrap();
    let rows = db_native_window_rows("000001.SZ", start_date, pick_date, 235);
    write_db_native_prepared_cache(
        root.path(),
        Method::Scm,
        pick_date,
        start_date,
        pick_date,
        252,
        &rows,
    )
    .unwrap();
    let path = prepared_cache_meta_path(root.path(), pick_date);
    let mut metadata: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    for old_version in [18, 19, 20] {
        metadata["schema_version"] = json!(old_version);
        std::fs::write(&path, serde_json::to_vec_pretty(&metadata).unwrap()).unwrap();
        assert!(
            load_prepared_cache(root.path(), Method::Scm, pick_date, start_date, pick_date)
                .unwrap()
                .is_none(),
            "schema {old_version}"
        );
    }
}

#[test]
fn db_native_cache_splits_pick_date_index_context_from_history_rows() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 6, 13).unwrap();
    let mut rows = db_native_window_rows("000001.SZ", start_date, pick_date, 235);
    rows[0].db_factors.insert("history_factor".to_string(), 9.0);
    rows.last_mut()
        .unwrap()
        .db_factors
        .insert("sw_l2_main_index_idx_close".to_string(), 12.0);
    rows.last_mut()
        .unwrap()
        .db_factors
        .insert("market_index_sse50_idx_close".to_string(), 11.0);
    rows.last_mut()
        .unwrap()
        .db_factors
        .insert("history_factor".to_string(), 13.0);

    write_db_native_prepared_dataset(
        root.path(),
        Method::Scm,
        pick_date,
        start_date,
        pick_date,
        235,
        &PreparedDataset {
            rows,
            db_data_gaps: std::collections::BTreeMap::new(),
        },
    )
    .unwrap();

    let paths = prepared_cache_paths(root.path(), pick_date, false);
    let context_data_path = paths.data_path.with_file_name("2026-06-15.context.parquet");
    let history_reader =
        ParquetRecordBatchReaderBuilder::try_new(File::open(&paths.data_path).unwrap()).unwrap();
    let history_schema = history_reader.schema();
    let context_reader =
        ParquetRecordBatchReaderBuilder::try_new(File::open(context_data_path).unwrap()).unwrap();
    let context_schema = context_reader.schema();
    assert!(!history_schema.fields().iter().any(|field| {
        field.name() == "market_index_sse50_idx_close"
            || field.name() == "sw_l2_main_index_idx_close"
    }));
    assert!(
        context_schema
            .fields()
            .iter()
            .any(|field| field.name() == "market_index_sse50_idx_close")
    );

    let loaded = load_prepared_dataset(root.path(), Method::Scm, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();
    assert_eq!(loaded.rows[0].db_factors["history_factor"], 9.0);
    let latest = loaded
        .rows
        .iter()
        .find(|row| row.trade_date == pick_date)
        .unwrap();
    assert_eq!(latest.db_factors["market_index_sse50_idx_close"], 11.0);
    assert_eq!(latest.db_factors["sw_l2_main_index_idx_close"], 12.0);
    assert_eq!(latest.db_factors["history_factor"], 13.0);
}

#[test]
fn stk_factor_pro_rejects_pre_extension_prepared_cache() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 1, 30).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 2, 1).unwrap();
    let rows = (0..245)
        .map(|offset| {
            prepared_row(
                "603409.SH",
                start_date + chrono::Duration::days(offset),
                40.04,
            )
        })
        .chain(std::iter::once(prepared_row("603409.SH", pick_date, 40.04)))
        .collect::<Vec<_>>();
    write_db_native_prepared_cache(
        root.path(),
        Method::Scm,
        pick_date,
        start_date,
        pick_date,
        rows.len() as u32,
        &rows,
    )
    .unwrap();
    assert!(
        load_prepared_cache(root.path(), Method::Scm, pick_date, start_date, pick_date)
            .unwrap()
            .is_some()
    );
    let path = prepared_cache_meta_path(root.path(), pick_date);
    let mut metadata: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    metadata["schema_version"] = json!(14);
    std::fs::write(&path, serde_json::to_vec(&metadata).unwrap()).unwrap();
    assert!(
        load_prepared_cache(root.path(), Method::Scm, pick_date, start_date, pick_date)
            .unwrap()
            .is_none()
    );
}

#[test]
fn db_native_cache_rejects_missing_price_basis_with_parquet_schema() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 1, 30).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 2, 1).unwrap();
    let rows = (0..245)
        .map(|offset| {
            prepared_row(
                "603409.SH",
                start_date + chrono::Duration::days(offset),
                40.04,
            )
        })
        .chain(std::iter::once(prepared_row("603409.SH", pick_date, 40.04)))
        .collect::<Vec<_>>();
    write_db_native_prepared_cache(
        root.path(),
        Method::Scm,
        pick_date,
        start_date,
        pick_date,
        246,
        &rows,
    )
    .unwrap();
    let path = prepared_cache_meta_path(root.path(), pick_date);
    let mut metadata: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    assert_eq!(metadata["calc_versions"]["price_basis"], "asof_qfq_v1");
    for method in [Method::Scm, Method::Pbm, Method::B2] {
        assert_eq!(
            load_prepared_cache(root.path(), method, pick_date, start_date, pick_date)
                .unwrap()
                .unwrap()
                .len(),
            rows.len()
        );
    }
    metadata["calc_versions"]
        .as_object_mut()
        .unwrap()
        .remove("price_basis");
    std::fs::write(&path, serde_json::to_vec(&metadata).unwrap()).unwrap();

    for method in [Method::Scm, Method::Pbm, Method::B2] {
        assert!(
            load_prepared_cache(root.path(), method, pick_date, start_date, pick_date)
                .unwrap()
                .is_none()
        );
    }
}

#[test]
fn all_methods_rebuild_db_native_cache_without_completed_month_macd() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 1, 30).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 2, 1).unwrap();
    let rows = (0..245)
        .map(|offset| {
            prepared_row(
                "603409.SH",
                start_date + chrono::Duration::days(offset),
                40.04,
            )
        })
        .chain(std::iter::once(prepared_row("603409.SH", pick_date, 40.04)))
        .collect::<Vec<_>>();
    write_db_native_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        246,
        &rows,
    )
    .unwrap();
    let path = prepared_cache_meta_path(root.path(), pick_date);
    let original = std::fs::read(&path).unwrap();
    let mut metadata: serde_json::Value = serde_json::from_slice(&original).unwrap();
    metadata["calc_versions"]
        .as_object_mut()
        .unwrap()
        .remove("monthly_macd_history");
    std::fs::write(&path, serde_json::to_vec(&metadata).unwrap()).unwrap();

    for method in [Method::B2, Method::Scm, Method::Pbm] {
        assert!(
            load_prepared_cache(root.path(), method, pick_date, start_date, pick_date)
                .unwrap()
                .is_none(),
            "{method:?} must rebuild a cache that only carries pick-date MACD"
        );
    }
    std::fs::write(path, original).unwrap();
    for method in [Method::Scm, Method::Pbm, Method::B2] {
        assert!(
            load_prepared_cache(root.path(), method, pick_date, start_date, pick_date)
                .unwrap()
                .is_some()
        );
    }
}

#[test]
fn prepared_cache_pasw_l2_use_parquet_data_extension() {
    let root = tempfile::tempdir().unwrap();
    let date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    assert_eq!(
        prepared_cache_data_path(root.path(), date),
        root.path().join("prepared/2026-05-25.parquet")
    );
    assert_eq!(
        prepared_cache_meta_path(root.path(), date),
        root.path().join("prepared/2026-05-25.meta.json")
    );
}

#[test]
fn prepared_cache_pasw_l2_support_intraday_layout_without_overwriting_eod() {
    let root = tempfile::tempdir().unwrap();
    let date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    let eod = prepared_cache_paths(root.path(), date, false);
    let intraday = prepared_cache_paths(root.path(), date, true);

    assert_eq!(
        eod.data_path,
        root.path().join("prepared/2026-05-25.parquet")
    );
    assert_eq!(
        eod.meta_path,
        root.path().join("prepared/2026-05-25.meta.json")
    );
    assert_eq!(
        intraday.data_path,
        root.path().join("prepared/2026-05-25.intraday.parquet")
    );
    assert_eq!(
        intraday.meta_path,
        root.path().join("prepared/2026-05-25.intraday.meta.json")
    );
}

#[test]
fn prepared_cache_is_a_readable_parquet_file() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let rows = vec![prepared_row("000001.SZ", pick_date, 10.5)];

    write_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        pick_date,
        pick_date,
        &rows,
    )
    .unwrap();

    let bytes = std::fs::read(prepared_cache_data_path(root.path(), pick_date)).unwrap();
    assert_eq!(&bytes[..4], b"PAR1");
    assert_eq!(&bytes[bytes.len() - 4..], b"PAR1");
    assert_eq!(
        load_prepared_cache(root.path(), Method::B2, pick_date, pick_date, pick_date)
            .unwrap()
            .unwrap(),
        rows
    );
}

#[test]
fn prepared_cache_retention_limit_defaults_to_30_and_reads_sources() {
    assert_eq!(
        prepared_cache_retention_limit_from_sources(None, "").unwrap(),
        30
    );
    assert_eq!(
        prepared_cache_retention_limit_from_sources(
            Some("2"),
            "STOCK_SELECT_PREPARED_CACHE_LIMIT=5\n"
        )
        .unwrap(),
        2
    );
    assert_eq!(
        prepared_cache_retention_limit_from_sources(None, "STOCK_SELECT_PREPARED_CACHE_LIMIT=7\n")
            .unwrap(),
        7
    );
    assert!(prepared_cache_retention_limit_from_sources(Some("0"), "").is_err());
}

#[test]
fn prune_eod_prepared_cache_to_limit_keeps_newest_eod_and_ignores_intraday() {
    let root = tempfile::tempdir().unwrap();
    for day in 1..=4 {
        let pick_date = NaiveDate::from_ymd_opt(2026, 5, day).unwrap();
        write_prepared_cache(
            root.path(),
            Method::B2,
            pick_date,
            NaiveDate::from_ymd_opt(2023, 5, day).unwrap(),
            pick_date,
            &[prepared_row("000001.SZ", pick_date, 10.0 + f64::from(day))],
        )
        .unwrap();
    }
    let intraday_date = NaiveDate::from_ymd_opt(2026, 5, 1).unwrap();
    write_prepared_cache_for_mode(
        root.path(),
        Method::B2,
        intraday_date,
        NaiveDate::from_ymd_opt(2023, 5, 1).unwrap(),
        intraday_date,
        true,
        &[prepared_row("000001.SZ", intraday_date, 99.0)],
    )
    .unwrap();

    let removed = prune_eod_prepared_cache_to_limit(root.path(), 2).unwrap();

    assert_eq!(removed, 2);
    assert!(
        !prepared_cache_paths(
            root.path(),
            NaiveDate::from_ymd_opt(2026, 5, 1).unwrap(),
            false
        )
        .meta_path
        .exists()
    );
    assert!(
        !prepared_cache_paths(
            root.path(),
            NaiveDate::from_ymd_opt(2026, 5, 2).unwrap(),
            false
        )
        .data_path
        .exists()
    );
    assert!(
        prepared_cache_paths(
            root.path(),
            NaiveDate::from_ymd_opt(2026, 5, 3).unwrap(),
            false
        )
        .meta_path
        .exists()
    );
    assert!(
        prepared_cache_paths(
            root.path(),
            NaiveDate::from_ymd_opt(2026, 5, 4).unwrap(),
            false
        )
        .data_path
        .exists()
    );
    assert!(
        prepared_cache_paths(root.path(), intraday_date, true)
            .meta_path
            .exists()
    );
    assert!(
        prepared_cache_paths(root.path(), intraday_date, true)
            .data_path
            .exists()
    );
}

#[test]
fn prune_eod_prepared_cache_to_limit_keeps_newest_artifacts_by_file_time() {
    let root = tempfile::tempdir().unwrap();
    let old_pick_date = NaiveDate::from_ymd_opt(2026, 4, 1).unwrap();
    let newer_pick_date = NaiveDate::from_ymd_opt(2026, 5, 1).unwrap();
    let newest_pick_date = NaiveDate::from_ymd_opt(2026, 6, 1).unwrap();

    for pick_date in [newer_pick_date, newest_pick_date, old_pick_date] {
        write_prepared_cache(
            root.path(),
            Method::B2,
            pick_date,
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            pick_date,
            &[prepared_row("000001.SZ", pick_date, 10.0)],
        )
        .unwrap();
        sleep(Duration::from_millis(20));
    }

    let removed = prune_eod_prepared_cache_to_limit(root.path(), 2).unwrap();

    assert_eq!(removed, 1);
    assert!(
        prepared_cache_paths(root.path(), old_pick_date, false)
            .meta_path
            .exists()
    );
    assert!(
        prepared_cache_paths(root.path(), newest_pick_date, false)
            .meta_path
            .exists()
    );
    assert!(
        !prepared_cache_paths(root.path(), newer_pick_date, false)
            .meta_path
            .exists()
    );
}

#[test]
fn write_prepared_cache_prunes_eod_cache_to_default_limit_without_touching_intraday() {
    let root = tempfile::tempdir().unwrap();
    for day in 1..=31 {
        let pick_date = NaiveDate::from_ymd_opt(2026, 5, day).unwrap();
        write_prepared_cache(
            root.path(),
            Method::B2,
            pick_date,
            NaiveDate::from_ymd_opt(2023, 5, 1).unwrap(),
            pick_date,
            &[prepared_row("000001.SZ", pick_date, 10.0 + f64::from(day))],
        )
        .unwrap();
        sleep(Duration::from_millis(2));
    }
    let intraday_date = NaiveDate::from_ymd_opt(2026, 4, 30).unwrap();
    write_prepared_cache_for_mode(
        root.path(),
        Method::B2,
        intraday_date,
        NaiveDate::from_ymd_opt(2023, 4, 30).unwrap(),
        intraday_date,
        true,
        &[prepared_row("000001.SZ", intraday_date, 99.0)],
    )
    .unwrap();

    prune_eod_prepared_cache_to_limit(root.path(), 30).unwrap();

    let eod_meta_count = std::fs::read_dir(root.path().join("prepared"))
        .unwrap()
        .filter_map(Result::ok)
        .filter(|entry| {
            let file_name = entry.file_name();
            let file_name = file_name.to_string_lossy();
            file_name.ends_with(".meta.json") && !file_name.contains(".intraday.")
        })
        .count();
    assert_eq!(eod_meta_count, 30);
    assert!(
        prepared_cache_paths(root.path(), intraday_date, true)
            .meta_path
            .exists()
    );
}

#[test]
fn load_prepared_cache_ignores_legacy_bin_path() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    let data_path = root.path().join("prepared/2026-05-25.bin");
    std::fs::create_dir_all(data_path.parent().unwrap()).unwrap();
    std::fs::write(&data_path, prepared_cache_bytes()).unwrap();
    std::fs::write(
        prepared_cache_meta_path(root.path(), pick_date),
        serde_json::to_vec_pretty(&json!({
            "artifact_version": 1,
            "method": "b2",
            "shared_methods": ["b2", "scm", "pbm"],
            "pick_date": "2026-05-25",
            "start_date": "2025-05-24",
            "end_date": "2026-05-25",
            "schema_version": PREPARED_CACHE_SCHEMA_VERSION,
            "row_count": 1,
            "symbol_count": 1,
            "source_table": LOCAL_DERIVED_PREPARED_CACHE_SOURCE
        }))
        .unwrap(),
    )
    .unwrap();

    assert!(
        load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date)
            .unwrap()
            .is_none()
    );
}

#[test]
fn load_prepared_cache_rejects_legacy_bin_with_stale_schema_version() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    let data_path = root.path().join("prepared/2026-05-25.bin");
    std::fs::create_dir_all(data_path.parent().unwrap()).unwrap();
    std::fs::write(&data_path, prepared_cache_bytes()).unwrap();
    std::fs::write(
        prepared_cache_meta_path(root.path(), pick_date),
        serde_json::to_vec_pretty(&json!({
            "artifact_version": 1,
            "method": "b2",
            "shared_methods": ["b2", "scm", "pbm"],
            "pick_date": "2026-05-25",
            "start_date": "2025-05-24",
            "end_date": "2026-05-25",
            "schema_version": 5,
            "row_count": 1,
            "symbol_count": 1,
            "source_table": LOCAL_DERIVED_PREPARED_CACHE_SOURCE
        }))
        .unwrap(),
    )
    .unwrap();

    let rows =
        load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date).unwrap();

    assert!(rows.is_none());
}

#[test]
fn load_prepared_cache_rejects_current_schema_daily_market_metadata() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    let data_path = root.path().join("prepared/2026-05-25.bin.zst");
    std::fs::create_dir_all(data_path.parent().unwrap()).unwrap();
    std::fs::write(&data_path, prepared_cache_bytes()).unwrap();
    std::fs::write(
        prepared_cache_meta_path(root.path(), pick_date),
        serde_json::to_vec_pretty(&json!({
            "artifact_version": 1,
            "method": "b2",
            "shared_methods": ["b2", "scm", "pbm"],
            "pick_date": "2026-05-25",
            "start_date": "2025-05-24",
            "end_date": "2026-05-25",
            "schema_version": PREPARED_CACHE_SCHEMA_VERSION,
            "row_count": 1,
            "symbol_count": 1,
            "source_table": "daily_market"
        }))
        .unwrap(),
    )
    .unwrap();

    let rows =
        load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date).unwrap();

    assert!(rows.is_none());
}

#[test]
fn load_intraday_prepared_cache_rejects_legacy_bin_with_stale_schema_version() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    let data_path = root.path().join("prepared/2026-05-25.intraday.bin");
    std::fs::create_dir_all(data_path.parent().unwrap()).unwrap();
    std::fs::write(&data_path, prepared_cache_bytes()).unwrap();
    std::fs::write(
        prepared_cache_paths(root.path(), pick_date, true).meta_path,
        serde_json::to_vec_pretty(&json!({
            "artifact_version": 1,
            "method": "b2",
            "shared_methods": ["b2", "scm", "pbm"],
            "pick_date": "2026-05-25",
            "start_date": "2025-05-24",
            "end_date": "2026-05-25",
            "schema_version": 5,
            "row_count": 1,
            "symbol_count": 1,
            "source_table": "daily_market",
            "mode": "intraday_snapshot",
            "source": "tushare_rt_k"
        }))
        .unwrap(),
    )
    .unwrap();

    let rows = load_prepared_cache_for_mode(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        true,
    )
    .unwrap();

    assert!(rows.is_none());
}

#[test]
fn load_prepared_cache_prefers_parquet_and_ignores_legacy_binary_files() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    let prepared_dir = root.path().join("prepared");
    std::fs::create_dir_all(&prepared_dir).unwrap();

    write_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &[prepared_row("000001.SZ", pick_date, 12.0)],
    )
    .unwrap();
    std::fs::write(
        prepared_dir.join("2026-05-25.bin"),
        prepared_cache_bytes_for_rows_legacy(&[prepared_row("000001.SZ", pick_date, 10.0)]),
    )
    .unwrap();

    let rows = load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();

    assert_eq!(rows[0].close, 12.0);
}

#[test]
fn rejects_current_prepared_cache_binary_row() {
    let error = decode_prepared_cache_rows(b"SSPRBIN1")
        .unwrap_err()
        .to_string();
    assert!(error.contains("binary"), "{error}");
}

#[test]
fn rejects_legacy_prepared_cache_binary_factor_map() {
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let row = prepared_row_with_factors(
        "000001.SZ",
        pick_date,
        10.0,
        &[("boll_width_pct", 12.3), ("wr_qfq", -87.5)],
    );

    let error = decode_prepared_cache_rows(&prepared_cache_bytes_for_rows_legacy(&[row]))
        .expect_err("legacy binary caches are no longer supported")
        .to_string();

    assert!(error.contains("binary"), "{error}");
}

#[test]
fn load_prepared_cache_requires_matching_metadata() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    let rows = [prepared_row("000001.SZ", pick_date, 10.0)];
    write_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &rows,
    )
    .unwrap();
    std::fs::remove_file(prepared_cache_meta_path(root.path(), pick_date)).unwrap();

    assert!(
        load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date)
            .unwrap()
            .is_none()
    );

    std::fs::write(
        prepared_cache_meta_path(root.path(), pick_date),
        serde_json::to_vec_pretty(&json!({
            "artifact_version": 1,
            "method": "b2",
            "shared_methods": ["b2", "scm", "pbm"],
            "pick_date": "2026-05-25",
            "start_date": "2025-05-24",
            "end_date": "2026-05-25",
            "schema_version": PREPARED_CACHE_SCHEMA_VERSION,
            "row_count": 1,
            "symbol_count": 1,
            "source_table": LOCAL_DERIVED_PREPARED_CACHE_SOURCE
        }))
        .unwrap(),
    )
    .unwrap();

    let rows = load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();

    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].ts_code, "000001.SZ");
}

#[test]
fn load_prepared_cache_rejects_rows_missing_requested_end_date() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 8).unwrap();
    let start_date = pick_date - chrono::Duration::days(366);
    write_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &[prepared_row(
            "000001.SZ",
            NaiveDate::from_ymd_opt(2026, 6, 5).unwrap(),
            10.0,
        )],
    )
    .unwrap();

    let rows =
        load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date).unwrap();

    assert!(rows.is_none());
}

#[test]
fn prepared_cache_round_trips_db_factor_extras() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    let mut row = prepared_row("000001.SZ", pick_date, 10.0);
    row.db_factors.insert("boll_width_pct".to_string(), 12.3456);
    row.db_factors.insert("wr_qfq".to_string(), -87.5);

    write_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &[row],
    )
    .unwrap();

    let metadata: serde_json::Value = serde_json::from_slice(
        &std::fs::read(prepared_cache_meta_path(root.path(), pick_date)).unwrap(),
    )
    .unwrap();
    assert_eq!(metadata["schema_version"], PREPARED_CACHE_SCHEMA_VERSION);
    assert!(
        metadata["shared_methods"]
            .as_array()
            .unwrap()
            .iter()
            .any(|method| method.as_str() == Some("scm"))
    );

    let rows = load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();

    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].db_factors["boll_width_pct"], 12.3456);
    assert_eq!(rows[0].db_factors["wr_qfq"], -87.5);
}

#[test]
fn write_db_native_prepared_cache_records_source_window_and_calc_versions() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 6, 13).unwrap();
    let rows = db_native_window_rows("000001.SZ", start_date, pick_date, 235);

    write_db_native_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        252,
        &rows,
    )
    .unwrap();

    let metadata: serde_json::Value = serde_json::from_slice(
        &std::fs::read(prepared_cache_meta_path(root.path(), pick_date)).unwrap(),
    )
    .unwrap();
    assert_eq!(metadata["schema_version"], PREPARED_CACHE_SCHEMA_VERSION);
    assert_eq!(metadata["source_table"], "stock-cache-db-native");
    assert_eq!(metadata["source"], "stock-cache-db-native");
    assert_eq!(metadata["start_date"], start_date.to_string());
    assert_eq!(metadata["end_date"], pick_date.to_string());
    assert_eq!(metadata["window_trading_days"], 235);
    assert_eq!(metadata["window_start_date"], start_date.to_string());
    assert_eq!(metadata["window_end_date"], pick_date.to_string());
    assert_eq!(metadata["calc_versions"]["macd"], "macd_qfq_12_26_9_v1");
    assert_eq!(metadata["calc_versions"]["rolling"], "rolling_qfq_v1");
    assert_eq!(
        metadata["calc_versions"]["czsc"],
        "czsc_structure_qfq_min6_r7_v1"
    );
    assert!(metadata["calc_versions"].get("left_peak").is_none());
    assert_eq!(metadata["membership_sources"]["sw_l2"], "index_sw_member");
    assert_eq!(
        metadata["membership_sources"]["market_index_weights"],
        "index_weight"
    );
    assert!(metadata["membership_sources"].get("ths").is_none());

    let loaded = load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();
    assert_eq!(loaded.len(), rows.len());
}

#[test]
fn db_native_prepared_cache_round_trips_data_gaps_without_bumping_schema() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 6, 13).unwrap();
    let rows = db_native_window_rows("000001.SZ", start_date, pick_date, 235);
    let dataset = PreparedDataset {
        rows,
        db_data_gaps: std::collections::BTreeMap::from([
            (
                "calc_daily_industry_moneyflow".to_string(),
                DbDataGap {
                    reason: DbDataGapReason::MissingRows,
                    missing_columns: Vec::new(),
                    expected_rows: Some(1),
                    actual_rows: Some(0),
                },
            ),
            (
                "calc_daily_indicators".to_string(),
                DbDataGap {
                    reason: DbDataGapReason::SchemaMismatch,
                    missing_columns: vec!["daily_hist_x2_asof".to_string()],
                    expected_rows: None,
                    actual_rows: None,
                },
            ),
        ]),
    };

    write_db_native_prepared_dataset(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        252,
        &dataset,
    )
    .unwrap();

    let metadata: serde_json::Value = serde_json::from_slice(
        &std::fs::read(prepared_cache_meta_path(root.path(), pick_date)).unwrap(),
    )
    .unwrap();
    assert_eq!(metadata["schema_version"], PREPARED_CACHE_SCHEMA_VERSION);
    assert_eq!(
        metadata["db_data_gaps"]["calc_daily_industry_moneyflow"],
        json!({
            "reason": "missing_rows",
            "expected_rows": 1,
            "actual_rows": 0
        })
    );
    assert_eq!(
        metadata["db_data_gaps"]["calc_daily_indicators"],
        json!({
            "reason": "schema_mismatch",
            "missing_columns": ["daily_hist_x2_asof"]
        })
    );

    let loaded = load_prepared_dataset(root.path(), Method::B2, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();
    assert_eq!(loaded.db_data_gaps, dataset.db_data_gaps);
    assert_eq!(loaded.rows.len(), dataset.rows.len());
}

#[test]
fn load_prepared_cache_rejects_db_native_cache_with_legacy_structure_version() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 6, 13).unwrap();
    let rows = db_native_window_rows("000001.SZ", start_date, pick_date, 235);

    write_db_native_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        252,
        &rows,
    )
    .unwrap();

    let metadata_path = prepared_cache_meta_path(root.path(), pick_date);
    let mut metadata: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&metadata_path).unwrap()).unwrap();
    metadata["calc_versions"] = json!({
        "macd": "macd_qfq_12_26_9_v1",
        "rolling": "rolling_qfq_v1",
        "left_peak": "left_peak_qfq_v1"
    });
    std::fs::write(metadata_path, serde_json::to_vec_pretty(&metadata).unwrap()).unwrap();

    let loaded =
        load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date).unwrap();

    assert!(loaded.is_none());
}

#[test]
fn load_prepared_cache_rejects_db_native_cache_with_short_decoded_window() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 6, 15).unwrap();
    let mut row = prepared_row("000001.SZ", pick_date, 10.0);
    row.db_factors.insert("macd_daily_hist".to_string(), 0.1234);
    write_db_native_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        pick_date,
        pick_date,
        252,
        &[row],
    )
    .unwrap();
    std::fs::write(
        prepared_cache_meta_path(root.path(), pick_date),
        serde_json::to_vec_pretty(&json!({
            "artifact_version": 1,
            "method": "b2",
            "shared_methods": ["b2", "scm", "pbm"],
            "pick_date": pick_date,
            "start_date": start_date,
            "end_date": pick_date,
            "schema_version": PREPARED_CACHE_SCHEMA_VERSION,
            "row_count": 1,
            "symbol_count": 1,
            "source_table": "stock-cache-db-native",
            "source": "stock-cache-db-native",
            "compression": "zstd",
            "encoding": "dictionary_v2",
            "window_trading_days": 252,
            "window_start_date": start_date,
            "window_end_date": pick_date,
            "calc_versions": {
                "macd": "macd_qfq_12_26_9_v1",
                "rolling": "rolling_qfq_v1",
                "left_peak": "left_peak_qfq_v1"
            },
            "membership_sources": {
                "sw_l2": "index_sw_member"
            }
        }))
        .unwrap(),
    )
    .unwrap();

    let loaded =
        load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date).unwrap();

    assert!(loaded.is_none());
}

#[test]
fn write_prepared_cache_uses_parquet_payload() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    let rows = vec![
        prepared_row_with_factors(
            "000001.SZ",
            pick_date,
            10.0,
            &[("boll_width_pct", 12.3), ("wr_qfq", -87.5)],
        ),
        prepared_row_with_factors(
            "000002.SZ",
            pick_date,
            20.0,
            &[("boll_width_pct", 8.8), ("wr_qfq", -50.0)],
        ),
    ];

    write_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &rows,
    )
    .unwrap();

    let bytes = std::fs::read(prepared_cache_data_path(root.path(), pick_date)).unwrap();
    assert_eq!(&bytes[..4], b"PAR1");
    assert_eq!(&bytes[bytes.len() - 4..], b"PAR1");

    let metadata: serde_json::Value = serde_json::from_slice(
        &std::fs::read(prepared_cache_meta_path(root.path(), pick_date)).unwrap(),
    )
    .unwrap();
    assert_eq!(metadata["compression"], "zstd");
    assert_eq!(metadata["encoding"], "parquet");
    assert_ne!(metadata["source_table"], "daily_market");

    let loaded = load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();
    assert_eq!(loaded, rows);
}

#[test]
fn parquet_payload_is_readable_with_dynamic_factor_columns() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    let rows = vec![
        prepared_row_with_factors(
            "000001.SZ",
            pick_date,
            10.0,
            &[("boll_width_pct", 12.3), ("dist_to_up_limit_pct", 9.0)],
        ),
        prepared_row_with_factors(
            "000002.SZ",
            pick_date,
            20.0,
            &[("boll_width_pct", 8.8), ("wr_qfq", -50.0)],
        ),
        prepared_row_with_factors("000003.SZ", pick_date, 30.0, &[]),
    ];

    write_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &rows,
    )
    .unwrap();
    let parquet_size = std::fs::metadata(prepared_cache_data_path(root.path(), pick_date))
        .unwrap()
        .len();

    let file = File::open(prepared_cache_data_path(root.path(), pick_date)).unwrap();
    let mut reader = ParquetRecordBatchReaderBuilder::try_new(file)
        .unwrap()
        .build()
        .unwrap();
    let batch = reader.next().unwrap().unwrap();
    let schema = batch.schema();
    assert_eq!(schema.field(26).name(), "boll_width_pct");
    assert_eq!(schema.field(27).name(), "dist_to_up_limit_pct");
    assert_eq!(schema.field(28).name(), "wr_qfq");
    assert!(schema.index_of("db_factors").is_err());
    let boll = batch
        .column(schema.index_of("boll_width_pct").unwrap())
        .as_any()
        .downcast_ref::<Float64Array>()
        .unwrap();
    assert_eq!(boll.value(0), 12.3);
    assert_eq!(boll.value(1), 8.8);
    assert!(boll.is_null(2));
    let wr = batch
        .column(schema.index_of("wr_qfq").unwrap())
        .as_any()
        .downcast_ref::<Float64Array>()
        .unwrap();
    assert!(wr.is_null(0));
    assert_eq!(wr.value(1), -50.0);

    assert!(parquet_size > 0);
}

#[test]
fn intraday_prepared_cache_read_write_does_not_overwrite_eod_cache() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();

    write_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &[prepared_row("000001.SZ", pick_date, 10.0)],
    )
    .unwrap();
    write_prepared_cache_for_mode(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        true,
        &[prepared_row("000001.SZ", pick_date, 12.0)],
    )
    .unwrap();

    let eod = load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();
    let intraday = load_prepared_cache_for_mode(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        true,
    )
    .unwrap()
    .unwrap();

    assert_eq!(eod[0].close, 10.0);
    assert_eq!(intraday[0].close, 12.0);
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(
            &std::fs::read(prepared_cache_paths(root.path(), pick_date, true).meta_path).unwrap()
        )
        .unwrap()["mode"],
        "intraday_snapshot"
    );
}

#[test]
fn load_intraday_prepared_cache_accepts_previous_trade_date_window() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 4).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 6, 3).unwrap();
    let stored_start_date = previous_trade_date - chrono::Duration::days(366);
    let requested_start_date = pick_date - chrono::Duration::days(366);
    write_prepared_cache_for_mode(
        root.path(),
        Method::B2,
        pick_date,
        stored_start_date,
        pick_date,
        true,
        &[prepared_row("000001.SZ", pick_date, 12.0)],
    )
    .unwrap();

    let rows = load_prepared_cache_for_mode(
        root.path(),
        Method::B2,
        pick_date,
        requested_start_date,
        pick_date,
        true,
    )
    .unwrap()
    .unwrap();

    assert_eq!(rows[0].close, 12.0);
}

#[test]
fn scm_can_read_shared_prepared_cache_written_for_b2() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 4).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 6, 3).unwrap();
    write_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &[prepared_row("000001.SZ", pick_date, 12.0)],
    )
    .unwrap();

    let rows = load_prepared_cache(root.path(), Method::Scm, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();

    assert_eq!(rows[0].close, 12.0);
}

#[test]
fn builds_history_payload_for_candidate_code_from_prepared_rows() {
    let date1 = NaiveDate::from_ymd_opt(2026, 5, 24).unwrap();
    let date2 = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let rows = vec![
        prepared_row("000002.SZ", date1, 20.0),
        prepared_row("000001.SZ", date2, 10.5),
        prepared_row("000001.SZ", date1, 10.0),
    ];

    let history = history_payload_for_code(&rows, "000001.SZ");

    assert_eq!(history.len(), 2);
    assert_eq!(history[0]["close"], 10.0);
    assert_eq!(history[1]["close"], 10.5);
    assert_eq!(history[1]["volume"], 1000.0);
    assert_eq!(history[1]["turnover_n"], 12.0);
    assert_eq!(history[1]["turnover_rate"], 1.5);
    assert_eq!(history[1]["ma25"], 10.0);
    assert_eq!(history[1]["zxdq"], 10.2);
    assert_eq!(history[1]["zxdkx"], 10.1);
    assert_eq!(history[1]["macd_hist"], 0.1);
    assert_eq!(history[1]["db_factors"]["boll_width_pct"], 11.0);
}

#[test]
fn history_payload_skips_rows_with_non_finite_required_prices() {
    let date1 = NaiveDate::from_ymd_opt(2026, 5, 24).unwrap();
    let date2 = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let mut bad = prepared_row("000001.SZ", date1, 10.0);
    bad.open = f64::NAN;
    let rows = vec![bad, prepared_row("000001.SZ", date2, 10.5)];

    let history = history_payload_for_code(&rows, "000001.SZ");

    assert_eq!(history.len(), 1);
    assert_eq!(history[0]["trade_date"], "2026-05-25");
    assert_eq!(history[0]["open"], 10.0);
}

fn prepared_row(code: &str, trade_date: NaiveDate, close: f64) -> PreparedRow {
    prepared_row_with_factors(code, trade_date, close, &[("boll_width_pct", 11.0)])
}

fn db_native_window_rows(
    code: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
    trading_days: usize,
) -> Vec<PreparedRow> {
    assert!(trading_days >= 2);
    let mut rows = (0..(trading_days - 1))
        .map(|offset| {
            prepared_row(
                code,
                start_date + chrono::Duration::days(offset as i64),
                10.0 + offset as f64 * 0.01,
            )
        })
        .collect::<Vec<_>>();
    rows.push(prepared_row(code, end_date, 12.0));
    rows
}

fn prepared_row_with_factors(
    code: &str,
    trade_date: NaiveDate,
    close: f64,
    factors: &[(&str, f64)],
) -> PreparedRow {
    PreparedRow {
        ts_code: code.to_string(),
        trade_date,
        open: close - 0.5,
        high: close + 1.0,
        low: close - 1.0,
        close,
        volume: 1000.0,
        turnover_n: 12.0,
        turnover_rate: Some(1.5),
        k: 50.0,
        d: 40.0,
        j: 60.0,
        zxdq: Some(10.2),
        zxdkx: Some(10.1),
        dif: 0.3,
        dea: 0.2,
        macd_hist: 0.1,
        ma25: Some(10.0),
        ma60: Some(9.8),
        ma144: None,
        chg_d: Some(1.2),
        weekly_ma_bull: true,
        max_vol_not_bearish: false,
        v_shrink: true,
        safe_mode: false,
        lt_filter: true,
        db_factors: factors
            .iter()
            .map(|(key, value)| ((*key).to_string(), *value))
            .collect(),
    }
}

fn prepared_cache_bytes_for_rows_legacy(rows: &[PreparedRow]) -> Vec<u8> {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(b"SSPRBIN1");
    write_u64(&mut bytes, rows.len() as u64);
    for row in rows {
        write_string(&mut bytes, &row.ts_code);
        write_i32(&mut bytes, row.trade_date.num_days_from_ce());
        for value in [
            row.open,
            row.high,
            row.low,
            row.close,
            row.volume,
            row.turnover_n,
        ] {
            write_f64(&mut bytes, value);
        }
        write_option_f64(&mut bytes, row.turnover_rate);
        for value in [row.k, row.d, row.j] {
            write_f64(&mut bytes, value);
        }
        write_option_f64(&mut bytes, row.zxdq);
        write_option_f64(&mut bytes, row.zxdkx);
        for value in [row.dif, row.dea, row.macd_hist] {
            write_f64(&mut bytes, value);
        }
        write_option_f64(&mut bytes, row.ma25);
        write_option_f64(&mut bytes, row.ma60);
        write_option_f64(&mut bytes, row.ma144);
        write_option_f64(&mut bytes, row.chg_d);
        for value in [
            row.weekly_ma_bull,
            row.max_vol_not_bearish,
            row.v_shrink,
            row.safe_mode,
            row.lt_filter,
        ] {
            write_bool(&mut bytes, value);
        }
        write_u64(&mut bytes, row.db_factors.len() as u64);
        for (key, value) in &row.db_factors {
            write_string(&mut bytes, key);
            write_f64(&mut bytes, *value);
        }
    }
    bytes
}

fn prepared_cache_bytes() -> Vec<u8> {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(b"SSPRBIN1");
    write_u64(&mut bytes, 1);
    write_string(&mut bytes, "000001.SZ");
    write_i32(
        &mut bytes,
        NaiveDate::from_ymd_opt(2026, 5, 25)
            .unwrap()
            .num_days_from_ce(),
    );
    for value in [10.0, 11.0, 9.0, 10.5, 1000.0, 12.0] {
        write_f64(&mut bytes, value);
    }
    write_option_f64(&mut bytes, Some(1.5));
    for value in [50.0, 40.0, 60.0] {
        write_f64(&mut bytes, value);
    }
    write_option_f64(&mut bytes, Some(10.2));
    write_option_f64(&mut bytes, Some(10.1));
    for value in [0.3, 0.2, 0.1] {
        write_f64(&mut bytes, value);
    }
    write_option_f64(&mut bytes, Some(10.0));
    write_option_f64(&mut bytes, Some(9.8));
    write_option_f64(&mut bytes, None);
    write_option_f64(&mut bytes, Some(1.2));
    for value in [true, false, true, false, true, false] {
        write_bool(&mut bytes, value);
    }
    write_u64(&mut bytes, 0);
    bytes
}

fn write_string(out: &mut Vec<u8>, value: &str) {
    out.extend_from_slice(&(value.len() as u16).to_le_bytes());
    out.extend_from_slice(value.as_bytes());
}

fn write_bool(out: &mut Vec<u8>, value: bool) {
    out.push(u8::from(value));
}

fn write_option_f64(out: &mut Vec<u8>, value: Option<f64>) {
    match value {
        Some(value) => {
            write_bool(out, true);
            write_f64(out, value);
        }
        None => write_bool(out, false),
    }
}

fn write_u64(out: &mut Vec<u8>, value: u64) {
    out.extend_from_slice(&value.to_le_bytes());
}

fn write_i32(out: &mut Vec<u8>, value: i32) {
    out.extend_from_slice(&value.to_le_bytes());
}

fn write_f64(out: &mut Vec<u8>, value: f64) {
    out.extend_from_slice(&value.to_le_bytes());
}
