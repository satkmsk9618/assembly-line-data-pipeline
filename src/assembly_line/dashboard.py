"""Live, problem-solving view of the simulated assembly line."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os
import secrets
import threading
import time
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, available_timezones

import pandas as pd
import requests
import streamlit as st

from assembly_line import cloud_simulator
from assembly_line.auth import auth_settings, current_user, make_client, remember_oauth_client, take_oauth_client
from assembly_line.db import connect, database_url
from assembly_line.report_pdf import create_daily_pdf

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

auth_config = auth_settings()
logged_in_user = None
if auth_config:
    auth_client = make_client(*auth_config)
    oauth_callback_error = ""
    oauth_error = st.query_params.get("error_description") or st.query_params.get("error")
    oauth_code = st.query_params.get("code")
    if oauth_error:
        oauth_callback_error = "Google sign-in was not completed. Please try again."
        st.query_params.clear()
    elif oauth_code:
        oauth_flow = st.query_params.get("oauth_flow", "")
        callback_client = take_oauth_client(oauth_flow)
        if callback_client is None:
            oauth_callback_error = "The Google sign-in session expired. Please start sign-in again."
            st.query_params.clear()
        else:
            try:
                result = callback_client.auth.exchange_code_for_session({"auth_code": oauth_code})
                if result.session:
                    st.session_state["auth_access_token"] = result.session.access_token
                    st.session_state["auth_refresh_token"] = result.session.refresh_token
                    st.query_params.clear()
                    st.rerun()
                oauth_callback_error = "Google sign-in did not return a session. Please try again."
            except Exception:
                oauth_callback_error = "Google sign-in could not be completed. Check the Supabase OAuth settings and try again."
            st.query_params.clear()
    logged_in_user = current_user(auth_client, st.session_state.get("auth_access_token", ""),
                                  st.session_state.get("auth_refresh_token", ""))
    if not logged_in_user:
        st.title("Assembly Line Dashboard")
        st.write("Sign in with email and password or Google to view saved production history and manage your daily report.")
        login_tab, signup_tab = st.tabs(["Sign in", "Create account"])
        with login_tab:
            if oauth_callback_error:
                st.error(oauth_callback_error)
            with st.form("sign_in_form"):
                login_email = st.text_input("Email", key="login_email")
                login_password = st.text_input("Password", type="password", key="login_password")
                login_submit = st.form_submit_button("Sign in", type="primary")
            if login_submit:
                try:
                    result = auth_client.auth.sign_in_with_password({"email": login_email, "password": login_password})
                    st.session_state["auth_access_token"] = result.session.access_token
                    st.session_state["auth_refresh_token"] = result.session.refresh_token
                    st.rerun()
                except Exception:
                    st.error("Sign-in failed. Check your email and password, then try again.")
            try:
                oauth_flow = secrets.token_urlsafe(24)
                redirect_to = f"{st.context.url}?{urlencode({'oauth_flow': oauth_flow})}"
                oauth_response = auth_client.auth.sign_in_with_oauth({
                    "provider": "google",
                    "options": {"redirect_to": redirect_to},
                })
                remember_oauth_client(oauth_flow, auth_client)
                st.link_button("Continue with Google", oauth_response.url, use_container_width=True)
            except Exception:
                st.info("Google sign-in is unavailable. Check that Google is enabled in Supabase Auth.")
        with signup_tab:
            with st.form("sign_up_form"):
                signup_email = st.text_input("Email", key="signup_email")
                signup_password = st.text_input("Password (at least 8 characters)", type="password", key="signup_password")
                signup_submit = st.form_submit_button("Create account")
            if signup_submit:
                if len(signup_password) < 8:
                    st.error("Choose a password with at least 8 characters.")
                else:
                    try:
                        result = auth_client.auth.sign_up({"email": signup_email, "password": signup_password})
                        if result.session:
                            st.session_state["auth_access_token"] = result.session.access_token
                            st.session_state["auth_refresh_token"] = result.session.refresh_token
                            st.rerun()
                        st.success("Check your inbox to verify your email, then sign in here.")
                    except Exception:
                        st.error("Account creation failed. Check the email and try again.")
        st.caption("Email confirmation should stay enabled in Supabase Auth. Passwords are handled by Supabase and are not stored by this app.")
        st.stop()
    st.sidebar.caption(f"Signed in as {logged_in_user.email}")
    if st.sidebar.button("Sign out"):
        st.session_state.pop("auth_access_token", None)
        st.session_state.pop("auth_refresh_token", None)
        st.rerun()

    try:
        private_db_ready = bool(os.getenv("DATABASE_URL") or st.secrets.get("DATABASE_URL", ""))
    except Exception:
        private_db_ready = bool(os.getenv("DATABASE_URL"))
    with st.sidebar.expander("Daily PDF email (optional)"):
        if private_db_ready:
            try:
                with connect() as conn:
                    row = conn.execute("SELECT timezone, send_hour, opted_in FROM report_preference WHERE user_id=%s", (str(logged_in_user.id),)).fetchone()
                preference = dict(row) if row else {}
                zones = sorted(available_timezones())
                saved_zone = preference.get("timezone", "UTC")
                selected_zone = st.selectbox("Time zone", zones, index=zones.index(saved_zone) if saved_zone in zones else zones.index("UTC"))
                selected_hour = st.slider("Send time in your time zone", 0, 23, int(preference.get("send_hour", 9)))
                opted_in = st.checkbox("Email me a daily report", value=bool(preference.get("opted_in", False)))
                st.caption(f"The report goes to your account email: {logged_in_user.email}")
                if st.button("Save email preference", key="save_email_preference"):
                    inactive_through = datetime.now(ZoneInfo(selected_zone)).date() - timedelta(days=1)
                    last_sent_day = None if opted_in else inactive_through
                    with connect() as conn:
                        conn.execute("""INSERT INTO report_preference(user_id, report_email, timezone, send_hour, opted_in, last_sent_local_date)
                            VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET
                            report_email=EXCLUDED.report_email, timezone=EXCLUDED.timezone,
                            send_hour=EXCLUDED.send_hour, opted_in=EXCLUDED.opted_in,
                            last_sent_local_date=CASE WHEN EXCLUDED.opted_in THEN report_preference.last_sent_local_date ELSE EXCLUDED.last_sent_local_date END,
                            updated_at=CURRENT_TIMESTAMP""",
                            (str(logged_in_user.id), logged_in_user.email, selected_zone, selected_hour, opted_in, last_sent_day))
                    st.success("Your daily report preference was saved.")
            except Exception as exc:
                st.warning(f"Report settings need the database schema to be installed. {exc}")
        else:
            st.info("Connect PostgreSQL to save your report preference. Email reports are optional.")
else:
    st.sidebar.info(
        "To set up daily email reports, add SUPABASE_URL and SUPABASE_ANON_KEY "
        "in this app's Streamlit secrets, then create an account or sign in."
    )

st.title("🚗 Assembly Line Control Room")
st.caption("A live operations view backed by a clearly labeled simulated event stream.")
api_url = os.getenv("API_URL", "").rstrip("/")
persistent_mode = not api_url and bool(database_url())
cloud_mode = not api_url and not persistent_mode
REFRESH_SECONDS = 15


@st.cache_resource
def shared_persistent_simulator():
    """One generator state per app process, shared safely across viewers."""
    shared = {"state": {}, "lock": threading.Lock(), "thread_lock": threading.Lock(), "last_error": None}

    def generate_forever():
        # Keep the hosted feed moving independently of browser reruns. This avoids
        # coupling database writes to Streamlit's page refresh cycle.
        while True:
            try:
                with shared["lock"]:
                    cloud_simulator.advance(shared["state"])
                    cloud_simulator.persist_new_records(shared["state"])
                    shared["last_error"] = None
            except Exception as exc:  # keep retrying after transient DB/network errors
                shared["last_error"] = str(exc)
            time.sleep(REFRESH_SECONDS)

    with shared["thread_lock"]:
        thread = threading.Thread(target=generate_forever, name="assembly-line-generator", daemon=True)
        thread.start()
    return shared

with st.sidebar:
    st.header("Dashboard settings")
    data_view = st.radio("Data view", ["Recent", "Historical"])
    hours = st.selectbox("Recent data window", [1, 6, 24, 72], index=0, format_func=lambda n: f"Last {n} hour" if n == 1 else f"Last {n} hours")
    history_filters = {}
    if data_view == "Historical":
        history_start = st.date_input("From date", value=date.today())
        history_end = st.date_input("Through date", value=date.today())
        if history_start > history_end:
            st.error("The start date must be on or before the end date.")
            st.stop()
        history_filters = {"start_date": history_start.isoformat(), "end_date": history_end.isoformat()}
    auto_refresh = False
    if data_view == "Recent":
        auto_refresh = st.toggle("Auto-refresh every 15 seconds", value=False, key="dashboard_auto_refresh_v2")
        if not auto_refresh and st.button("Refresh dashboard now"):
            st.rerun()
    else:
        st.caption("Historical results stay still while you review them.")
    st.markdown("---")
    if data_view == "Recent":
        st.caption("Auto-refresh is on." if auto_refresh else "Auto-refresh is paused.")
        if persistent_mode and not auto_refresh:
            st.caption("New simulated records are still saved every 15 seconds. Use Refresh dashboard now to load the latest view.")
    st.caption("All records are synthetic. No real factory equipment is connected.")
    if cloud_mode:
        st.caption("Hosted demo mode: the app generates its own sample events; PostgreSQL is not connected.")
        if data_view == "Historical":
            st.warning("This session has no persistent history. Configure API_URL to a PostgreSQL-backed API to browse saved dates.")
            st.stop()


def get_json(path: str, **params):
    if cloud_mode:
        return cloud_simulator.metrics(st.session_state, path, int(params.get("hours", 1)))
    if persistent_mode:
        from assembly_line import api as metrics_api
        date_args = {key: date.fromisoformat(params[key]) for key in ("start_date", "end_date") if key in params}
        hours_arg = int(params.get("hours", 1))
        direct = {
            "/metrics/live-summary": lambda: metrics_api.live_summary(hours=hours_arg, **date_args),
            "/metrics/trend": lambda: metrics_api.trend(hours=hours_arg, **date_args),
            "/metrics/station-health": lambda: metrics_api.station_health(hours=hours_arg, **date_args),
            "/metrics/quality": lambda: metrics_api.quality(hours=hours_arg, **date_args),
            "/metrics/downtime": lambda: metrics_api.downtime(hours=hours_arg, **date_args),
        }
        return direct[path]()
    response = requests.get(f"{api_url}{path}", params=params, timeout=8)
    response.raise_for_status()
    return response.json()


def show_empty(message: str) -> None:
    st.info(message)


@st.fragment(run_every=REFRESH_SECONDS if auto_refresh and not history_filters else None)
def show_live_dashboard(window_hours: int, history: dict):
    if cloud_mode and not history:
        cloud_simulator.advance(st.session_state)
    if persistent_mode and not history:
        shared = shared_persistent_simulator()
        if shared["last_error"]:
            st.warning(f"The background simulator could not save its latest batch. It will retry automatically. Details: {shared['last_error']}")
    try:
        query = {"hours": window_hours, **history}
        summary = get_json("/metrics/live-summary", **query)
        trend = get_json("/metrics/trend", **query)
        stations = get_json("/metrics/station-health", **query)
        quality = get_json("/metrics/quality", **query)
        downtime = get_json("/metrics/downtime", **query)
    except Exception as exc:
        st.error(f"I could not load the metrics. Check that the API or PostgreSQL database is running and configured. Details: {exc}")
        return

    latest = pd.to_datetime(summary.get("latest_event_ts"), utc=True, errors="coerce")
    if history:
        st.markdown(f'<div class="source-note">Historical database records · {history["start_date"]} through {history["end_date"]}</div>', unsafe_allow_html=True)
    elif pd.isna(latest):
        st.warning("No production events are loaded yet. The simulated feed should add the first events shortly.")
        age_seconds = None
    else:
        age_seconds = max(0, int((pd.Timestamp.now(tz="UTC") - latest).total_seconds()))
        if age_seconds <= 180:
            source = "Hosted simulator" if cloud_mode else "Persistent simulated feed" if persistent_mode else "Simulated feed"
            refresh_note = f"auto-refreshes every {REFRESH_SECONDS}s" if auto_refresh else "auto-refresh is paused"
            st.markdown(f'<div class="source-note">● {source} is active · latest event {age_seconds} seconds ago · {refresh_note}</div>', unsafe_allow_html=True)
        else:
            st.warning(f"The most recent event is {age_seconds // 60} minutes old. Check the simulator service in Docker Compose.")

    events = int(summary.get("station_events") or 0)
    vehicles = int(summary.get("vehicles") or 0)
    avg_cycle = float(summary.get("avg_cycle_minutes") or 0)
    takt_misses = int(summary.get("events_over_takt") or 0)
    rework_pct = float(summary.get("rework_rate_pct") or 0)
    rate = round(vehicles / window_hours, 1) if not history else None

    metric_cols = st.columns(4)
    metric_cols[0].metric("Vehicles", f"{vehicles:,}", f"{rate}/hour" if rate is not None else None)
    metric_cols[1].metric("Station events", f"{events:,}")
    metric_cols[2].metric("Avg cycle", f"{avg_cycle:.2f} min", "vs 8 min takt" if avg_cycle else None)
    metric_cols[3].metric("Rework rate", f"{rework_pct:.1f}%", f"{int(summary.get('rework_events') or 0)} events")
    st.caption(f"{takt_misses:,} of {events:,} station events exceeded the 8-minute takt target.")
    report_start = history.get("start_date", f"Last {window_hours} hours")
    report_end = history.get("end_date", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    pdf = create_daily_pdf(summary=summary, stations=stations, quality=quality, downtime=downtime,
                           start=report_start, end=report_end,
                           source="Stored simulated production data" if history else "Live simulated production data")
    st.download_button("Download detailed report (PDF)", pdf,
                       file_name=f"assembly-line-report-{history.get('start_date', date.today().isoformat())}.pdf",
                       mime="application/pdf", key="download_daily_report")

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

    caption = (f"Historical window: {history['start_date']} through {history['end_date']}" if history
               else f"Data window: last {window_hours} hour(s)")
    st.caption(f"{caption} · last checked {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")


show_live_dashboard(hours, history_filters)
