use chrono::NaiveDate;
use postgres::{Client, NoTls};

use crate::model::MarketRow;

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
            vol::double precision AS vol
        FROM daily_market
        WHERE trade_date BETWEEN $1 AND $2
          AND open IS NOT NULL
          AND high IS NOT NULL
          AND low IS NOT NULL
          AND close IS NOT NULL
          AND vol IS NOT NULL
        ORDER BY ts_code ASC, trade_date ASC
        ",
        &[&start_date, &end_date],
    )?;
    rows.into_iter()
        .map(|row| {
            Ok(MarketRow {
                ts_code: row.try_get("ts_code")?,
                trade_date: row.try_get("trade_date")?,
                open: row.try_get("open")?,
                high: row.try_get("high")?,
                low: row.try_get("low")?,
                close: row.try_get("close")?,
                vol: row.try_get("vol")?,
            })
        })
        .collect()
}
