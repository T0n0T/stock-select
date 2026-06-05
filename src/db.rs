use chrono::NaiveDate;
use postgres::{Client, NoTls};
use std::collections::BTreeMap;

use crate::model::{InstrumentInfo, MarketRow};

pub fn fetch_daily_window(
    dsn: &str,
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
            vol::double precision AS vol,
            turnover_rate::double precision AS turnover_rate
        FROM daily_market
        WHERE trade_date BETWEEN $1 AND $2
        ORDER BY ts_code ASC, trade_date ASC
        ",
        &[&start_date, &end_date],
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
                turnover_rate: optional_option_f64(&row, "turnover_rate")?,
            })
        })
        .collect()
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
