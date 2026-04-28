"""Arbitrage opportunity detection using DuckDB."""

from datetime import datetime, timezone
from pathlib import Path

import duckdb

from src.config import ANALYTICS_DIR, FRESHNESS_MINUTES, STRICT_FRESHNESS


def write_partitioned(df, base_dir: Path, filename: str) -> list[Path]:
    """Write DataFrame as Hive-partitioned Parquet.
    Removes old file before writing to ensure clean overwrite.
    """
    if df.is_empty():
        return []
    written: list[Path] = []
    date_val = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sport_val = "basketball_nba"
    partition_dir = base_dir / f"date={date_val}" / f"sport={sport_val}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    out_path = partition_dir / filename

    # Remove old file to ensure clean overwrite
    if out_path.exists():
        out_path.unlink()

    df.write_parquet(out_path)
    written.append(out_path)
    return written


def detect_arbitrage():
    """Scan processed odds for arbitrage opportunities.

    Production-grade filters:
    - Freshness: bookmaker_last_update within configured minutes
    - Valid outcome pairing (h2h: 2 teams; totals: Over/Under)
    - Skip incomplete markets (exactly 2 outcomes required)
    - Latest snapshot per bookmaker (ROW_NUMBER by last_update)
    """
    freshness_clause = (
        f"AND date_diff('minute', bookmaker_last_update, CURRENT_TIMESTAMP) < {FRESHNESS_MINUTES}"
        if STRICT_FRESHNESS
        else ""
    )

    query = f"""
    WITH latest AS (
      SELECT *,
        ROW_NUMBER() OVER (
          PARTITION BY event_id, bookmaker, market, outcome, point
          ORDER BY bookmaker_last_update DESC
        ) AS rn
      FROM read_parquet('data/processed/*/*/odds.parquet', hive_partitioning=1)
      WHERE is_live = false
        {freshness_clause}
    ),
    deduped AS (
      SELECT * FROM latest WHERE rn = 1
    ),
    best_odds AS (
      SELECT
        event_id,
        market,
        outcome,
        point,
        MAX(odds_decimal) AS best_decimal,
        FIRST(bookmaker ORDER BY odds_decimal DESC) AS best_bookmaker
      FROM deduped
      GROUP BY event_id, market, outcome, point
    ),
    margins AS (
      SELECT
        event_id,
        market,
        point,
        SUM(1.0 / best_decimal) AS margin,
        COUNT(DISTINCT best_bookmaker) AS num_bookmakers,
        COUNT(*) AS num_outcomes,
        LIST(outcome) AS outcomes
      FROM best_odds
      GROUP BY event_id, market, point
      HAVING margin < 1.0
        AND COUNT(DISTINCT best_bookmaker) >= 2
        AND COUNT(*) = 2
    ),
    -- Validate outcome pairing
    valid_arbs AS (
      SELECT m.*
      FROM margins m
      WHERE
        -- h2h: two different team names (not same team twice)
        (m.market = 'h2h' AND m.outcomes[1] != m.outcomes[2])
        OR
        -- totals: must be Over and Under
        (m.market = 'totals'
         AND 'Over' IN m.outcomes
         AND 'Under' IN m.outcomes)
    ),
    event_meta AS (
      SELECT DISTINCT
        event_id, sport, league, home_team, away_team, commence_time
      FROM deduped
    )
    SELECT
      em.event_id,
      em.sport,
      em.league,
      em.home_team,
      em.away_team,
      em.commence_time,
      v.market,
      v.point,
      v.margin,
      (1.0 / v.margin - 1.0) * 100.0 AS profit_pct,
      v.num_bookmakers,
      bo.outcome AS leg_outcome,
      bo.best_decimal AS leg_best_odds,
      bo.best_bookmaker AS leg_best_bookmaker,
      (1.0 / bo.best_decimal) / v.margin AS leg_stake_allocation
    FROM valid_arbs v
    JOIN best_odds bo
      ON v.event_id = bo.event_id
      AND v.market = bo.market
      AND v.point IS NOT DISTINCT FROM bo.point
    JOIN event_meta em ON v.event_id = em.event_id
    ORDER BY profit_pct DESC
    """

    df = duckdb.sql(query).pl()

    # Clean up old file if result is empty
    date_val = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sport_val = "basketball_nba"
    partition_dir = ANALYTICS_DIR / f"date={date_val}" / f"sport={sport_val}"
    old_path = partition_dir / "arbitrage.parquet"
    if df.is_empty() and old_path.exists():
        old_path.unlink()
        print(f"  Removed stale: {old_path}")

    written = write_partitioned(df, ANALYTICS_DIR, "arbitrage.parquet")
    for p in written:
        print(f"  Arbitrage output: {p}")

    return df, len(df)


if __name__ == "__main__":
    df, count = detect_arbitrage()
    print(f"Arbitrage opportunities found: {count}")
