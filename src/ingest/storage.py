"""Raw data storage utilities."""

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import RAW_DIR


def build_snapshot_path(sport: str, timestamp: datetime) -> Path:
    """Build the dated file path: data/raw/YYYY/MM/DD/{sport}_odds_<timestamp>.jsonl"""
    date_dir = RAW_DIR / f"{timestamp.year:04d}" / f"{timestamp.month:02d}" / f"{timestamp.day:02d}"
    date_dir.mkdir(parents=True, exist_ok=True)
    ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
    return date_dir / f"{sport}_odds_{ts_str}.jsonl"


def write_raw_snapshot(
    sport: str,
    events: list[dict],
    request_url_without_key: str,
    fetched_at: datetime | None = None,
) -> Path:
    """Write each API event as a JSONL line wrapped with metadata.

    Args:
        sport: Sport key (e.g., basketball_nba).
        events: List of raw event dicts from The Odds API.
        request_url_without_key: Request URL with API key redacted.
        fetched_at: UTC timestamp of the fetch. Defaults to now.

    Returns:
        Path to the written JSONL file.
    """
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc)

    snapshot_path = build_snapshot_path(sport, fetched_at)

    with open(snapshot_path, "w", encoding="utf-8") as f:
        for event in events:
            record = {
                "fetched_at_utc": fetched_at.isoformat(),
                "source": "the-odds-api",
                "sport": sport,
                "request_url_without_api_key": request_url_without_key,
                "event": event,
            }
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    return snapshot_path
