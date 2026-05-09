"""Real-Time Multi-Sport Odds Market Intelligence Platform — Streamlit Dashboard."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import duckdb
import polars as pl
import streamlit as st
from datetime import datetime, timezone

from src.config import (
    ANALYTICS_DIR, PROCESSED_DIR, STRICT_FRESHNESS, EV_THRESHOLD,
    SPORTS, get_sport_label
)

st.set_page_config(
    page_title="Real-Time Multi-Sport Odds Market Intelligence Platform",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auto-refresh ────────────────────────────────────────────
if hasattr(st, "autorefresh"):
    st.autorefresh(interval=60 * 1000, key="auto_refresh")


# ── Data Loaders ────────────────────────────────────────────

def _safe_read(query: str) -> pl.DataFrame | None:
    try:
        df = duckdb.sql(query).pl()
        return df if not df.is_empty() else None
    except Exception:
        return None


def load_processed_odds() -> pl.DataFrame | None:
    return _safe_read("""
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
    """)


def load_plus_ev() -> pl.DataFrame | None:
    return _safe_read(
        "SELECT * FROM read_parquet('data/analytics/*/*/plus_ev.parquet', hive_partitioning=1)"
    )


def load_arbitrage() -> pl.DataFrame | None:
    return _safe_read(
        "SELECT * FROM read_parquet('data/analytics/*/*/arbitrage.parquet', hive_partitioning=1)"
    )


def load_line_movement() -> pl.DataFrame | None:
    return _safe_read(
        "SELECT * FROM read_parquet('data/analytics/line_movement/line_movement.parquet')"
    )


def load_movement_summary() -> pl.DataFrame | None:
    return _safe_read(
        "SELECT * FROM read_parquet('data/analytics/line_movement/movement_summary.parquet')"
    )


def get_unique_values(df: pl.DataFrame | None, col: str) -> list[str]:
    if df is None or col not in df.columns:
        return []
    return sorted([str(x) for x in df[col].unique().to_list() if x is not None])


def get_freshness(df: pl.DataFrame | None) -> tuple[datetime | None, int, str]:
    if df is None or "bookmaker_last_update" not in df.columns:
        return None, 0, "gray"
    try:
        latest = df["bookmaker_last_update"].max()
        if latest is None:
            return None, 0, "gray"
        now = datetime.now(timezone.utc)
        if hasattr(latest, "tzinfo") and latest.tzinfo is not None:
            age = int((now - latest).total_seconds() / 60)
        else:
            age = int((now.replace(tzinfo=None) - latest).total_seconds() / 60)
        color = "green" if age < 5 else "yellow" if age < 15 else "red"
        return latest, age, color
    except Exception:
        return None, 0, "gray"


# ── Load Data ─────────────────────────────────────────────
raw_odds = load_processed_odds()
ev_df = load_plus_ev()
arb_df = load_arbitrage()
movement_df = load_line_movement()
summary_df = load_movement_summary()

latest_time, age_min, freshness_color = get_freshness(raw_odds)

# ── Sidebar ────────────────────────────────────────────────

st.sidebar.title("⚙️ Filters")

mode_label = "Production (strict)" if STRICT_FRESHNESS else "Demo (allow stale)"
st.sidebar.caption(f"Mode: {mode_label}")

# Sport selector (multi-select, default all)
all_sports = get_unique_values(raw_odds, "sport")
if not all_sports:
    all_sports = SPORTS
sport_labels = {s: get_sport_label(s) for s in all_sports}
selected_sports = st.sidebar.multiselect(
    "Sports",
    options=all_sports,
    default=all_sports,
    format_func=lambda s: sport_labels.get(s, s),
    help="Filter by sport.",
)

# EV threshold
threshold = st.sidebar.slider(
    "EV Threshold (%)", 0.0, 10.0, float(EV_THRESHOLD * 100), 0.5,
) / 100.0

# Bookmaker & Market filters
all_bookmakers = get_unique_values(raw_odds, "bookmaker")
selected_bookmakers = st.sidebar.multiselect(
    "Bookmakers", options=all_bookmakers, default=all_bookmakers,
)
all_markets = get_unique_values(raw_odds, "market")
selected_markets = st.sidebar.multiselect(
    "Markets", options=all_markets, default=all_markets,
)

# ── Apply Filters ───────────────────────────────────────────

if raw_odds is not None and selected_sports:
    raw_odds = raw_odds.filter(pl.col("sport").is_in(selected_sports))
if ev_df is not None and selected_sports:
    ev_df = ev_df.filter(pl.col("sport").is_in(selected_sports))
if arb_df is not None and selected_sports:
    arb_df = arb_df.filter(pl.col("sport").is_in(selected_sports))
if movement_df is not None and selected_sports:
    movement_df = movement_df.filter(pl.col("sport").is_in(selected_sports))
if summary_df is not None and selected_sports:
    summary_df = summary_df.filter(pl.col("sport").is_in(selected_sports))

# ── Live Snapshot Banner ──────────────────────────────────

banner_styles = {
    "green": "background-color:#d4edda;color:#155724;",
    "yellow": "background-color:#fff3cd;color:#856404;",
    "red": "background-color:#f8d7da;color:#721c24;",
    "gray": "background-color:#e2e3e5;color:#383d41;",
}
style = banner_styles.get(freshness_color, banner_styles["gray"])

st.markdown(
    f"""
    <div style="{style} padding:10px 15px;border-radius:5px;margin-bottom:15px;">
        <strong>📡 Live Snapshot</strong> —
        Latest: <strong>{latest_time.strftime('%Y-%m-%d %H:%M UTC') if latest_time else 'N/A'}</strong> |
        Age: <strong>{age_min} min</strong> |
        Status: <strong>{freshness_color.upper()}</strong>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Title ─────────────────────────────────────────────────

