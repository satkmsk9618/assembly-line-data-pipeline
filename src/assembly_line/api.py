"""Read-only metrics API backed by PostgreSQL."""
from datetime import date

from fastapi import FastAPI, HTTPException, Query

from assembly_line.db import connect

app = FastAPI(title="Assembly Line Metrics API", version="0.4.0")


@app.get("/health")
def health():
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc


def _filters(start_date: date | None, end_date: date | None, station_id: str | None, shift_name: str | None):
    clauses, params = [], []
    if start_date:
        clauses.append("f.start_ts >= %s::date")
        params.append(start_date)
    if end_date:
        clauses.append("f.start_ts < (%s::date + INTERVAL '1 day')")
        params.append(end_date)
    if station_id:
        clauses.append("f.station_id = %s")
        params.append(station_id)
    if shift_name:
        clauses.append("sh.shift_name = %s")
        params.append(shift_name)
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


@app.get("/metrics/summary")
def summary(start_date: date | None = None, end_date: date | None = None,
            station_id: str | None = None, shift_name: str | None = None):
    where, params = _filters(start_date, end_date, station_id, shift_name)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""WITH filtered AS (
              SELECT f.vehicle_id, f.status, f.cycle_time_minutes
              FROM fact_station_event f JOIN dim_shift sh USING(shift_id)""" + where + """),
            per_vehicle AS (
              SELECT vehicle_id, bool_and(status='complete') AS first_pass
              FROM filtered GROUP BY vehicle_id
            ), totals AS (
              SELECT count(*) AS station_events, round(avg(cycle_time_minutes)::numeric, 2) AS avg_cycle_minutes
              FROM filtered
            )
            SELECT totals.station_events, (SELECT count(*) FROM per_vehicle) AS vehicles_processed,
              totals.avg_cycle_minutes,
              round(100.0 * (SELECT count(*) FROM per_vehicle WHERE first_pass) /
                    NULLIF((SELECT count(*) FROM per_vehicle),0), 2) AS first_pass_yield_pct
            FROM totals""", params)
        result = cur.fetchone()
    return dict(result)


@app.get("/metrics/stations")
def stations(start_date: date | None = None, end_date: date | None = None,
             station_id: str | None = None, shift_name: str | None = None):
    where, params = _filters(start_date, end_date, station_id, shift_name)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT f.station_id, count(*) AS events,
            round(avg(f.cycle_time_minutes)::numeric,2) AS avg_cycle_minutes,
            count(*) FILTER (WHERE f.status='rework') AS rework_events
            FROM fact_station_event f JOIN dim_station s USING(station_id)
            JOIN dim_shift sh USING(shift_id)""" + where +
            " GROUP BY f.station_id ORDER BY avg(f.cycle_time_minutes) DESC", params)
        return [dict(row) for row in cur.fetchall()]


