-- Run with: psql "$DATABASE_URL" -f sql/analytics.sql
-- These are practice queries. Capture plans using EXPLAIN (ANALYZE, BUFFERS).

-- 1. Average cycle time by station (bottleneck candidates)
SELECT station_id, round(avg(cycle_time_minutes), 2) AS avg_cycle
FROM fact_station_event GROUP BY station_id ORDER BY avg_cycle DESC;

-- 2. Cycle time trend by hour
SELECT date_trunc('hour', start_ts) AS hour, round(avg(cycle_time_minutes), 2) AS avg_cycle
FROM fact_station_event GROUP BY 1 ORDER BY 1;

-- 3. Rework rate by operator shift
SELECT sh.shift_name,
       round(100.0 * count(*) FILTER (WHERE e.status='rework') / count(*), 2) AS rework_pct
FROM fact_station_event e JOIN dim_shift sh USING (shift_id)
GROUP BY sh.shift_name ORDER BY rework_pct DESC;

-- 4. Running event count by station and time (window function)
SELECT station_id, start_ts,
       count(*) OVER (PARTITION BY station_id ORDER BY start_ts) AS running_events
FROM fact_station_event;

-- 5. Rank stations by average cycle time
WITH station_cycle AS (
    SELECT station_id, avg(cycle_time_minutes) AS avg_cycle
    FROM fact_station_event GROUP BY station_id
)
SELECT station_id, round(avg_cycle, 2), dense_rank() OVER (ORDER BY avg_cycle DESC) AS bottleneck_rank
FROM station_cycle;

-- 6. Defect mix by severity
SELECT d.defect_type, f.severity, count(*) AS defects
FROM fact_defect f JOIN dim_defect d USING (defect_id)
GROUP BY d.defect_type, f.severity ORDER BY defects DESC;

-- 7. Downtime minutes by cause and station
SELECT station_id, reason_code,
       round(sum(extract(epoch FROM (end_ts-start_ts))/60)::numeric, 1) AS downtime_minutes
FROM fact_downtime GROUP BY station_id, reason_code ORDER BY downtime_minutes DESC;

-- 8. Compare each station to the line average (CTE)
WITH line AS (SELECT avg(cycle_time_minutes) AS line_avg FROM fact_station_event)
SELECT station_id, round(avg(cycle_time_minutes),2) AS station_avg,
       round(avg(cycle_time_minutes) - line.line_avg,2) AS difference_from_line
FROM fact_station_event CROSS JOIN line GROUP BY station_id, line.line_avg;

-- 9. Daily first-pass yield
SELECT start_ts::date AS production_day,
       round(100.0 * count(*) FILTER (WHERE status='complete') / count(*),2) AS first_pass_yield_pct
FROM fact_station_event GROUP BY 1 ORDER BY 1;

-- 10. Find station-specific vehicle rework counts
SELECT vehicle_id, station_id, count(*) AS rework_events
FROM fact_station_event WHERE status='rework'
GROUP BY vehicle_id, station_id ORDER BY rework_events DESC;