st.title("🏆 Real-Time Multi-Sport Odds Market Intelligence Platform")
st.markdown("Multi-sport odds, arbitrage, +EV detection, and line movement analytics.")

# ── KPI Cards ─────────────────────────────────────────────

total_events = raw_odds["event_id"].n_unique() if raw_odds is not None else 0
total_bookies = raw_odds["bookmaker"].n_unique() if raw_odds is not None else 0
total_markets = raw_odds["market"].n_unique() if raw_odds is not None else 0
total_odds = raw_odds.height if raw_odds is not None else 0
ev_count = ev_df.height if ev_df is not None else 0
arb_count = arb_df.height if arb_df is not None else 0
num_sports = raw_odds["sport"].n_unique() if raw_odds is not None else 0

c1, c2, c3, c4 = st.columns(4)
c5, c6, c7, c8 = st.columns(4)

with c1:
    st.metric("Sports Tracked", num_sports)
with c2:
    st.metric("Events Tracked", total_events)
with c3:
    st.metric("Bookmakers Active", total_bookies)
with c4:
    st.metric("Total Odds", total_odds)
with c5:
    st.metric("+EV Signals", ev_count)
with c6:
    st.metric("Arbitrage", arb_count)
with c7:
    st.metric("Last Snapshot", latest_time.strftime("%H:%M") if latest_time else "N/A")
with c8:
    st.metric("Snapshot Age", f"{age_min} min")

# ── Section A: +EV Bets ───────────────────────────────────

st.header("📈 +EV Bets")

if ev_df is None or ev_df.is_empty():
    msg = (
        "🔒 No fresh +EV opportunities found. Data is older than the freshness threshold."
        if STRICT_FRESHNESS
        else "📭 No +EV opportunities found with current filters."
    )
    st.info(msg)
else:
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

        display_df = ev_df.with_columns([
            (pl.col("true_prob") * 100).round(2).alias("true_prob_pct"),
            (pl.col("ev") * 100).round(2).alias("ev_pct"),
        ])

        cols = [
            "sport", "home_team", "away_team", "bookmaker", "market",
            "outcome", "odds_decimal", "odds_american", "true_prob_pct",
            "ev_pct", "num_bookmakers_used",
        ]
        show_df = display_df.select([c for c in cols if c in display_df.columns])

        st.dataframe(
            show_df.to_pandas(),
            width="stretch",
            hide_index=True,
            column_config={
                "ev_pct": st.column_config.NumberColumn("EV %", format="%.2f%%"),
                "true_prob_pct": st.column_config.NumberColumn("True Prob", format="%.2f%%"),
                "odds_decimal": st.column_config.NumberColumn("Decimal", format="%.2f"),
            },
        )

        # Sport breakdown bar chart
        sport_ev = ev_df.group_by("sport").agg(pl.len().alias("count")).sort("count", descending=True)
        if not sport_ev.is_empty():
            sport_ev = sport_ev.with_columns(
                pl.col("sport").map_elements(lambda s: get_sport_label(s), return_dtype=pl.Utf8).alias("label")
            )
            st.bar_chart(sport_ev.to_pandas().set_index("label")["count"], width="stretch")

