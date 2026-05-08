-- DuckDB Analytics Queries for Sports Odds Intelligence Platform
-- Run these against the Hive-partitioned Parquet data

-- 1. Create views for Hive-partitioned data
CREATE VIEW odds AS
    SELECT * FROM read_parquet('data/processed/**/*.parquet', hive_partitioning=1);

CREATE VIEW plus_ev AS
    SELECT * FROM read_parquet('data/analytics/**/*.parquet', hive_partitioning=1);

-- 2. Bookmaker coverage overview
SELECT 
    bookmaker,
    COUNT(DISTINCT event_id) as events_covered,
    COUNT(*) as total_odds,
    COUNT(DISTINCT market) as markets,
    ROUND(AVG(odds_decimal), 3) as avg_decimal_odds
FROM odds
GROUP BY bookmaker
ORDER BY events_covered DESC, total_odds DESC;

-- 3. Market distribution
SELECT 
    market,
    COUNT(DISTINCT event_id) as events,
    COUNT(*) as total_rows,
    ROUND(AVG(odds_decimal), 3) as avg_odds,
    ROUND(STDDEV(odds_decimal), 3) as std_odds
FROM odds
GROUP BY market
ORDER BY total_rows DESC;

-- 4. Vig analysis (implied probability sums)
SELECT 
    event_id,
    bookmaker,
    market,
    COALESCE(CAST(point AS VARCHAR), 'N/A') as point,
    ROUND(SUM(implied_probability), 4) as total_vig,
    ROUND(SUM(implied_probability) - 1.0, 4) as vig_margin,
    COUNT(*) as num_outcomes
FROM odds
WHERE market IN ('h2h', 'totals')
GROUP BY event_id, bookmaker, market, point
HAVING COUNT(*) >= 2
ORDER BY total_vig DESC;

-- 5. Best odds per outcome (H2H)
SELECT 
    event_id,
    outcome,
    MAX(odds_decimal) as best_decimal,
    MAX(odds_american) as best_american,
    FIRST(bookmaker ORDER BY odds_decimal DESC) as best_bookmaker,
    COUNT(DISTINCT bookmaker) as num_bookmakers,
    ROUND(STDDEV(odds_decimal), 3) as std_across_books
FROM odds
WHERE market = 'h2h'
GROUP BY event_id, outcome
ORDER BY best_decimal DESC;

-- 6. Totals over/under comparison
SELECT 
    event_id,
    COALESCE(CAST(point AS VARCHAR), 'N/A') as total_line,
    MAX(CASE WHEN outcome = 'Over' THEN odds_decimal END) as over_odds,
    MAX(CASE WHEN outcome = 'Under' THEN odds_decimal END) as under_odds,
    COUNT(DISTINCT bookmaker) as num_bookmakers
FROM odds
WHERE market = 'totals' AND outcome IN ('Over', 'Under')
GROUP BY event_id, point
ORDER BY num_bookmakers DESC;

-- 7. Spreads market depth
SELECT 
    event_id,
    COALESCE(CAST(point AS VARCHAR), 'N/A') as spread_line,
    COUNT(DISTINCT bookmaker) as num_bookmakers,
    COUNT(*) as total_rows,
    ROUND(AVG(odds_decimal), 3) as avg_odds,
    ROUND(STDDEV(odds_decimal), 3) as std_odds
FROM odds
WHERE market = 'spreads'
GROUP BY event_id, point
ORDER BY num_bookmakers DESC;

-- 8. Data freshness
SELECT 
    'Raw ingestion latency' as metric,
    ROUND(AVG(EXTRACT(EPOCH FROM (ingested_at_utc - bookmaker_last_update))/60), 1) as avg_minutes,
    MIN(EXTRACT(EPOCH FROM (ingested_at_utc - bookmaker_last_update))/60) as min_minutes,
    MAX(EXTRACT(EPOCH FROM (ingested_at_utc - bookmaker_last_update))/60) as max_minutes
FROM odds
UNION ALL
SELECT 
    'Time to game start',
    ROUND(AVG(EXTRACT(EPOCH FROM (commence_time - ingested_at_utc))/3600), 1),
    MIN(EXTRACT(EPOCH FROM (commence_time - ingested_at_utc))/3600),
    MAX(EXTRACT(EPOCH FROM (commence_time - ingested_at_utc))/3600)
FROM odds;

-- 9. Sharp vs recreational bookmaker comparison
WITH sharp AS (
    SELECT event_id, market, outcome, AVG(odds_decimal) as sharp_odds
    FROM odds
    WHERE bookmaker IN ('lowvig', 'betonlineag')
    GROUP BY event_id, market, outcome
),
recreational AS (
    SELECT event_id, market, outcome, AVG(odds_decimal) as rec_odds
    FROM odds
    WHERE bookmaker IN ('betmgm', 'betrivers', 'bovada')
    GROUP BY event_id, market, outcome
)
SELECT 
    s.event_id, s.market, s.outcome,
    ROUND(s.sharp_odds, 3) as sharp,
    ROUND(r.rec_odds, 3) as recreational,
    ROUND(r.rec_odds - s.sharp_odds, 3) as diff,
    ROUND((r.rec_odds - s.sharp_odds)/s.sharp_odds * 100, 2) as pct_diff
FROM sharp s
JOIN recreational r ON s.event_id = r.event_id 
    AND s.market = r.market 
    AND s.outcome = r.outcome
WHERE s.market = 'h2h'
ORDER BY ABS(pct_diff) DESC;

-- 10. +EV bets summary
SELECT 
    bookmaker, event_id, outcome, market,
    odds_decimal, odds_american, 
    ROUND(true_probability, 4) as true_prob,
    ROUND(ev * 100, 2) as ev_percent,
    num_bookmakers_used
FROM plus_ev
ORDER BY ev DESC;
