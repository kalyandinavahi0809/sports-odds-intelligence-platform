# 🏀 Sports Odds Intelligence Platform

A **production-grade, 100% free** real-time sports odds intelligence platform for detecting **arbitrage opportunities** and **positive expected value (+EV) bets**.

Built with Python, DuckDB, Polars, and Streamlit. Deploys to Streamlit Community Cloud at zero cost.

---

## 🚀 Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/kalyandinavahi0809/sports-odds-intelligence-platform.git
cd sports-odds-intelligence-platform

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy environment file and add your API key
cp .env.example .env
# Edit .env: add your ODDS_API_KEY from https://the-odds-api.com/

# 4. Fetch odds + run analytics + start dashboard
make ingest
make normalize
make analytics
make dashboard
```

The dashboard opens at `http://localhost:8501`.

---

## 📋 Prerequisites

| Requirement | How to get it |
|-------------|--------------|
| Python 3.11+ | `python3 --version` |
| The Odds API key | [Free tier](https://the-odds-api.com/) — 500 requests/month |
| Git | `git --version` |

---

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  The Odds API   │────▶│  Ingestion      │────▶│  Raw JSONL      │
│  (Free Tier)    │     │  (Python/httpx) │     │  data/raw/      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Streamlit      │◀────│  DuckDB         │◀────│  Parquet        │
│  Dashboard      │     │  Analytics      │     │  data/processed/│
│  (Community     │     │  (SQL)          │     │                 │
│   Cloud)        │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                                               │
        │         ┌─────────────────┐                  │
        └─────────│  +EV Signals    │◀─────────────────┘
                  │  data/analytics/│
                  └─────────────────┘
```

---

## 🔧 Makefile Commands

| Command | What it does |
|---------|-------------|
| `make install` | Install Python dependencies |
| `make ingest` | Fetch odds from The Odds API |
| `make normalize` | Convert JSONL → partitioned Parquet |
| `make analytics` | Run arbitrage + +EV detection |
| `make dashboard` | Start Streamlit dashboard |
| `make process` | Run normalize + analytics together |
| `make test` | Run pytest suite |
| `make clean` | Remove Python cache files |

---

## 📊 Dashboard Features

### +EV Bets Table
- Event, bookmaker, outcome, odds, EV%, confidence (number of bookmakers)
- Filter by EV threshold, bookmaker, market
- Bar chart of EV distribution

### Arbitrage Opportunities
- Event, market, profit %, best odds per outcome, stake allocation
- Outcome pairing validation (Over/Under, Team A/Team B)
- Only shows valid 2-outcome markets

### Market Overview
- Best odds per outcome across all bookmakers
- Bookmaker coverage chart
- Market distribution chart

---

## ⚙️ Configuration

Edit `.env`:

```bash
# Required
ODDS_API_KEY=your_api_key_here

# Optional
SPORTS=basketball_nba                    # comma-separated
EV_THRESHOLD=0.02                        # +2% minimum EV
FRESHNESS_MINUTES=5                    # max data age
STRICT_FRESHNESS=true                  # true=production, false=demo
```

| Mode | Behavior |
|------|----------|
| `STRICT_FRESHNESS=true` | Only shows data <5 min old. Empty state = "No fresh opportunities" |
| `STRICT_FRESHNESS=false` | Shows all historical data. Good for portfolio demos. |

---

## 🗂️ Project Structure

```
sports-odds-intelligence-platform/
├── .github/workflows/        # GitHub Actions automation
│   ├── ingest.yml            # Fetch every 6 hours
│   └── process.yml           # Normalize + analytics
├── src/
│   ├── ingest/               # API client + JSONL storage
│   ├── transform/            # Normalization + Parquet
│   ├── analytics/            # Arbitrage + +EV (DuckDB)
│   └── dashboard/            # Streamlit app
├── data/
│   ├── raw/                  # JSONL snapshots (gitignored)
│   ├── processed/            # Hive-partitioned Parquet
│   └── analytics/            # Signal Parquet
├── sql/                      # Standalone DuckDB queries
├── tests/                    # pytest suite
├── .env.example              # Template for secrets
├── Makefile                  # All common commands
└── requirements.txt          # Python dependencies
```

---

## 🔒 Security

- `.env` is **gitignored** — never committed
- API keys are read via `os.getenv()` only
- `.env.example` contains placeholders
- GitHub Actions uses `secrets.ODDS_API_KEY`
- Raw data stores URLs with `REDACTED` API keys

---

## 📈 Data Model

### Canonical Schema (one row = one odds snapshot)

| Field | Description |
|-------|-------------|
| `event_id` | Unique game identifier |
| `sport` | e.g. `basketball_nba` |
| `home_team` / `away_team` | Team names |
| `commence_time` | Game start (UTC) |
| `bookmaker` | e.g. `draftkings` |
| `market` | `h2h`, `spreads`, `totals` |
| `outcome` | Team name or Over/Under |
| `odds_decimal` | Decimal odds |
| `odds_american` | American odds |
| `implied_probability` | `1 / odds_decimal` |
| `point` | Spread/total line (null for h2h) |
| `bookmaker_last_update` | When book posted this line |
| `ingested_at_utc` | When pipeline recorded it |
| `is_live` | `true` if game has started |

### Three Time Dimensions
- `commence_time` — game start
- `bookmaker_last_update` — book's line timestamp
- `ingested_at_utc` — pipeline timestamp

---

## 🧮 Analytics

### Arbitrage Detection
```
For each (event, market, point):
  best_odds_per_outcome = max(odds) across all bookmakers
  margin = Σ(1 / best_odds)
  if margin < 1.0 and ≥2 bookmakers:
    arbitrage exists
    profit_pct = (1/margin - 1) × 100
```

### +EV Detection
```
For each bookmaker:
  no_vig_prob = implied_prob / vig

For each outcome:
  weighted_consensus = weighted average of no_vig_probs
                         (excludes current bookmaker)
  EV = (true_prob × odds_decimal) - 1
  if EV > 2% and odds > 1.5 and prob in [0.1, 0.9]:
    +EV signal
```

**Bookmaker weights:** sharp=1.5, mid=1.0, recreational=0.7

---

## 🚀 Deployment

### Streamlit Community Cloud (Free)

1. Push to GitHub (this repo)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect GitHub repo
4. App deploys automatically

### GitHub Actions (Automated Ingestion)

1. Add `ODDS_API_KEY` to GitHub Secrets
2. Workflows run every 6 hours automatically
3. Raw JSONL + processed Parquet committed back to repo

---

## 🧪 Testing

```bash
make test
```

Tests cover:
- Odds conversion (decimal ↔ American)
- Flattening logic (raw → normalized)
- URL construction (API key redaction)
- Live game detection
- Invalid odds filtering

---

## 📦 Tech Stack

| Layer | Tool | Cost |
|-------|------|------|
| Language | Python 3.11+ | Free |
| Ingestion | `httpx` (async) | Free |
| Processing | `polars` + `pyarrow` | Free |
| Analytics | `duckdb` (embedded) | Free |
| Dashboard | `streamlit` | Free |
| Storage | JSONL + Parquet (local) | Free |
| CI/CD | GitHub Actions | Free (public repo) |
| Hosting | Streamlit Community Cloud | Free |

---

## 📚 What is +EV Betting?

**Expected Value (EV)** tells you whether a bet is profitable long-term:

- **+EV (>0%)** — You have an edge. Bet it.
- **0%** — Fair price. No edge.
- **-EV (<0%)** — House has an edge. Skip it.

This platform finds **+EV opportunities** by comparing a bookmaker's odds against the market's consensus fair probability — derived from sharp bookmakers' no-vig lines.

---

## 📚 What is Arbitrage?

**Arbitrage** exists when you can bet on all outcomes of an event across different bookmakers and guarantee a profit:

```
If Σ(1 / best_odds) < 1.0:
  You can distribute stakes proportionally
  Profit = (1/margin - 1) × 100
```

Rare in practice because bookmakers maintain ~2% vig, but the platform scans continuously.

---

## 📝 License

MIT

---

## 🙋 Support

Open an issue on GitHub or reach out via the repo's discussions.