# ── Section B: Arbitrage ──────────────────────────────────

st.header("🔄 Arbitrage Opportunities")

if arb_df is None or arb_df.is_empty():
    msg = (
        "🔒 No fresh arbitrage opportunities found."
        if STRICT_FRESHNESS
        else "📭 No arbitrage opportunities found."
    )
    st.info(msg)
else:
    st.metric("Arbitrage Opportunities", arb_df.height)
    cols = [
        "sport", "home_team", "away_team", "market", "point",
        "margin", "profit_pct", "num_bookmakers",
        "leg_outcome", "leg_best_odds", "leg_best_bookmaker",
    ]
    display_df = arb_df.select([c for c in cols if c in arb_df.columns])
    st.dataframe(display_df.to_pandas(), width="stretch", hide_index=True)

# ── Section C: Line Movement Intelligence ───────────────────

st.header("📈 Line Movement Intelligence")

if movement_df is None or movement_df.is_empty():
    st.info("📭 No line movement data available. Need ≥2 snapshots per event. Run `make ingest` multiple times.")
else:
    mv_tabs = st.tabs(["Odds Movement", "Biggest Movers", "Impl. Prob. Movement", "Market Volatility"])

    with mv_tabs[0]:
        st.subheader("Odds Movement Over Time")
        events = get_unique_values(movement_df, "event_id")
        selected_event = st.selectbox("Select Event", events, key="mv_event")
        event_mv = movement_df.filter(pl.col("event_id") == selected_event)

        if not event_mv.is_empty():
            chart_data = event_mv.select([
                "bookmaker", "outcome", "snapshot_time", "latest_odds", "market"
            ]).sort("snapshot_time")
            chart_data = chart_data.with_columns(
                (pl.col("bookmaker") + " — " + pl.col("outcome") + " (" + pl.col("market") + ")").alias("line_label")
            )
            pd_chart = chart_data.select(["line_label", "snapshot_time", "latest_odds"]).to_pandas()
            if not pd_chart.empty:
                st.line_chart(pd_chart, x="snapshot_time", y="latest_odds", color="line_label", width="stretch")
            st.dataframe(
                event_mv.select([
                    "bookmaker", "market", "outcome", "latest_odds", "previous_odds",
                    "odds_delta", "snapshot_time"
                ]).to_pandas(),
                width="stretch", hide_index=True,
            )

    with mv_tabs[1]:
        st.subheader("Biggest Movers")
        if summary_df is not None and not summary_df.is_empty():
            filtered = summary_df
            if selected_bookmakers:
                filtered = filtered.filter(pl.col("bookmaker").is_in(selected_bookmakers))
            if selected_markets:
                filtered = filtered.filter(pl.col("market").is_in(selected_markets))

            col_up, col_down = st.columns(2)
            with col_up:
                st.markdown("**📈 Biggest Positive Moves**")
                up_df = filtered.filter(pl.col("net_change") > 0).sort("pct_change", descending=True).head(10)
                if not up_df.is_empty():
                    up_df = up_df.with_columns(
                        (pl.col("home_team") + " vs " + pl.col("away_team")).alias("matchup")
                    )
                    st.dataframe(
                        up_df.select(["matchup", "bookmaker", "outcome", "opening_odds", "latest_odds", "net_change", "pct_change"]).to_pandas(),
                        width="stretch", hide_index=True,
                        column_config={"pct_change": st.column_config.NumberColumn("Change %", format="+%.2f%%")},
                    )
                    chart_up = up_df.head(8).select(["outcome", "bookmaker", "pct_change"]).to_pandas()
                    chart_up["label"] = chart_up["bookmaker"] + " — " + chart_up["outcome"]
                    st.bar_chart(chart_up.set_index("label")["pct_change"], width="stretch")
                else:
                    st.info("No positive movers.")

            with col_down:
                st.markdown("**📉 Biggest Negative Moves**")
                down_df = filtered.filter(pl.col("net_change") < 0).sort("pct_change", descending=False).head(10)
                if not down_df.is_empty():
                    down_df = down_df.with_columns(
                        (pl.col("home_team") + " vs " + pl.col("away_team")).alias("matchup")
                    )
                    st.dataframe(
                        down_df.select(["matchup", "bookmaker", "outcome", "opening_odds", "latest_odds", "net_change", "pct_change"]).to_pandas(),
                        width="stretch", hide_index=True,
                        column_config={"pct_change": st.column_config.NumberColumn("Change %", format="%.2f%%")},
                    )
                    chart_down = down_df.head(8).select(["outcome", "bookmaker", "pct_change"]).to_pandas()
                    chart_down["label"] = chart_down["bookmaker"] + " — " + chart_down["outcome"]
                    st.bar_chart(chart_down.set_index("label")["pct_change"], width="stretch")
                else:
                    st.info("No negative movers.")
        else:
            st.info("No movement summary data.")

    with mv_tabs[2]:
        st.subheader("Implied Probability Movement")
        events_impl = get_unique_values(movement_df, "event_id")
        selected_impl = st.selectbox("Select Event", events_impl, key="impl_event")
        event_impl = movement_df.filter(pl.col("event_id") == selected_impl)

        if not event_impl.is_empty():
            impl_chart = event_impl.select([
                "bookmaker", "outcome", "snapshot_time", "latest_impl_prob", "market"
            ]).sort("snapshot_time")
            impl_chart = impl_chart.with_columns(
                (pl.col("bookmaker") + " — " + pl.col("outcome") + " (" + pl.col("market") + ")").alias("line_label")
            )
            pd_impl = impl_chart.select(["line_label", "snapshot_time", "latest_impl_prob"]).to_pandas()
            if not pd_impl.empty:
                st.line_chart(pd_impl, x="snapshot_time", y="latest_impl_prob", color="line_label", width="stretch")
            delta_chart = event_impl.select(["bookmaker", "outcome", "impl_prob_delta"]).to_pandas()
            delta_chart["label"] = delta_chart["bookmaker"] + " — " + delta_chart["outcome"]
            st.bar_chart(delta_chart.set_index("label")["impl_prob_delta"], width="stretch")
            st.dataframe(
                event_impl.select([
                    "bookmaker", "market", "outcome", "latest_impl_prob", "previous_impl_prob",
                    "impl_prob_delta", "snapshot_time"
                ]).to_pandas(), width="stretch", hide_index=True,
            )

    with mv_tabs[3]:
        st.subheader("Market Volatility Heatmap")
        if summary_df is not None and not summary_df.is_empty():
            heat_df = summary_df.with_columns(
                (pl.col("home_team") + " vs " + pl.col("away_team")).alias("matchup")
            )
            heat_agg = heat_df.group_by(["matchup", "bookmaker"]).agg(
                pl.max("pct_change").abs().alias("max_movement")
            ).sort("max_movement", descending=True)

            # Show as table since Streamlit doesn't have native heatmap
            st.dataframe(
                heat_agg.to_pandas(),
                width="stretch", hide_index=True,
                column_config={"max_movement": st.column_config.NumberColumn("Max Movement %", format="%.2f%%")},
            )

            st.subheader("Most Volatile Lines")
            top_vol = heat_agg.sort("max_movement", descending=True).head(15)
            st.dataframe(top_vol.to_pandas(), width="stretch", hide_index=True)

            vol_chart = top_vol.head(10).to_pandas()
            vol_chart["label"] = vol_chart["bookmaker"] + " — " + vol_chart["matchup"]
            st.bar_chart(vol_chart.set_index("label")["max_movement"], width="stretch")
        else:
            st.info("No volatility data.")

