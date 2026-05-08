"""Streamlit dashboard for Sports Odds Intelligence Platform."""

import sys
from pathlib import Path

# Add project root to Python path so src.* imports work when streamlit runs this file
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import duckdb
import polars as pl
import streamlit as st

from src.config import ANALYTICS_DIR, PROCESSED_DIR, STRICT_FRESHNESS, EV_THRESHOLD

st.set_page_config(
    page_title="Sports Odds Intelligence",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Helpers ────────────────────────────────────────────────

def load_plus_ev() -> pl.DataFrame | None:
    """Load +EV bets from analytics Parquet."""
    try:
        df = duckdb.sql("""
            SELECT * FROM read_parquet('data/analytics/*/*/plus_ev.parquet', hive_partitioning=1)
        """).pl()
        return df if not df.is_empty() else None
    except Exception:
        return None


def load_arbitrage() -> pl.DataFrame | None:
    """Load arbitrage opportunities from analytics Parquet."""
    try:
        df = duckdb.sql("""
            SELECT * FROM read_parquet('data/analytics/*/*/arbitrage.parquet', hive_partitioning=1)
        """).pl()
        return df if not df.is_empty() else None
    except Exception:
        return None


def load_processed_odds() -> pl.DataFrame | None:
    """Load latest normalized odds for market overview."""
    try:
        query = """
        WITH latest AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY event_id, bookmaker, market, outcome, point
                    ORDER BY bookmaker_last_update DESC
                ) AS rn
            FROM read_parquet('data/processed/*/*/odds.parquet', hive_partitioning=1)
            WHERE is_live = false
        )
        SELECT * FROM latest WHERE rn = 1
        """
        return duckdb.sql(query).pl()
    except Exception:
        return None


def get_unique_values(df: pl.DataFrame, col: str) -> list[str]:
    """Return sorted unique values from a column."""
    if df is None or col not in df.columns:
        return []
    return sorted([str(x) for x in df[col].unique().to_list() if x is not None])


# ── Sidebar ────────────────────────────────────────────────

st.sidebar.title("⚙️ Filters")

mode_label = "Production (strict)" if STRICT_FRESHNESS else "Demo (allow stale)"
st.sidebar.caption(f"Mode: {mode_label}")

# EV threshold slider
threshold = st.sidebar.slider(
    "EV Threshold (%)",
    min_value=0.0,
    max_value=10.0,
    value=float(EV_THRESHOLD * 100),
    step=0.5,
    help="Minimum expected value to display.",
) / 100.0

# Load raw data first to build filter options
raw_odds = load_processed_odds()

# Bookmaker filter
all_bookmakers = get_unique_values(raw_odds, "bookmaker")
selected_bookmakers = st.sidebar.multiselect(
    "Bookmakers",
    options=all_bookmakers,
    default=all_bookmakers,
    help="Filter by bookmaker.",
)

# Market filter
all_markets = get_unique_values(raw_odds, "market")
selected_markets = st.sidebar.multiselect(
    "Markets",
    options=all_markets,
    default=all_markets,
    help="Filter by market type.",
)

# ── Main Content ──────────────────────────────────────────

st.title("🏀 Sports Odds Intelligence Platform")
st.markdown("Real-time odds, arbitrage, and +EV detection.")

# ── Section A: +EV Bets ───────────────────────────────────

st.header("📈 +EV Bets")

ev_df = load_plus_ev()

if ev_df is None:
    if STRICT_FRESHNESS:
        st.info("🔒 No fresh +EV opportunities found. Data is older than the freshness threshold. Run `make ingest` to fetch current odds, or switch to demo mode.")
    else:
        st.info("📭 No +EV opportunities found with current filters.")
else:
    # Apply filters
    if threshold > 0:
        ev_df = ev_df.filter(pl.col("ev") > threshold)
    if selected_bookmakers:
        ev_df = ev_df.filter(pl.col("bookmaker").is_in(selected_bookmakers))
    if selected_markets:
        ev_df = ev_df.filter(pl.col("market").is_in(selected_markets))

    if ev_df.is_empty():
        st.info("📭 No +EV bets match the selected filters.")
    else:
        st.metric("+EV Bets Found", ev_df.height)

        display_cols = [
            "home_team", "away_team", "bookmaker", "market", "outcome",
            "odds_decimal", "odds_american", "true_prob", "ev_pct", "num_bookmakers_used",
        ]
        display_df = ev_df.select([c for c in display_cols if c in ev_df.columns])

        st.dataframe(
            display_df.to_pandas(),
            width="stretch",
            hide_index=True,
            column_config={
                "ev_pct": st.column_config.NumberColumn("EV %", format="%.2f%%"),
                "true_prob": st.column_config.NumberColumn("True Prob", format="%.2f%%"),
                "odds_decimal": st.column_config.NumberColumn("Decimal", format="%.2f"),
            },
        )

        # Simple bar chart of EV % by bet
        chart_df = ev_df.select(["outcome", "bookmaker", "ev_pct"]).to_pandas()
        chart_df["label"] = chart_df["bookmaker"] + " — " + chart_df["outcome"]
        st.bar_chart(chart_df.set_index("label")["ev_pct"], width="stretch")

# ── Section B: Arbitrage ──────────────────────────────────

st.header("🔄 Arbitrage Opportunities")

arb_df = load_arbitrage()

if arb_df is None:
    if STRICT_FRESHNESS:
        st.info("🔒 No fresh arbitrage opportunities found. Data is older than the freshness threshold. Run `make ingest` to fetch current odds, or switch to demo mode.")
    else:
        st.info("📭 No arbitrage opportunities found.")
else:
    st.metric("Arbitrage Opportunities", arb_df.height)

    if arb_df.is_empty():
        st.info("📭 No arbitrage opportunities match the selected filters.")
    else:
        display_cols = [
            "home_team", "away_team", "market", "point", "margin",
            "profit_pct", "num_bookmakers", "leg_outcome", "leg_best_odds", "leg_best_bookmaker",
        ]
        display_df = arb_df.select([c for c in display_cols if c in arb_df.columns])
        st.dataframe(display_df.to_pandas(), width="stretch", hide_index=True)

# ── Section C: Market Overview ────────────────────────────

st.header("📊 Market Overview")

if raw_odds is None or raw_odds.is_empty():
    st.warning("No processed odds data found. Run `make normalize` first.")
else:
    # Filter processed odds by sidebar selections
    filtered = raw_odds
    if selected_bookmakers:
        filtered = filtered.filter(pl.col("bookmaker").is_in(selected_bookmakers))
    if selected_markets:
        filtered = filtered.filter(pl.col("market").is_in(selected_markets))

    if filtered.is_empty():
        st.info("📭 No odds match the selected filters.")
    else:
        st.metric("Active Odds", filtered.height)

        # Best odds per outcome
        best_odds_query = f"""
        SELECT
            event_id,
            home_team,
            away_team,
            market,
            outcome,
            point,
            MAX(odds_decimal) AS best_decimal,
            FIRST(bookmaker ORDER BY odds_decimal DESC) AS best_bookmaker
        FROM filtered
        GROUP BY event_id, home_team, away_team, market, outcome, point
        ORDER BY home_team, away_team, market, outcome
        """
        best_df = duckdb.sql(best_odds_query).pl()

        st.subheader("Best Odds per Outcome")
        st.dataframe(
            best_df.to_pandas(),
            width="stretch",
            hide_index=True,
            column_config={
                "best_decimal": st.column_config.NumberColumn("Best Odds", format="%.2f"),
            },
        )

        # Simple chart: bookmaker coverage
        bm_counts = filtered.group_by("bookmaker").agg(pl.len().alias("count")).sort("count", descending=True)
        st.subheader("Bookmaker Coverage")
        st.bar_chart(
            bm_counts.to_pandas().set_index("bookmaker")["count"],
            width="stretch",
        )

        # Market distribution
        market_counts = filtered.group_by("market").agg(pl.len().alias("count"))
        st.subheader("Market Distribution")
        st.bar_chart(
            market_counts.to_pandas().set_index("market")["count"],
            width="stretch",
        )

# ── Section D: Analytics Visualizations ───────────────────

st.header("📈 Analytics Visualizations")

CHARTS_DIR = _project_root / "charts"

viz_tabs = st.tabs(["Coverage & Markets", "Vig Analysis", "Odds Value", "Sharp vs Rec"])

with viz_tabs[0]:
    col1, col2 = st.columns(2)
    with col1:
        img = CHARTS_DIR / "01_bookmaker_coverage.png"
        if img.exists():
            st.image(str(img), caption="Bookmaker Coverage: Events vs Odds Lines")
        else:
            st.info("Chart not found. Run analytics generation.")
    with col2:
        img = CHARTS_DIR / "02_market_distribution.png"
        if img.exists():
            st.image(str(img), caption="Market Distribution: Odds Lines by Type")
        else:
            st.info("Chart not found.")

with viz_tabs[1]:
    img = CHARTS_DIR / "03_vig_by_bookmaker.png"
    if img.exists():
        st.image(str(img), caption="Market Efficiency: Average Vig by Bookmaker (Latest Snapshot)")
        st.markdown("""
        **Interpretation:** Lower vig = sharper bookmaker. 
        `lowvig` (3.5%) and `betonlineag` (4.3%) are most efficient.
        `betrivers` (5.6%) carries the highest margin.
        """)
    else:
        st.info("Chart not found.")

with viz_tabs[2]:
    col1, col2 = st.columns(2)
    with col1:
        img = CHARTS_DIR / "04_best_h2h_odds.png"
        if img.exists():
            st.image(str(img), caption="Best H2H Odds per Outcome")
        else:
            st.info("Chart not found.")
    with col2:
        img = CHARTS_DIR / "06_spreads_depth.png"
        if img.exists():
            st.image(str(img), caption="Spreads Market Depth")
        else:
            st.info("Chart not found.")

with viz_tabs[3]:
    img = CHARTS_DIR / "05_sharp_vs_rec.png"
    if img.exists():
        st.image(str(img), caption="Sharp vs Recreational Bookmaker: H2H Odds % Difference")
        st.markdown("""
        **Interpretation:** Positive bars = recreational books offer worse odds.
        Bigger bars = bigger edge for sharp bettors shopping lines.
        """)
    else:
        st.info("Chart not found.")

# ── Footer ──────────────────────────────────────────────────

st.divider()
st.caption(
    "Built with DuckDB + Polars + Streamlit | "
    f"Mode: {'Production (strict freshness)' if STRICT_FRESHNESS else 'Demo (stale data allowed)'}"
)
