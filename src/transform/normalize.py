"""Normalization: raw JSONL → canonical partitioned Parquet."""

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from src.config import RAW_DIR, PROCESSED_DIR
from src.transform.models import MarketType


# ── Constants ──────────────────────────────────────────────
DEDUP_KEY = [
    "event_id",
    "bookmaker",
    "market",
    "outcome",
    "point",
    "bookmaker_last_update",
    "odds_decimal",
]

# Market types vary by sport (e.g., tennis only has h2h, soccer has h2h+totals)
# Accept any market type the API returns — no hardcoded filter.
VALID_MARKETS = None  # disabled: accept all


# ── Odds Conversion ────────────────────────────────────────
def decimal_to_american(decimal: float) -> int:
    """Convert decimal odds to American format.

    Examples:
        1.28 → -357
        3.6  → +260
    """
    if decimal >= 2.0:
        return round((decimal - 1) * 100)
    else:
        return round(-100 / (decimal - 1))


# ── Date Parsing Helpers ───────────────────────────────────
def parse_iso(ts: str | None) -> datetime:
    """Parse ISO-8601 timestamp, return UTC-aware datetime."""
    if not ts:
        return datetime.now(timezone.utc)
    # Handle 'Z' suffix
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


# ── Flattening Logic ───────────────────────────────────────
def flatten_raw_record(record: dict) -> list[dict]:
    """Flatten one JSONL record into multiple normalized rows.

    Each row = one (event, bookmaker, market, outcome) snapshot.
    """
    rows: list[dict] = []

    meta = record
    event = meta.get("event", {})
    fetched_at = parse_iso(meta.get("fetched_at_utc"))

    # Event-level fields
    event_id = event.get("id", "")
    sport = event.get("sport_key", meta.get("sport", ""))
    league = event.get("sport_title", None)
    home_team = event.get("home_team", "")
    away_team = event.get("away_team", "")
    commence_time = parse_iso(event.get("commence_time"))
    is_live = commence_time < fetched_at

    for bookmaker in event.get("bookmakers", []):
        bm_key = bookmaker.get("key", "")
        if not bm_key:
            continue

        for market in bookmaker.get("markets", []):
            market_key = market.get("key", "")
            if not market_key:
                continue

            # Skip unsupported markets silently (API may return markets not requested)
            if VALID_MARKETS is not None and market_key not in VALID_MARKETS:
                continue

            # Market timestamp: prefer bookmaker's market update, fallback
            bm_last_update = parse_iso(
                market.get("last_update") or bookmaker.get("last_update")
            )

            for outcome in market.get("outcomes", []):
                price = outcome.get("price")
                if price is None or price <= 0:
                    continue

                odds_decimal = float(price)
                odds_american = decimal_to_american(odds_decimal)
                implied_prob = 1.0 / odds_decimal

                # point is present for spreads/totals, None for h2h
                point = outcome.get("point")
                if point is not None:
                    point = float(point)

                row = {
                    "event_id": event_id,
                    "sport": sport,
                    "league": league,
                    "home_team": home_team,
                    "away_team": away_team,
                    "commence_time": commence_time,
                    "bookmaker": bm_key,
                    "market": market_key,
                    "outcome": outcome.get("name", ""),
                    "odds_decimal": odds_decimal,
                    "odds_american": odds_american,
                    "implied_probability": implied_prob,
                    "point": point,
                    "bookmaker_last_update": bm_last_update,
                    "ingested_at_utc": fetched_at,
                    "is_live": is_live,
                }
                rows.append(row)

    return rows


# ── File Discovery ─────────────────────────────────────────
def discover_raw_files(raw_dir: Path = RAW_DIR) -> list[Path]:
    """Recursively find all .jsonl files under raw_dir."""
    return sorted(raw_dir.rglob("*.jsonl"))


# ── Partition Writing ──────────────────────────────────────
def write_partitioned_parquet(df: pl.DataFrame, base_dir: Path = PROCESSED_DIR) -> list[Path]:
    """Write DataFrame as Hive-partitioned Parquet: date=YYYY-MM-DD/sport=X/odds.parquet.

    Returns list of written file paths.
    """
    if df.is_empty():
        return []

    written: list[Path] = []

    # Add partition columns as strings for Hive-style partitioning
    df = df.with_columns([
        pl.col("ingested_at_utc").dt.date().cast(pl.Utf8).alias("date"),
        pl.col("sport").cast(pl.Utf8).alias("sport"),
    ])

    # Group by partition columns
    groups = df.group_by(["date", "sport"])
    for keys, group in groups:
        date_val, sport_val = keys[0], keys[1]
        partition_dir = base_dir / f"date={date_val}" / f"sport={sport_val}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        out_path = partition_dir / "odds.parquet"

        # Drop partition columns before writing (they're in the path)
        group_to_write = group.drop(["date", "sport"])

        # If file exists, read + concat + dedup, then rewrite
        if out_path.exists():
            existing = pl.read_parquet(out_path)
            combined = pl.concat([existing, group_to_write])
            combined = combined.unique(subset=DEDUP_KEY, keep="first")
            combined.write_parquet(out_path)
        else:
            group_to_write = group_to_write.unique(subset=DEDUP_KEY, keep="first")
            group_to_write.write_parquet(out_path)

        written.append(out_path)

    return written


# ── Main Entrypoint ────────────────────────────────────────
def normalize_all() -> tuple[list[Path], int]:
    """Read all raw JSONL, flatten, dedup, write partitioned Parquet.

    Returns: (list of written parquet paths, total rows written)
    """
    raw_files = discover_raw_files()
    print(f"Found {len(raw_files)} raw JSONL file(s)")

    all_rows: list[dict] = []
    for fp in raw_files:
        print(f"  Processing: {fp}")
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    rows = flatten_raw_record(record)
                    all_rows.extend(rows)
                except json.JSONDecodeError as exc:
                    print(f"    JSON decode error: {exc}")
                except Exception as exc:
                    print(f"    Unexpected error: {exc}")

    print(f"Total flattened rows: {len(all_rows)}")

    if not all_rows:
        return [], 0

    df = pl.DataFrame(all_rows)

    # Schema alignment
    df = df.with_columns([
        pl.col("commence_time").cast(pl.Datetime(time_unit="us", time_zone="UTC")),
        pl.col("bookmaker_last_update").cast(pl.Datetime(time_unit="us", time_zone="UTC")),
        pl.col("ingested_at_utc").cast(pl.Datetime(time_unit="us", time_zone="UTC")),
        pl.col("point").cast(pl.Float64),
    ])

    written_paths = write_partitioned_parquet(df)
    total_rows = len(df)

    for p in written_paths:
        print(f"  Wrote Parquet: {p}")

    return written_paths, total_rows


if __name__ == "__main__":
    paths, rows = normalize_all()
    print(f"\nDone. {rows} rows written to {len(paths)} partition(s).")
