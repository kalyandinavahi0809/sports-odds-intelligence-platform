"""Tests for fetcher.py."""

from src.ingest.fetcher import build_request_url, build_safe_request_url
from src.config import ODDS_API_BASE


def test_build_request_url():
    url = build_request_url("basketball_nba", "test_key_123")
    assert ODDS_API_BASE in url
    assert "basketball_nba" in url
    assert "test_key_123" in url
    assert "h2h,spreads,totals" in url
    assert "us" in url
    assert "decimal" in url


def test_build_safe_request_url():
    url = build_safe_request_url("basketball_nba")
    assert ODDS_API_BASE in url
    assert "basketball_nba" in url
    assert "REDACTED" in url
    assert "h2h,spreads,totals" in url
    assert "us" in url
    assert "decimal" in url
    assert "test_key" not in url  # no accidental key leak
