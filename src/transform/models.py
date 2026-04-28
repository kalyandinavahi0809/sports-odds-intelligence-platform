"""Canonical data models for normalized odds."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal

MarketType = Literal["h2h", "spreads", "totals"]


class NormalizedOdds(BaseModel):
    """One row per (event, bookmaker, market, outcome, timestamp) snapshot.

    Time-series preservation is intentional — do NOT overwrite.
    Each row captures a distinct market state at a point in time.
    """

    # ── Event Identity ──
    event_id: str
    sport: str
    league: str | None
    home_team: str
    away_team: str
    commence_time: datetime = Field(description="When the game starts (UTC)")

    # ── Market Identity ──
    bookmaker: str = Field(description="Bookmaker slug, e.g. draftkings")
    market: MarketType = Field(description="h2h | spreads | totals")
    outcome: str = Field(description="Team name or Over/Under")

    # ── Odds & Derived Metrics ──
    odds_decimal: float = Field(gt=0, description="Decimal odds from API")
    odds_american: int = Field(description="American odds derived from decimal")
    implied_probability: float = Field(ge=0, le=1, description="1 / odds_decimal")
    point: float | None = Field(description="Spread/total line; null for h2h")

    # ── Three Time Dimensions ──
    bookmaker_last_update: datetime = Field(description="When book posted this line (UTC)")
    ingested_at_utc: datetime = Field(description="When our pipeline recorded it (UTC)")

    # ── Game State ──
    is_live: bool = Field(description="commence_time < ingested_at_utc")
