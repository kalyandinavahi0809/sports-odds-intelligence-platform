"""Tests for normalize.py and odds conversion."""

from src.transform.normalize import decimal_to_american, flatten_raw_record


def test_decimal_to_american_favorite():
    """Decimal < 2.0 → negative American odds."""
    assert decimal_to_american(1.28) == -357
    assert decimal_to_american(1.50) == -200
    assert decimal_to_american(1.91) == -110


def test_decimal_to_american_underdog():
    """Decimal >= 2.0 → positive American odds."""
    assert decimal_to_american(2.00) == 100
    assert decimal_to_american(3.60) == 260
    assert decimal_to_american(5.00) == 400


def test_flatten_raw_record_structure():
    """End-to-end: raw JSONL record → flattened normalized rows."""
    raw = {
        "fetched_at_utc": "2026-04-28T00:58:35+00:00",
        "source": "the-odds-api",
        "sport": "basketball_nba",
        "request_url_without_api_key": "https://...",
        "event": {
            "id": "test-event-123",
            "sport_key": "basketball_nba",
            "sport_title": "NBA",
            "commence_time": "2026-04-28T02:00:00Z",
            "home_team": "Lakers",
            "away_team": "Warriors",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "last_update": "2026-04-28T00:55:00Z",
                    "markets": [
                        {
                            "key": "h2h",
                            "last_update": "2026-04-28T00:55:00Z",
                            "outcomes": [
                                {"name": "Lakers", "price": 1.80},
                                {"name": "Warriors", "price": 2.10},
                            ],
                        },
                        {
                            "key": "spreads",
                            "last_update": "2026-04-28T00:55:00Z",
                            "outcomes": [
                                {"name": "Lakers", "price": 1.91, "point": -5.5},
                                {"name": "Warriors", "price": 1.91, "point": 5.5},
                            ],
                        },
                        {
                            "key": "totals",
                            "last_update": "2026-04-28T00:55:00Z",
                            "outcomes": [
                                {"name": "Over", "price": 1.87, "point": 220.5},
                                {"name": "Under", "price": 1.87, "point": 220.5},
                            ],
                        },
                    ],
                }
            ],
        },
    }

    rows = flatten_raw_record(raw)

    # 1 bookmaker × 3 markets × 2 outcomes = 6 rows
    assert len(rows) == 6

    # Check h2h row
    h2h_rows = [r for r in rows if r["market"] == "h2h"]
    assert len(h2h_rows) == 2
    assert h2h_rows[0]["point"] is None

    # Check spreads row
    spread_rows = [r for r in rows if r["market"] == "spreads"]
    assert len(spread_rows) == 2
    assert spread_rows[0]["point"] == -5.5
    assert spread_rows[1]["point"] == 5.5

    # Check totals row
    total_rows = [r for r in rows if r["market"] == "totals"]
    assert len(total_rows) == 2
    assert total_rows[0]["point"] == 220.5

    # Check derived fields
    lakers_row = [r for r in rows if r["outcome"] == "Lakers" and r["market"] == "h2h"][0]
    assert lakers_row["odds_decimal"] == 1.80
    assert lakers_row["odds_american"] == -125  # (1.8-1)*100
    assert round(lakers_row["implied_probability"], 4) == round(1 / 1.80, 4)
    assert lakers_row["is_live"] is False  # commence_time > ingested_at_utc

    # Check all rows have the three time dimensions
    for r in rows:
        assert "bookmaker_last_update" in r
        assert "ingested_at_utc" in r
        assert "commence_time" in r


def test_flatten_live_game():
    """Game already started → is_live=True."""
    raw = {
        "fetched_at_utc": "2026-04-28T02:30:00+00:00",
        "event": {
            "id": "live-event",
            "sport_key": "basketball_nba",
            "commence_time": "2026-04-28T02:00:00Z",
            "home_team": "A",
            "away_team": "B",
            "bookmakers": [
                {
                    "key": "dk",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [{"name": "A", "price": 2.0}],
                        }
                    ],
                }
            ],
        },
    }

    rows = flatten_raw_record(raw)
    assert len(rows) == 1
    assert rows[0]["is_live"] is True


def test_flatten_skips_invalid_odds():
    """Zero or negative odds should be skipped."""
    raw = {
        "fetched_at_utc": "2026-04-28T00:00:00+00:00",
        "event": {
            "id": "bad-odds",
            "sport_key": "basketball_nba",
            "commence_time": "2026-04-28T02:00:00Z",
            "home_team": "A",
            "away_team": "B",
            "bookmakers": [
                {
                    "key": "dk",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "A", "price": 0.0},
                                {"name": "B", "price": -1.5},
                                {"name": "C", "price": 2.0},
                            ],
                        }
                    ],
                }
            ],
        },
    }

    rows = flatten_raw_record(raw)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "C"
