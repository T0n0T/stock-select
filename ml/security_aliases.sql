-- Rust 筛选和 Python 标签共用的证券身份核验，不按代码尾号推断。
WITH old_bars AS MATERIALIZED (
    SELECT ts_code, trade_date, open, high, low, close, vol
    FROM stock_stk_factor_pro
    WHERE ts_code LIKE '%.BJ' AND ts_code NOT LIKE '920%.BJ'
), new_bars AS MATERIALIZED (
    SELECT ts_code, trade_date, open, high, low, close, vol
    FROM stock_stk_factor_pro
    WHERE ts_code LIKE '920%.BJ'
), matches AS (
    SELECT o.ts_code AS old_code, n.ts_code AS new_code,
           count(*) AS identical_raw_bars
    FROM old_bars o
    JOIN new_bars n
      ON o.trade_date = n.trade_date
     AND o.open = n.open AND o.high = n.high AND o.low = n.low
     AND o.close = n.close AND o.vol = n.vol
    WHERE o.open > 0 AND o.close > 0 AND o.vol > 0
    GROUP BY o.ts_code, n.ts_code
    HAVING count(*) >= 20
), checked AS (
    SELECT m.old_code, m.new_code, m.identical_raw_bars,
           max(o.trade_date) AS old_last_date,
           count(*) FILTER (WHERE n.ts_code IS NULL) AS missing_canonical_bars,
           count(*) FILTER (
               WHERE n.ts_code IS NOT NULL AND (
                   o.open IS DISTINCT FROM n.open OR o.high IS DISTINCT FROM n.high
                   OR o.low IS DISTINCT FROM n.low OR o.close IS DISTINCT FROM n.close
                   -- 部分旧代码为小数手，新代码为整数手；只允许相同的舍入结果。
                   OR round(o.vol) IS DISTINCT FROM round(n.vol)
                   OR abs(o.vol - n.vol) > 0.5
               )
           ) AS conflicting_raw_bars
    FROM matches m
    JOIN old_bars o ON o.ts_code = m.old_code
    LEFT JOIN new_bars n ON n.ts_code = m.new_code AND n.trade_date = o.trade_date
    GROUP BY m.old_code, m.new_code, m.identical_raw_bars
)
SELECT CASE
           WHEN count(*) OVER (PARTITION BY old_code) <> 1
             OR count(*) OVER (PARTITION BY new_code) <> 1
             OR missing_canonical_bars > 0 OR conflicting_raw_bars > 0
           THEN error('security identity is ambiguous or canonical raw history is inconsistent/incomplete')
           ELSE old_code
       END AS old_code,
       new_code, identical_raw_bars, old_last_date
FROM checked
ORDER BY old_code
