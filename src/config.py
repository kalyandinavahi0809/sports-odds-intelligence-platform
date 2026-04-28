"""Project configuration loaded from environment."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / os.getenv("DATA_DIR", "data")
RAW_DIR = PROJECT_ROOT / os.getenv("RAW_DIR", "data/raw")
PROCESSED_DIR = PROJECT_ROOT / os.getenv("PROCESSED_DIR", "data/processed")
ANALYTICS_DIR = PROJECT_ROOT / os.getenv("ANALYTICS_DIR", "data/analytics")

# API
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Sports (extensible)
SPORTS = [s.strip() for s in os.getenv("SPORTS", "basketball_nba").split(",") if s.strip()]

# Bookmakers
BOOKMAKERS = [b.strip() for b in os.getenv("BOOKMAKERS", "").split(",") if b.strip()]

# Analytics
EV_THRESHOLD = float(os.getenv("EV_THRESHOLD", "0.02"))
FRESHNESS_MINUTES = int(os.getenv("FRESHNESS_MINUTES", "5"))
STRICT_FRESHNESS = os.getenv("STRICT_FRESHNESS", "true").lower() == "true"
