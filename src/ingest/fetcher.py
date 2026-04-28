"""Odds data ingestion from The Odds API."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.config import ODDS_API_KEY, ODDS_API_BASE, SPORTS
from src.ingest.storage import write_raw_snapshot


DEFAULT_MARKETS = "h2h,spreads,totals"
DEFAULT_REGIONS = "us"
DEFAULT_ODDS_FORMAT = "decimal"
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 3


def build_request_url(sport_key: str, api_key: str) -> str:
    """Build the full request URL for a sport."""
    return (
        f"{ODDS_API_BASE}/sports/{sport_key}/odds"
        f"?apiKey={api_key}"
        f"&regions={DEFAULT_REGIONS}"
        f"&markets={DEFAULT_MARKETS}"
        f"&oddsFormat={DEFAULT_ODDS_FORMAT}"
    )


def build_safe_request_url(sport_key: str) -> str:
    """Build the request URL with the API key redacted (for logging/storage)."""
    return (
        f"{ODDS_API_BASE}/sports/{sport_key}/odds"
        f"?apiKey=REDACTED"
        f"&regions={DEFAULT_REGIONS}"
        f"&markets={DEFAULT_MARKETS}"
        f"&oddsFormat={DEFAULT_ODDS_FORMAT}"
    )


async def fetch_sport(
    client: httpx.AsyncClient,
    sport_key: str,
    api_key: str,
) -> tuple[list[dict], str]:
    """Fetch odds for a single sport with retries.

    Returns:
        (events_list, safe_request_url)
    """
    if not api_key or api_key == "your_api_key_here":
        raise ValueError(
            "ODDS_API_KEY is missing or unset. "
            "Copy .env.example to .env and add your key."
        )

    url = build_request_url(sport_key, api_key)
    safe_url = build_safe_request_url(sport_key)
    fetched_at = datetime.now(timezone.utc)

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = await client.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            events = response.json()

            if not isinstance(events, list):
                raise ValueError(
                    f"Unexpected API response for {sport_key}: expected list, got {type(events).__name__}"
                )

            print(f"[{fetched_at.isoformat()}] Fetched {len(events)} events for {sport_key}")
            return events, safe_url

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            body = exc.response.text[:200]
            last_error = exc
            print(
                f"HTTP {status} for {sport_key} (attempt {attempt}/{MAX_RETRIES}): {body}"
            )
            if status == 401:
                raise ValueError(
                    f"Authentication failed for {sport_key}. Check your ODDS_API_KEY."
                ) from exc
            if status == 429:
                raise RuntimeError(
                    f"Rate limit hit for {sport_key}. "
                    "The Odds API free tier may have expired or quota exhausted."
                ) from exc
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)

        except httpx.RequestError as exc:
            last_error = exc
            print(
                f"Network error for {sport_key} (attempt {attempt}/{MAX_RETRIES}): {exc}"
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)

    raise RuntimeError(
        f"Failed to fetch {sport_key} after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    ) from last_error


async def fetch_all() -> list[Path]:
    """Fetch odds for all configured sports and write raw JSONL snapshots.

    Returns:
        List of written snapshot file paths.
    """
    api_key = ODDS_API_KEY
    if not api_key:
        raise ValueError("ODDS_API_KEY not found in environment.")

    written_paths: list[Path] = []
    async with httpx.AsyncClient(http2=True) as client:
        for sport_key in SPORTS:
            try:
                events, safe_url = await fetch_sport(client, sport_key, api_key)
                snapshot_path = write_raw_snapshot(
                    sport=sport_key,
                    events=events,
                    request_url_without_key=safe_url,
                )
                written_paths.append(snapshot_path)
            except Exception as exc:
                print(f"ERROR: Ingestion failed for {sport_key}: {exc}")
                raise

    return written_paths


if __name__ == "__main__":
    paths = asyncio.run(fetch_all())
    for p in paths:
        print(f"Snapshot saved: {p}")