# ── Section D: Market Overview ────────────────────────────

st.header("📊 Market Overview")

if raw_odds is None or raw_odds.is_empty():
    st.warning("No processed odds data found. Run `make normalize` first.")
else:
    filtered = raw_odds
    if selected_bookmakers:
        filtered = filtered.filter(pl.col("bookmaker").is_in(selected_bookmakers))
    if selected_markets:
        filtered = filtered.filter(pl.col("market").is_in(selected_markets))

    if filtered.is_empty():
        st.info("📭 No odds match the selected filters.")
    else:
        st.metric("Active Odds", filtered.height)

        # Sport breakdown
        sport_counts = filtered.group_by("sport").agg(pl.len().alias("count")).sort("count", descending=True)
        sport_counts = sport_counts.with_columns(
            pl.col("sport").map_elements(lambda s: get_sport_label(s), return_dtype=pl.Utf8).alias("label")
        )
        st.subheader("Odds by Sport")
        st.bar_chart(sport_counts.to_pandas().set_index("label")["count"], width="stretch")

        # Bookmaker coverage
        bm_counts = filtered.group_by("bookmaker").agg(pl.len().alias("count")).sort("count", descending=True)
        st.subheader("Bookmaker Coverage")
        st.bar_chart(bm_counts.to_pandas().set_index("bookmaker")["count"], width="stretch")

        # Market distribution
        market_counts = filtered.group_by("market").agg(pl.len().alias("count"))
        st.subheader("Market Distribution")
        st.bar_chart(market_counts.to_pandas().set_index("market")["count"], width="stretch")

        # Best odds per outcome
        best_df = duckdb.sql("""
            SELECT
                event_id, sport, home_team, away_team, market, outcome, point,
                MAX(odds_decimal) AS best_decimal,
                FIRST(bookmaker ORDER BY odds_decimal DESC) AS best_bookmaker
            FROM filtered
            GROUP BY event_id, sport, home_team, away_team, market, outcome, point
            ORDER BY home_team, away_team, market, outcome
        """).pl()
        st.subheader("Best Odds per Outcome")
        st.dataframe(
            best_df.to_pandas(),
            width="stretch", hide_index=True,
            column_config={"best_decimal": st.column_config.NumberColumn("Best Odds", format="%.2f")},
        )

