# 🏆 Real-Time Multi-Sport Odds Market Intelligence Platform

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://streamlit.io/"><img src="https://img.shields.io/badge/streamlit-1.30+-FF4B4B.svg?style=flat-square&logo=streamlit&logoColor=white" alt="Streamlit"></a>
  <a href="https://duckdb.org/"><img src="https://img.shields.io/badge/duckdb-0.10+-yellow.svg?style=flat-square&logo=duckdb&logoColor=black" alt="DuckDB"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg?style=flat-square" alt="License"></a>
  <a href="https://github.com/kalyandinavahi0809/sports-odds-intelligence-platform/commits/main"><img src="https://img.shields.io/github/last-commit/kalyandinavahi0809/sports-odds-intelligence-platform?style=flat-square" alt="Last Commit"></a>
  <a href="https://github.com/kalyandinavahi0809/sports-odds-intelligence-platform/stargazers"><img src="https://img.shields.io/github/stars/kalyandinavahi0809/sports-odds-intelligence-platform?style=flat-square&color=yellow" alt="Stars"></a>
</p>

<p align="center">
  <b>Multi-sport odds intelligence for arbitrage, +EV betting, and line movement analytics</b>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-features">Features</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-deployment">Deploy</a> •
  <a href="#-analytics">Analytics</a>
</p>

---

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/kalyandinavahi0809/sports-odds-intelligence-platform.git
cd sports-odds-intelligence-platform

# 2. Install
pip install -r requirements.txt

# 3. Get API key (free tier)
# → https://the-odds-api.com/
cp .env.example .env
# Edit .env: ODDS_API_KEY=your_key_here

# 4. Run full pipeline
make ingest && make normalize && make analytics && make dashboard
```

**Dashboard opens at** `http://localhost:8501`

---

## 📸 Dashboard Preview

### Live Snapshot Banner
Real-time freshness indicator with color-coded status:
- 🟢 Green (< 5 min): Live data
- 🟡 Yellow (5–15 min): Slightly stale
- 🔴 Red (> 15 min): Stale — refresh needed

### +EV Bets (Positive Expected Value)
Identifies bets where the market price exceeds fair probability:

```
Event: Spurs vs Trail Blazers
Bookmaker: betrivers
Outcome: Portland Trail Blazers
Odds: 6.10 (+510)
True Probability: 16.84%
EV: +2.70%
Confidence: 8 bookmakers
```

### Line Movement Intelligence
Track odds changes across snapshots:
- Odds movement line charts by bookmaker
- Biggest positive/negative movers
- Implied probability shifts
- Market volatility heatmap

### Arbitrage Scanner
Detects risk-free opportunities across bookmakers:

```
Condition: SUM(1 / best_odds) < 1.0
Profit: (1/margin - 1) × 100%
```

### Market Overview
- Best odds per outcome across all bookmakers
- Bookmaker coverage analysis
- Real-time market distribution

---

## 🎯 Features

| Feature | Description |
|---------|-------------|
| **Real-time Ingestion** | Polls The Odds API every 5s with async HTTP/2 |
| **Time-Series Storage** | Hive-partitioned Parquet: `date=YYYY-MM-DD/sport=X/` |
| **3D Time Tracking** | `commence_time` × `bookmaker_last_update` × `ingested_at_utc` |
| **Weighted Consensus** | Sharp books (lowvig) weighted 1.5×, recreational 0.7× |
| **Leave-One-Out EV** | Bookmaker excluded from its own consensus |
| **Freshness Filter** | `STRICT_FRESHNESS=true` for production, `false` for demo |
| **DuckDB Analytics** | Embedded SQL engine, zero external DB |
| **Streamlit Dashboard** | Filters, charts, dark mode support |
| **GitHub Actions** | Scheduled ingestion every 6 hours |
| **100% Free** | No paid cloud, no database, no infrastructure |

### Supported Sports

Configure via `SPORTS` env variable (comma-separated):

| Sport | Key | Markets | Status |
|-------|-----|---------|--------|
| NBA | `basketball_nba` | h2h, spreads, totals | ✅ Active |
| NFL | `americanfootball_nfl` | h2h, spreads, totals | ✅ Ready |
| MLB | `baseball_mlb` | h2h, spreads, totals | ✅ Ready |
| NHL | `icehockey_nhl` | h2h, spreads, totals | ✅ Ready |
| EPL | `soccer_epl` | h2h, totals | ✅ Ready |
| Champions League | `soccer_uefa_champs_league` | h2h, totals | ✅ Ready |
| ATP Tennis | `tennis_atp` | h2h | ✅ Ready |
| MMA | `mma_mixed_martial_arts` | h2h | ✅ Ready |

**Free tier recommendation:** Start with 3 sports to stay within API quota.

---

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  The Odds API   │────▶│  Python Async   │────▶│  Raw JSONL      │
│  (Free Tier)    │     │  httpx Client   │     │  data/raw/      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Streamlit      │◀────│  DuckDB SQL     │◀────│  Parquet        │
│  Dashboard      │     │  Analytics      │     │  data/processed/│
│  (Community     │     │                 │     │                 │
│   Cloud)        │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                                               │
        │         ┌─────────────────┐                  │
        └─────────│  +EV Signals    │◀─────────────────┘
                  │  data/analytics/│
                  └─────────────────┘
