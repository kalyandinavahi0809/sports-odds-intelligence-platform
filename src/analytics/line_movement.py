"""Line Movement Intelligence — track odds changes across snapshots."""

import duckdb
from pathlib import Path

from src.config import PROCESSED_DIR


def compute_line_movement() -> Path:
    """Compute odds deltas between consecutive snapshots using DuckDB."""

    output_dir = Path("data/analytics/line_movement")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "line_movement.parquet"

    con = duckdb.connect(":memory:")

    # Build time-series view with snapshot ordering
    con.execute(f"""
        CREATE VIEW odds_series AS
        SELECT *,
            ROW_NUMBER() OVER (
                PARTITION BY event_id, bookmaker, market, outcome, point
                ORDER BY bookmaker_last_update DESC
            ) as snapshot_rank,
            DENSE_RANK() OVER (
                ORDER BY bookmaker_last_update
            ) as snapshot_id
        FROM read_parquet('{PROCESSED_DIR}/**/*.parquet', hive_partitioning=1)
        WHERE is_live = false
    """)

    # Compute latest and previous values with deltas
    con.execute(f"""
        COPY (
            WITH ranked AS (
                SELECT *,
                    LAG(odds_decimal) OVER (
                        PARTITION BY event_id, bookmaker, market, outcome, point
                        ORDER BY bookmaker_last_update
                    ) as prev_odds,
                    LAG(implied_probability) OVER (
                        PARTITION BY event_id, bookmaker, market, outcome, point
                        ORDER BY bookmaker_last_update
                    ) as prev_impl,
                    LAG(bookmaker_last_update) OVER (
                        PARTITION BY event_id, bookmaker, market, outcome, point
                        ORDER BY bookmaker_last_update
                    ) as prev_update
                FROM odds_series
            )
            SELECT
                event_id,
                home_team,
                away_team,
                commence_time,
                bookmaker,
                market,
                outcome,
                point,
                bookmaker_last_update as snapshot_time,
                odds_decimal as latest_odds,
                prev_odds as previous_odds,
                ROUND(odds_decimal - prev_odds, 4) as odds_delta,
                implied_probability as latest_impl_prob,
                prev_impl as previous_impl_prob,
                ROUND(implied_probability - prev_impl, 4) as impl_prob_delta,
                -- vig computation for this snapshot
                ROUND(
                    SUM(implied_probability) OVER (
                        PARTITION BY event_id, bookmaker, market, point
                        ORDER BY bookmaker_last_update
                        ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
                    ) - 1.0,
                    4
                ) as vig_delta,
                -- time since previous update
                EXTRACT(EPOCH FROM (bookmaker_last_update - prev_update)) / 60.0 as minutes_since_prev,
                ingested_at_utc,
                date,
                sport
            FROM ranked
            WHERE prev_odds IS NOT NULL
            ORDER BY ABS(odds_delta) DESC
        ) TO '{output_file}' (FORMAT PARQUET)
    """)

    # Also compute a summary by event/bookmaker
    summary_file = output_dir / "movement_summary.parquet"
    con.execute(f"""
        COPY (
            WITH movement AS (
                SELECT *,
                    LAG(odds_decimal) OVER (
                        PARTITION BY event_id, bookmaker, market, outcome, point
                        ORDER BY bookmaker_last_update
                    ) as prev_odds
                FROM read_parquet('{PROCESSED_DIR}/**/*.parquet', hive_partitioning=1)
                WHERE is_live = false
            ),
            grouped AS (
                SELECT
                    event_id,
                    home_team,
                    away_team,
                    bookmaker,
                    market,
                    outcome,
                    point,
                    COUNT(*) as num_snapshots,
                    MIN(odds_decimal) as min_odds,
                    MAX(odds_decimal) as max_odds,
                    ROUND(MAX(odds_decimal) - MIN(odds_decimal), 4) as odds_range,
                    FIRST(odds_decimal ORDER BY bookmaker_last_update ASC) as opening_odds,
                    LAST(odds_decimal ORDER BY bookmaker_last_update ASC) as latest_odds,
                    ROUND(
                        LAST(odds_decimal ORDER BY bookmaker_last_update ASC) -
                        FIRST(odds_decimal ORDER BY bookmaker_last_update ASC),
                        4
                    ) as net_change,
                    ROUND(
                        (LAST(odds_decimal ORDER BY bookmaker_last_update ASC) -
                         FIRST(odds_decimal ORDER BY bookmaker_last_update ASC)) /
                        FIRST(odds_decimal ORDER BY bookmaker_last_update ASC) * 100,
                        2
                    ) as pct_change,
                    MIN(bookmaker_last_update) as first_update,
                    MAX(bookmaker_last_update) as last_update,
                    COUNT(DISTINCT bookmaker_last_update) as unique_updates
                FROM movement
                GROUP BY event_id, home_team, away_team, bookmaker, market, outcome, point
            )
            SELECT * FROM grouped
            WHERE num_snapshots >= 2
            ORDER BY ABS(pct_change) DESC
        ) TO '{summary_file}' (FORMAT PARQUET)
    """)

    con.close()

    print(f"Line movement written to: {output_file}")
    print(f"Movement summary written to: {summary_file}")
    return output_file


if __name__ == "__main__":
    compute_line_movement()
