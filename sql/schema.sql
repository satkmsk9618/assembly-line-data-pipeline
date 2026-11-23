CREATE TABLE IF NOT EXISTS dim_station (
    station_id TEXT PRIMARY KEY,
    station_name TEXT
);
CREATE TABLE IF NOT EXISTS dim_shift (
    shift_id BIGSERIAL PRIMARY KEY,
    shift_name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_defect (
    defect_id BIGSERIAL PRIMARY KEY,
    defect_type TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_station_event (
    event_id BIGSERIAL,
    vehicle_id TEXT NOT NULL,
    station_id TEXT NOT NULL REFERENCES dim_station(station_id),
    shift_id BIGINT NOT NULL REFERENCES dim_shift(shift_id),
    start_ts TIMESTAMPTZ NOT NULL,
    end_ts TIMESTAMPTZ NOT NULL,
    cycle_time_minutes NUMERIC(8,2) NOT NULL CHECK (cycle_time_minutes > 0),
    status TEXT NOT NULL,
    PRIMARY KEY (event_id, start_ts)
) PARTITION BY RANGE (start_ts);
-- One yearly partition is enough for the demo. The default catches other dates.
CREATE TABLE IF NOT EXISTS fact_station_event_2026 PARTITION OF fact_station_event
    FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');
CREATE TABLE IF NOT EXISTS fact_station_event_default PARTITION OF fact_station_event DEFAULT;
CREATE TABLE IF NOT EXISTS fact_defect (
    defect_event_id BIGSERIAL PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    station_id TEXT NOT NULL REFERENCES dim_station(station_id),
    defect_id BIGINT NOT NULL REFERENCES dim_defect(defect_id),
    severity TEXT NOT NULL,
    rework_flag BOOLEAN NOT NULL DEFAULT FALSE,
    recorded_ts TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- Also upgrade existing local demo volumes when this schema is applied again.
ALTER TABLE fact_defect ADD COLUMN IF NOT EXISTS recorded_ts TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
UPDATE fact_defect AS d SET recorded_ts = e.last_event_ts
FROM (SELECT vehicle_id, station_id, max(end_ts) AS last_event_ts
      FROM fact_station_event GROUP BY vehicle_id, station_id) AS e
WHERE d.vehicle_id = e.vehicle_id AND d.station_id = e.station_id;
CREATE TABLE IF NOT EXISTS fact_downtime (
    downtime_id BIGSERIAL PRIMARY KEY,
    station_id TEXT NOT NULL REFERENCES dim_station(station_id),
    start_ts TIMESTAMPTZ NOT NULL,
    end_ts TIMESTAMPTZ NOT NULL,
    reason_code TEXT NOT NULL
);

-- Support common date-range filters and station aggregations.
CREATE INDEX IF NOT EXISTS ix_event_start_ts ON fact_station_event (start_ts);
CREATE INDEX IF NOT EXISTS ix_event_end_ts ON fact_station_event (end_ts);
CREATE INDEX IF NOT EXISTS ix_event_station_start ON fact_station_event (station_id, start_ts);
CREATE INDEX IF NOT EXISTS ix_event_shift_status ON fact_station_event (shift_id, status);
CREATE INDEX IF NOT EXISTS ix_defect_station ON fact_defect (station_id);
CREATE INDEX IF NOT EXISTS ix_defect_recorded_ts ON fact_defect (recorded_ts);
CREATE INDEX IF NOT EXISTS ix_downtime_station_start ON fact_downtime (station_id, start_ts);
CREATE INDEX IF NOT EXISTS ix_downtime_end_ts ON fact_downtime (end_ts);

-- Keep successive simulator/ETL loads as history rather than replacing the table.
CREATE UNIQUE INDEX IF NOT EXISTS ux_event_vehicle_station_time
    ON fact_station_event (vehicle_id, station_id, start_ts);
CREATE UNIQUE INDEX IF NOT EXISTS ux_defect_natural_key
    ON fact_defect (vehicle_id, station_id, defect_id, recorded_ts);
CREATE UNIQUE INDEX IF NOT EXISTS ux_downtime_natural_key
    ON fact_downtime (station_id, start_ts, end_ts, reason_code);

-- The Streamlit server uses the verified Supabase Auth user ID to store one
-- personal email preference. No password or SMTP credential is stored here.
CREATE TABLE IF NOT EXISTS report_preference (
    user_id UUID PRIMARY KEY,
    report_email TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    send_hour SMALLINT NOT NULL DEFAULT 9 CHECK (send_hour BETWEEN 0 AND 23),
    opted_in BOOLEAN NOT NULL DEFAULT FALSE,
    last_sent_local_date DATE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Link preferences to Supabase Auth when this schema is installed there.
-- Local Docker PostgreSQL does not include the Supabase auth schema.
ALTER TABLE report_preference
    ALTER COLUMN user_id TYPE UUID USING user_id::uuid;
DO $$
BEGIN
    IF to_regclass('auth.users') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conrelid = 'public.report_preference'::regclass
             AND conname = 'report_preference_user_id_fkey'
       ) THEN
        EXECUTE 'ALTER TABLE public.report_preference
                 ADD CONSTRAINT report_preference_user_id_fkey
                 FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE';
    END IF;
END $$;
