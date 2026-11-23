"""Live, problem-solving view of the simulated assembly line."""
from __future__ import annotations

from datetime import datetime, timezone
import os

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Assembly Line Control Room", page_icon="🚗", layout="wide")
st.markdown("""
<style>
  *, *::before, *::after {box-sizing: border-box;}
  .block-container {padding-top: 1.8rem; padding-bottom: 3rem;}
  [data-testid="stMetric"] {background: #f4f7f8; border: 1px solid #e1e8eb; padding: 14px 16px; border-radius: 12px; width: 100%; height: 142px; display: flex; flex-direction: column; justify-content: space-between;}
  [data-testid="stMetricLabel"] {color: #425466; min-height: 24px;}
  [data-testid="stMetricValue"] {min-height: 44px; display: flex; align-items: center;}
  [data-testid="stMetricDelta"] {min-height: 20px;}
  .source-note {padding: 12px 15px; border-radius: 10px; background: #e8f4f1; color: #145a50;}
</style>
""", unsafe_allow_html=True)

st.title("🚗 Assembly Line Control Room")
st.caption("A live operations view backed by a clearly labeled simulated event stream.")
api_url = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
REFRESH_SECONDS = 15

with st.sidebar:
    st.header("Dashboard settings")
    hours = st.selectbox("Recent data window", [1, 6, 24], index=0, format_func=lambda n: f"Last {n} hour" if n == 1 else f"Last {n} hours")
    st.markdown("---")
    st.caption("Dashboard refreshes every 15 seconds.")
    st.caption("All records are synthetic. No real factory equipment is connected.")


def get_json(path: str, **params):
    response = requests.get(f"{api_url}{path}", params=params, timeout=8)
    response.raise_for_status()
    return response.json()


def show_empty(message: str) -> None:
    st.info(message)