@app.get("/dimensions")
def dimensions():
    """Return distinct filter choices for the dashboard."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT station_id FROM dim_station ORDER BY station_id")
        station_ids = [row["station_id"] for row in cur.fetchall()]
        cur.execute("SELECT shift_name FROM dim_shift ORDER BY shift_name")
        shifts = [row["shift_name"] for row in cur.fetchall()]
    return {"stations": station_ids, "shifts": shifts}


@app.get("/metrics/live-summary")
def live_summary(hours: int = Query(default=1, ge=1, le=720), start_date: date | None = None,
                 end_date: date | None = None, all_time: bool = False):
    """Line-health indicators for a recent window or the complete history."""
    with connect() as conn, conn.cursor() as cur:
        where, params = _history_filter("end_ts", hours, start_date, end_date, all_time)
        cur.execute("""SELECT count(*) AS station_events,
            count(DISTINCT vehicle_id) AS vehicles,
            round(avg(cycle_time_minutes)::numeric,2) AS avg_cycle_minutes,
            count(*) FILTER (WHERE cycle_time_minutes > 8) AS events_over_takt,
            count(*) FILTER (WHERE status='rework') AS rework_events,
            round(100.0 * count(*) FILTER (WHERE status='rework') / NULLIF(count(*),0),2) AS rework_rate_pct,
            max(end_ts) AS latest_event_ts
            FROM fact_station_event""" + where, params)
        return dict(cur.fetchone())


@app.get("/metrics/trend")
def trend(hours: int = Query(default=6, ge=1, le=720), start_date: date | None = None,
          end_date: date | None = None, all_time: bool = False):
    """Five-minute recent trend or daily trend across complete history."""
    with connect() as conn, conn.cursor() as cur:
        where, params = _history_filter("end_ts", hours, start_date, end_date, all_time)
        bucket = "date_trunc('day', end_ts)" if all_time and not (start_date or end_date) else "date_bin('5 minutes', end_ts, date_trunc('hour', now()))"
        cur.execute(f"""SELECT {bucket} AS time_bucket,
            count(*) AS station_events, count(DISTINCT vehicle_id) AS vehicles,
            round(avg(cycle_time_minutes)::numeric,2) AS avg_cycle_minutes,
            count(*) FILTER (WHERE status='rework') AS rework_events
            FROM fact_station_event""" + where + " GROUP BY time_bucket ORDER BY time_bucket", params)
        return [dict(row) for row in cur.fetchall()]


@app.get("/metrics/station-health")
def station_health(hours: int = Query(default=1, ge=1, le=720), start_date: date | None = None,
                   end_date: date | None = None, all_time: bool = False):
    """Show which stations are slow or producing the most rework."""
    with connect() as conn, conn.cursor() as cur:
        where, params = _history_filter("f.end_ts", hours, start_date, end_date, all_time)
        cur.execute("""SELECT f.station_id, count(*) AS events,
            round(avg(f.cycle_time_minutes)::numeric,2) AS avg_cycle_minutes,
            round(percentile_cont(0.9) WITHIN GROUP (ORDER BY f.cycle_time_minutes)::numeric,2) AS p90_cycle_minutes,
            count(*) FILTER (WHERE f.cycle_time_minutes > 8) AS over_takt_events,
            count(*) FILTER (WHERE f.status='rework') AS rework_events,
            round(100.0 * count(*) FILTER (WHERE f.status='rework') / NULLIF(count(*),0),2) AS rework_rate_pct
            FROM fact_station_event f""" + where + " GROUP BY f.station_id ORDER BY avg(f.cycle_time_minutes) DESC", params)
        return [dict(row) for row in cur.fetchall()]


@app.get("/metrics/quality")
def quality(hours: int = Query(default=24, ge=1, le=720), start_date: date | None = None,
            end_date: date | None = None, all_time: bool = False):
    """Recent defect counts by type and severity for a Pareto-style view."""
    with connect() as conn, conn.cursor() as cur:
        where, params = _history_filter("f.recorded_ts", hours, start_date, end_date, all_time)
        cur.execute("""SELECT d.defect_type, f.severity, count(*) AS defects,
            count(*) FILTER (WHERE f.rework_flag) AS rework_defects
            FROM fact_defect f JOIN dim_defect d USING(defect_id)""" + where +
            " GROUP BY d.defect_type, f.severity ORDER BY count(*) DESC, d.defect_type", params)
        return [dict(row) for row in cur.fetchall()]


@app.get("/metrics/downtime")
def downtime(hours: int = Query(default=24, ge=1, le=720), start_date: date | None = None,
             end_date: date | None = None, all_time: bool = False):
    """Recent downtime minutes by station and stop reason."""
    with connect() as conn, conn.cursor() as cur:
        where, params = _history_filter("end_ts", hours, start_date, end_date, all_time)
        cur.execute("""SELECT station_id, reason_code, count(*) AS stops,
            round(sum(extract(epoch FROM (end_ts - start_ts)) / 60)::numeric,1) AS downtime_minutes
            FROM fact_downtime""" + where +
            " GROUP BY station_id, reason_code ORDER BY sum(extract(epoch FROM (end_ts - start_ts))) DESC", params)
        return [dict(row) for row in cur.fetchall()]


def _history_filter(column: str, hours: int, start_date: date | None, end_date: date | None,
                    all_time: bool = False):
    """Return a safe SQL time predicate for a recent window or chosen dates."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if start_date or end_date:
        clauses, params = [], []
        if start_date:
            clauses.append(f"{column} >= %s::date")
            params.append(start_date)
        if end_date:
            clauses.append(f"{column} < (%s::date + INTERVAL '1 day')")
            params.append(end_date)
        return " WHERE " + " AND ".join(clauses), params
    if all_time:
        return "", []
    return f" WHERE {column} >= now() - (%s * INTERVAL '1 hour')", [hours]
