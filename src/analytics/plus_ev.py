"""Positive Expected Value (+EV) detection using DuckDB."""

from datetime import datetime, timezone
from pathlib import Path

import duckdb

from src.config import ANALYTICS_DIR, EV_THRESHOLD, FRESHNESS_MINUTES, STRICT_FRESHNESS
from src.analytics.arbitrage import write_partitioned


def detect_plus_ev():
    """Identify +EV bets above the configured threshold.

    Production-grade improvements:
    - Weighted consensus by bookmaker tier (sharp/mid/recreational)
    - Freshness: bookmaker_last_update within configured minutes (or disabled)
    - Filters: odds_decimal > 1.5, true_prob in [0.1, 0.9]
    - Confidence column: num_bookmakers_used
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
    weighted AS (
      SELECT *,
        CASE bookmaker
          WHEN 'lowvig' THEN 1.5
          WHEN 'betonlineag' THEN 1.5
          WHEN 'draftkings' THEN 1.0
          WHEN 'fanduel' THEN 1.0
          ELSE 0.7
        END AS weight
      FROM deduped
    ),
    no_vig AS (
      SELECT *,
        1.0 / odds_decimal AS implied_prob,
        SUM(1.0 / odds_decimal) OVER (PARTITION BY event_id, bookmaker, market) AS vig
      FROM weighted
    ),
    no_vig_probs AS (
      SELECT *,
        implied_prob / vig AS no_vig_prob,
        (implied_prob / vig) * weight AS weighted_prob
      FROM no_vig
    ),
    consensus_stats AS (
      SELECT
        event_id,
        market,
        outcome,
        point,
        SUM(weighted_prob) AS total_weighted,
        SUM(weight) AS total_weight,
        COUNT(DISTINCT bookmaker) AS book_count
      FROM no_vig_probs
      GROUP BY event_id, market, outcome, point
      HAVING COUNT(DISTINCT bookmaker) >= 3
    ),
    consensus_excl AS (
      SELECT
        nv.event_id,
        nv.market,
        nv.outcome,
        nv.point,
        nv.bookmaker,
        nv.odds_decimal,
        nv.odds_american,
        nv.weight,
        nv.no_vig_prob,
        nv.weighted_prob,
        cs.total_weighted,
        cs.total_weight,
        cs.book_count,
        -- Leave-one-out weighted consensus
        (cs.total_weighted - nv.weighted_prob)
          / NULLIF(cs.total_weight - nv.weight, 0) AS true_prob
      FROM no_vig_probs nv
      JOIN consensus_stats cs
        ON nv.event_id = cs.event_id
        AND nv.market = cs.market
        AND nv.outcome = cs.outcome
        AND nv.point IS NOT DISTINCT FROM cs.point
      WHERE cs.book_count >= 3
    ),
    event_meta AS (
      SELECT DISTINCT
        event_id, sport, league, home_team, away_team, commence_time
      FROM deduped
    )
    SELECT
      ce.event_id,
      em.sport,
      em.league,
      em.home_team,
      em.away_team,
      em.commence_time,
      ce.bookmaker,
      ce.market,
      ce.outcome,
      ce.point,
      ce.odds_decimal,
      ce.odds_american,
      ce.true_prob,
      ce.book_count AS num_bookmakers_used,
      (ce.true_prob * ce.odds_decimal - 1.0) AS ev,
      (ce.true_prob * ce.odds_decimal - 1.0) * 100.0 AS ev_pct
    FROM consensus_excl ce
    JOIN event_meta em ON ce.event_id = em.event_id
    WHERE ce.true_prob IS NOT NULL
      AND ce.odds_decimal > 1.5
      AND ce.true_prob BETWEEN 0.1 AND 0.9
      AND (ce.true_prob * ce.odds_decimal - 1.0) > {{threshold}}
    ORDER BY ev DESC
    """.format(threshold=EV_THRESHOLD)

    df = duckdb.sql(query).pl()

    # Clean up stale files per sport
    date_val = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for sport_dir in (ANALYTICS_DIR / f"date={date_val}").glob("sport=*"):
        old_path = sport_dir / "plus_ev.parquet"
        if old_path.exists():
            sport_key = sport_dir.name.replace("sport=", "")
            if "sport" not in df.columns or sport_key not in df["sport"].unique().to_list():
                old_path.unlink()
                print(f"  Removed stale: {old_path}")

    written = write_partitioned(df, ANALYTICS_DIR, "plus_ev.parquet")
    for p in written:
        print(f"  +EV output: {p}")

    return df, len(df)


if __name__ == "__main__":
    df, count = detect_plus_ev()
    print(f"+EV bets found: {count}")
