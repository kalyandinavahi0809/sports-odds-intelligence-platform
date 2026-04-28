# Sports Odds Intelligence Platform

A real-time sports odds intelligence platform for detecting arbitrage opportunities and positive expected value (+EV) bets using The Odds API free tier.

## Architecture

- **Ingestion**: Python async client polling The Odds API
- **Storage**: Local JSONL (raw) + Parquet (processed)
- **Analytics**: DuckDB SQL engine
- **Dashboard**: Streamlit Community Cloud
- **Automation**: GitHub Actions (scheduled)

## Quick Start

```bash
# 1. Install dependencies
make install

# 2. Copy and fill in your API key
cp .env.example .env

# 3. Run local ingestion
make ingest

# 4. Run normalization + analytics
make process

# 5. Start dashboard
make dashboard
```

## Repo Structure

```
├── .github/workflows/    # GitHub Actions (scheduled ingestion)
├── src/                  # Python source code
├── data/                 # Raw JSONL + processed Parquet
├── sql/                  # DuckDB SQL scripts
├── tests/                # Unit tests
├── Makefile              # Common commands
└── requirements.txt      # Python dependencies
```

## License

MIT