@st.fragment(run_every=REFRESH_SECONDS)
def show_live_dashboard(window_hours: int):
    try:
        summary = get_json("/metrics/live-summary", hours=window_hours)
        trend = get_json("/metrics/trend", hours=window_hours)
        stations = get_json("/metrics/station-health", hours=window_hours)
        quality = get_json("/metrics/quality", hours=max(1, window_hours))
        downtime = get_json("/metrics/downtime", hours=max(1, window_hours))
    except requests.RequestException as exc:
        st.error(f"I could not reach the metrics API. Check that Docker Compose is running. Details: {exc}")
        return

    latest = pd.to_datetime(summary.get("latest_event_ts"), utc=True, errors="coerce")
    if pd.isna(latest):
        st.warning("No production events are loaded yet. The simulated feed should add the first events shortly.")
        age_seconds = None
    else:
        age_seconds = max(0, int((pd.Timestamp.now(tz="UTC") - latest).total_seconds()))
        if age_seconds <= 180:
            st.markdown(f'<div class="source-note">● Simulated feed is active · latest event {age_seconds} seconds ago · dashboard refreshes every {REFRESH_SECONDS}s</div>', unsafe_allow_html=True)
        else:
            st.warning(f"The most recent event is {age_seconds // 60} minutes old. Check the simulator service in Docker Compose.")

    events = int(summary.get("station_events") or 0)
    vehicles = int(summary.get("vehicles") or 0)
    avg_cycle = float(summary.get("avg_cycle_minutes") or 0)
    takt_misses = int(summary.get("events_over_takt") or 0)
    rework_pct = float(summary.get("rework_rate_pct") or 0)
    rate = round(vehicles / window_hours, 1)

    metric_cols = st.columns(4)
    metric_cols[0].metric("Vehicles", f"{vehicles:,}", f"{rate}/hour")
    metric_cols[1].metric("Station events", f"{events:,}")
    metric_cols[2].metric("Avg cycle", f"{avg_cycle:.2f} min", "vs 8 min takt" if avg_cycle else None)
    metric_cols[3].metric("Rework rate", f"{rework_pct:.1f}%", f"{int(summary.get('rework_events') or 0)} events")
    st.caption(f"{takt_misses:,} of {events:,} station events exceeded the 8-minute takt target.")

    overview, quality_tab, downtime_tab = st.tabs(["Line overview", "Quality", "Downtime"])
    with overview:
        left, right = st.columns([1.2, 1])
        trend_frame = pd.DataFrame(trend)
        if trend_frame.empty:
            show_empty("Waiting for recent events to build the trend charts.")
        else:
            trend_frame["time_bucket"] = pd.to_datetime(trend_frame["time_bucket"], utc=True).dt.tz_convert(None)
            trend_frame = trend_frame.set_index("time_bucket").sort_index()
            with left:
                st.subheader("Production pace")
                st.line_chart(trend_frame[["vehicles"]], y_label="Vehicles per 5 minutes", height=280)
            with right:
                st.subheader("Cycle time over the shift")
                st.line_chart(trend_frame[["avg_cycle_minutes"]], y_label="Minutes", height=280)

        station_frame = pd.DataFrame(stations)
        st.subheader("Which station needs attention?")
        st.caption("Stations are ranked by average cycle time. The target line is 8-minute takt; check the rework and over-takt columns before deciding what to investigate.")
        if station_frame.empty:
            show_empty("No station events in this time window yet.")
        else:
            top_over_takt = station_frame.sort_values("over_takt_events", ascending=False).iloc[0]
            if int(top_over_takt["over_takt_events"]) > 0:
                st.warning(f"Investigate {top_over_takt['station_id']} first: it has {int(top_over_takt['over_takt_events'])} events over the 8-minute takt target in this window.")
            else:
                st.success("No station events exceeded the 8-minute takt target in this window.")
            chart_frame = station_frame.set_index("station_id")[["avg_cycle_minutes", "p90_cycle_minutes"]]
            chart_frame["takt_target_minutes"] = 8.0
            st.line_chart(chart_frame, y_label="Cycle time (minutes)", height=300)
            st.dataframe(station_frame, width="stretch", hide_index=True,
                         column_config={
                             "station_id": st.column_config.TextColumn("Station"),
                             "events": st.column_config.NumberColumn("Events", format="%d"),
                             "avg_cycle_minutes": st.column_config.NumberColumn("Average cycle", format="%.2f min"),
                             "p90_cycle_minutes": st.column_config.NumberColumn("90th percentile", format="%.2f min"),
                             "over_takt_events": st.column_config.NumberColumn("Over takt", format="%d"),
                             "rework_events": st.column_config.NumberColumn("Rework", format="%d"),
                             "rework_rate_pct": st.column_config.NumberColumn("Rework rate", format="%.1f%%"),
                         })

    with quality_tab:
        st.subheader("Defect Pareto")
        st.caption("Defects are grouped by type and severity. Start with the most frequent category, then compare severity and rework counts.")
        quality_frame = pd.DataFrame(quality)
        if quality_frame.empty:
            show_empty("No defects have been recorded in this time window.")
        else:
            pareto = quality_frame.groupby("defect_type", as_index=False)[["defects", "rework_defects"]].sum().sort_values("defects", ascending=False)
            top_defect = pareto.iloc[0]
            st.info(f"Most frequent issue: {top_defect['defect_type']} ({int(top_defect['defects'])} records), including {int(top_defect['rework_defects'])} rework-related defects.")
            q_left, q_right = st.columns([1.1, 1])
            with q_left:
                st.bar_chart(pareto.set_index("defect_type")[["defects"]], y_label="Defect records", height=300)
            with q_right:
                severity = quality_frame.pivot_table(index="defect_type", columns="severity", values="defects", aggfunc="sum", fill_value=0)
                st.bar_chart(severity, y_label="Defect records by severity", height=300)
            st.dataframe(pareto, width="stretch", hide_index=True)

    with downtime_tab:
        st.subheader("Where is production time being lost?")
        st.caption("Downtime is grouped by stop reason. Use the table to find which station and cause contribute the most minutes.")
        downtime_frame = pd.DataFrame(downtime)
        if downtime_frame.empty:
            show_empty("No downtime events have been recorded in this time window.")
        else:
            by_reason = downtime_frame.groupby("reason_code", as_index=False)[["downtime_minutes"]].sum().sort_values("downtime_minutes", ascending=False)
            top_stop = downtime_frame.sort_values("downtime_minutes", ascending=False).iloc[0]
            st.info(f"Largest recorded stop: {top_stop['reason_code']} at {top_stop['station_id']} ({top_stop['downtime_minutes']} minutes).")
            d_left, d_right = st.columns(2)
            with d_left:
                st.bar_chart(by_reason.set_index("reason_code"), y_label="Downtime (minutes)", height=300)
            with d_right:
                by_station = downtime_frame.groupby("station_id", as_index=False)[["downtime_minutes"]].sum().sort_values("downtime_minutes", ascending=False)
                st.bar_chart(by_station.set_index("station_id"), y_label="Downtime (minutes)", height=300)
            st.dataframe(downtime_frame, width="stretch", hide_index=True)

    st.caption(f"Data window: last {window_hours} hour(s) · last checked {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")


show_live_dashboard(hours)
