use std::io::Write;
use std::net::TcpListener;
use std::process::{Command, Stdio};

use duckdb_neo::{
    Parameters,
    environment::{Environment, StorageLocation},
    instance::{AttachBuilder, Instance},
};
use stock_select::db::{DuckDbLocation, open_duckdb, open_duckdb_with_auth};

#[test]
fn local_duckdb_file_is_opened_read_only_and_must_exist() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("stock-cache.duckdb");
    assert!(open_duckdb(path.to_str().unwrap()).is_err());
    assert!(!path.exists());

    {
        let environment = Environment::new().unwrap();
        let instance = environment
            .open(StorageLocation::OnDisk(path.to_str().unwrap().to_owned()))
            .unwrap();
        let connection = instance.connect().unwrap();
        connection
            .execute("CREATE TABLE probe AS SELECT 7 AS value", Parameters::None)
            .unwrap();
    }
    let connection = open_duckdb(path.to_str().unwrap()).unwrap();
    connection.execute("SELECT value FROM probe").unwrap();
    assert!(connection.execute("INSERT INTO probe VALUES (8)").is_err());
}

#[test]
fn quack_uri_is_accepted_in_both_duckdb_forms() {
    for uri in ["quack:localhost:9494", "quack://localhost:9494"] {
        assert!(matches!(
            DuckDbLocation::parse(uri).unwrap(),
            DuckDbLocation::Quack(_)
        ));
    }
}

#[test]
fn python_query_bridge_preserves_dates_lists_nulls_and_numeric_values() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("cache.duckdb");
    {
        let environment = Environment::new().unwrap();
        let instance = environment
            .open(StorageLocation::OnDisk(path.to_str().unwrap().to_owned()))
            .unwrap();
        let connection = instance.connect().unwrap();
        connection.execute("CREATE TABLE sample AS SELECT '000001.SZ' AS code, DATE '2026-06-01' AS day, 1.25::DOUBLE AS price, NULL::VARCHAR AS note", Parameters::None).unwrap();
    }
    let request = serde_json::json!({"source": path.to_str().unwrap(),
        "sql": "SELECT * FROM sample WHERE code = ANY($1) AND day >= $2::DATE",
        "params": [["000001.SZ", "000002.SZ"], "2026-06-01"]});
    let mut process = Command::new(env!("CARGO_BIN_EXE_stock-select-rs"))
        .arg("db-query")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    process
        .stdin
        .take()
        .unwrap()
        .write_all(request.to_string().as_bytes())
        .unwrap();
    let output = process.wait_with_output().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let rows: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(rows[0]["day"], "2026-06-01");
    assert_eq!(rows[0]["price"], 1.25);
    assert!(rows[0]["note"].is_null());
}

#[test]
fn native_quack_authentication_and_read_only_queries_work() {
    let listener = TcpListener::bind("0.0.0.0:0").unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);
    let uri = format!("quack:{address}");
    let local_uri = format!("quack:127.0.0.1:{}", address.port());
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("cache.duckdb");
    {
        let environment = Environment::new().unwrap();
        let instance = environment
            .open(StorageLocation::OnDisk(path.to_str().unwrap().to_owned()))
            .unwrap();
        instance
            .connect()
            .unwrap()
            .execute(
                "CREATE TABLE probe AS SELECT 42 AS answer",
                Parameters::None,
            )
            .unwrap();
        instance
            .connect()
            .unwrap()
            .execute(
                "CREATE TABLE sample AS SELECT 'O''Brien' AS code, DATE '2026-06-01' AS day",
                Parameters::None,
            )
            .unwrap();
    }
    let environment = Environment::new().unwrap();
    let instance = Instance::new(&environment).unwrap();
    instance
        .attach(
            AttachBuilder::new(StorageLocation::OnDisk(path.to_str().unwrap().to_owned()))
                .options([("read_only", "true")])
                .make_default(),
        )
        .unwrap();
    let server = instance.connect().unwrap();
    server
        .execute(
            format!("CALL quack_serve('{uri}', token = 'test''token', allow_other_hostname = true, disable_ssl = true)"),
            Parameters::None,
        )
        .unwrap();

    assert!(open_duckdb_with_auth(&local_uri, Some("wrong"), None).is_err());
    let request = serde_json::json!({
        "source": local_uri,
        "sql": "SELECT code, 'literal $1' AS label FROM sample WHERE code = ANY($1) AND day >= $2::DATE -- $3\n",
        "params": [["O'Brien", "unused"], "2026-06-01"]
    });
    let mut process = Command::new(env!("CARGO_BIN_EXE_stock-select-rs"))
        .current_dir(directory.path())
        .arg("db-query")
        .env("QUACK_AUTH_TOKEN", "test'token")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    process
        .stdin
        .take()
        .unwrap()
        .write_all(request.to_string().as_bytes())
        .unwrap();
    let output = process.wait_with_output().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let rows: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(rows[0]["code"], "O'Brien");
    assert_eq!(rows[0]["label"], "literal $1");
    {
        let client = open_duckdb_with_auth(&local_uri, Some("test'token"), None).unwrap();
        client
            .execute("SELECT answer FROM probe WHERE answer = 42")
            .unwrap();
        assert!(client.execute("INSERT INTO probe VALUES (43)").is_err());
    }
    let request = serde_json::json!({
        "source": format!("quack:127.0.0.2:{}", address.port()),
        "sql": "SELECT answer FROM probe",
        "params": []
    });
    let mut process = Command::new(env!("CARGO_BIN_EXE_stock-select-rs"))
        .current_dir(directory.path())
        .arg("db-query")
        .env("QUACK_AUTH_TOKEN", "test'token")
        .env("QUACK_DISABLE_SSL", "true")
        .env_remove("QUACK_SSL_FINGERPRINT")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    process
        .stdin
        .take()
        .unwrap()
        .write_all(request.to_string().as_bytes())
        .unwrap();
    let output = process.wait_with_output().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let rows: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(rows[0]["answer"], 42);
    server
        .execute(format!("CALL quack_stop('{uri}')"), Parameters::None)
        .unwrap();
}

#[test]
#[ignore = "需要 STOCK_SELECT_INTEGRATION_SOURCE 指向实际 stock-cache 数据"]
fn actual_stock_cache_daily_dataset_contains_latest_sample() {
    let source = std::env::var("STOCK_SELECT_INTEGRATION_SOURCE").expect("test source is required");
    let day = chrono::NaiveDate::from_ymd_opt(2026, 11, 17).unwrap();
    let dataset = stock_select::db::fetch_db_native_daily_dataset(
        &source,
        chrono::NaiveDate::from_ymd_opt(2025, 11, 17).unwrap(),
        day,
    )
    .expect("actual stock-cache daily dataset should load");
    let row = dataset
        .rows
        .iter()
        .find(|row| row.ts_code == "000001.SZ" && row.trade_date == day)
        .expect("stock-cache should contain the sampled stock and date");
    assert!((row.close - 12.25).abs() < 1e-9);
    assert!(
        row.db_factors
            .get("macd_daily_hist")
            .is_some_and(|value| value.is_finite())
    );
}