```

**Tech Stack:** Python 3.11 · Polars · DuckDB · Streamlit · httpx · Pydantic

---

## 🔧 Makefile Commands

| Command | What It Does |
|---------|-------------|
| `make install` | Install Python dependencies |
| `make ingest` | Fetch odds from The Odds API |
| `make normalize` | JSONL → Hive-partitioned Parquet |
| `make analytics` | Run arbitrage + +EV detection (DuckDB) |
| `make dashboard` | Start Streamlit at `localhost:8501` |
| `make process` | Run normalize + analytics together |
| `make test` | Run pytest suite |
| `make clean` | Remove Python cache |

---

## 📊 Analytics

### Arbitrage Detection

For each `(event, market, point)`:

```
best_odds = MAX(odds) per outcome across all bookmakers
margin = Σ(1 / best_odds)

if margin < 1.0 and ≥2 bookmakers:
    arbitrage exists
    profit_pct = (1/margin - 1) × 100
    stake_i = (1/best_odds_i) / margin × total_stake
```

### +EV Detection

For each bookmaker and outcome:

```
no_vig_prob = implied_prob / vig
weighted_consensus = weighted_avg(no_vig_probs, excl_current_book)

EV = (true_prob × odds_decimal) - 1
if EV > 2% and odds > 1.5 and prob in [0.1, 0.9]:
    +EV signal
```

**Bookmaker Tiers:**
| Tier | Books | Weight |
|------|-------|--------|
| Sharp | lowvig, betonlineag | 1.5 |
| Mid | draftkings, fanduel | 1.0 |
| Recreational | betmgm, bovada, betrivers, mybookieag, betus | 0.7 |

---

## ⚙️ Configuration

Edit `.env`:

```bash
# Required
ODDS_API_KEY=your_api_key_here        # Get at https://the-odds-api.com/

# Analytics
EV_THRESHOLD=0.02                     # Minimum +2% EV
FRESHNESS_MINUTES=5                   # Max data age in minutes
STRICT_FRESHNESS=true                 # true=production, false=demo
```

| Mode | Behavior |
|------|----------|
| `STRICT_FRESHNESS=true` | Only data <5 min old. Empty = "No fresh opportunities" |
| `STRICT_FRESHNESS=false` | Shows all historical data. Good for demos/portfolio |

---

## 🚀 Deployment

### Streamlit Community Cloud (Free)

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Connect GitHub repo
3. Set `src/dashboard/app.py` as entry point
4. Add `ODDS_API_KEY` and `STRICT_FRESHNESS=false` to Streamlit Secrets
5. Deploy → get live URL

### GitHub Actions (Automated)

1. Add `ODDS_API_KEY` to GitHub Secrets
2. Workflows auto-run every 6 hours
3. Commits raw + processed data back to repo

---

## 🗂️ Project Structure

```
sports-odds-intelligence-platform/
├── .github/workflows/
│   ├── ingest.yml              # Scheduled: fetch + commit raw JSONL
│   └── process.yml             # Normalization + analytics
├── src/
│   ├── ingest/
│   │   ├── fetcher.py          # Async HTTP client (httpx)
│   │   └── storage.py          # JSONL append writer
│   ├── transform/
│   │   ├── normalize.py        # Flatten → Parquet (Polars)
│   │   └── models.py           # Pydantic canonical schema
│   ├── analytics/
│   │   ├── arbitrage.py        # DuckDB arb detection
│   │   └── plus_ev.py          # DuckDB +EV detection
│   └── dashboard/
│       └── app.py              # Streamlit app
├── data/
│   ├── raw/                    # JSONL snapshots (gitignored)
│   ├── processed/              # Hive-partitioned Parquet
│   └── analytics/              # Signal Parquet
├── sql/
│   ├── setup_views.sql         # DuckDB view definitions
│   └── arb_scan.sql            # Standalone arb query
├── tests/
│   ├── test_fetcher.py         # URL + storage tests
│   ├── test_normalize.py       # Odds conversion + flattening
│   └── test_analytics.py       # Analytics tests
├── .env.example                # Template for secrets
├── Makefile                    # All common commands
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

---

## 🧪 Testing

```bash
make test
```

Tests cover:
- Decimal ↔ American odds conversion
- Raw JSONL → normalized row flattening
- API key redaction in URLs
- Live game detection
- Invalid odds filtering

---

## 🔒 Security

| Check | Status |
|-------|--------|
| `.env` in `.gitignore` | ✅ Never committed |
| API keys via `os.getenv()` | ✅ No hardcoding |
| `.env.example` template | ✅ Placeholder only |
| GitHub Actions secrets | ✅ `${{ secrets.ODDS_API_KEY }}` |
| Raw data redaction | ✅ `apiKey=REDACTED` in stored URLs |

---

## 📚 What is +EV?

**Expected Value** = `(true_probability × odds) − 1`

| EV | Meaning |
|----|---------|
| > 0% | **+EV** — you have an edge. Bet it. |
| ≈ 0% | Fair price. No edge. |
| < 0% | **-EV** — house edge. Skip. |

This platform finds +EV by comparing a book's odds against the **market consensus** — derived from sharp bookmakers' no-vig lines.

---

## 📚 What is Arbitrage?

Arbitrage exists when `Σ(1 / best_odds) < 1.0` across bookmakers.

You bet on **all outcomes** proportionally and **guarantee profit** regardless of result.

Rare in practice (bookmakers maintain ~2% vig), but the platform scans continuously.

---

## 📝 License

MIT

---

## 🙋 Support

Open an issue on GitHub or start a discussion.

**Built with 💚 by a Quant Infrastructure Engineer.**