# ── Section E: Historical Analytics Charts ────────────────

st.header("📈 Historical Analytics")

CHARTS_DIR = _project_root / "charts"
viz_tabs = st.tabs(["Coverage & Markets", "Vig Analysis", "Odds Value", "Sharp vs Rec"])

with viz_tabs[0]:
    col1, col2 = st.columns(2)
    for path, caption in [
        ("01_bookmaker_coverage.png", "Bookmaker Coverage"),
        ("02_market_distribution.png", "Market Distribution"),
    ]:
        with col1 if path == "01_bookmaker_coverage.png" else col2:
            img = CHARTS_DIR / path
            if img.exists():
                st.image(str(img), caption=caption)
            else:
                st.info(f"Chart {path} not found.")

with viz_tabs[1]:
    img = CHARTS_DIR / "03_vig_by_bookmaker.png"
    if img.exists():
        st.image(str(img), caption="Average Vig by Bookmaker (Latest Snapshot)")
        st.markdown("""Lower vig = sharper bookmaker. `lowvig` (3.5%) and `betonlineag` (4.3%) are most efficient.""")
    else:
        st.info("Chart not found.")

with viz_tabs[2]:
    col1, col2 = st.columns(2)
    for path, caption in [
        ("04_best_h2h_odds.png", "Best H2H Odds"),
        ("06_spreads_depth.png", "Spreads Market Depth"),
    ]:
        with col1 if path == "04_best_h2h_odds.png" else col2:
            img = CHARTS_DIR / path
            if img.exists():
                st.image(str(img), caption=caption)
            else:
                st.info(f"Chart {path} not found.")

with viz_tabs[3]:
    img = CHARTS_DIR / "05_sharp_vs_rec.png"
    if img.exists():
        st.image(str(img), caption="Sharp vs Recreational: H2H Odds % Difference")
        st.markdown("""Positive bars = recreational books offer worse odds.""")
    else:
        st.info("Chart not found.")

# ── Footer ──────────────────────────────────────────────────

st.divider()
st.caption(
    "Built with DuckDB + Polars + Streamlit | "
    f"Mode: {'Production (strict freshness)' if STRICT_FRESHNESS else 'Demo (stale data allowed)'} | "
    f"Last refresh: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
)
