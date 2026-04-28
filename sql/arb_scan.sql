-- Standalone arbitrage scan query

WITH best_odds AS (
    SELECT
        event_id,
        market,
        outcome,
        MAX(odds_decimal) AS best_decimal,
        ARBITRARY(bookmaker) AS best_bookmaker
    FROM read_parquet('data/processed/odds.parquet')
    GROUP BY event_id, market, outcome
)
SELECT
    event_id,
    market,
    SUM(1.0 / best_decimal) AS margin
FROM best_odds
GROUP BY event_id, market
HAVING margin < 1.0;
