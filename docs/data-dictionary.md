# Data dictionary

All timestamps are ISO-8601 strings in raw exports and UTC-aware `TIMESTAMPTZ` values in PostgreSQL. The generator's seed and size are command-line options.

## Raw machine exports

| File | Field | Meaning |
|---|---|---|
| `station_events.csv` | `vehicle_id` | Simulated vehicle key, such as `V-000001` |
| | `station_id` | Workstation key, such as `ST-01` |
| | `start_ts`, `end_ts` | Start and end of one station operation |
| | `operator_shift` | `day`, `swing`, or `night` |
| | `status` | `complete` or `rework` |
| `quality_defects.csv` | `defect_type` | Simulated defect category |
| | `severity` | `low`, `medium`, or `high` |
| | `rework_flag` | Whether the defect led to rework in the simulated record |
| | `recorded_ts` | Time the defect was recorded |
| `downtime_events.csv` | `station_id` | Station where the interruption occurred |
| | `start_ts`, `end_ts` | Interruption interval |
| | `reason_code` | `jam`, `maintenance`, `material_wait`, or `changeover` |

The generator introduces duplicate station rows, missing timestamps, negative cycle times, and shuffled arrival order. The transformation currently rejects missing or non-positive cycles and removes exact station event duplicates. It preserves defect and downtime rows as delivered. Extending their validation is a planned improvement.

## PostgreSQL model

| Table | Grain | Important fields |
|---|---|---|
| `dim_station` | One row per station | `station_id` primary key |
| `dim_shift` | One row per shift name | `shift_id`, unique `shift_name` |
| `dim_defect` | One row per defect type | `defect_id`, unique `defect_type` |
| `fact_station_event` | One cleaned vehicle visit to one station | `vehicle_id`, station/shift keys, timestamps, cycle time, status |
| `fact_defect` | One defect record | vehicle, station/defect keys, severity, rework flag, recorded timestamp |
| `fact_downtime` | One downtime interval | station, timestamps, reason code |

The event fact is partitioned by `start_ts`. The 2026 partition covers the generated sample and the default partition accepts other years. Its primary key includes the partition key, as PostgreSQL requires for partitioned unique constraints.

### Relationships

- `fact_station_event.station_id` → `dim_station.station_id`
- `fact_station_event.shift_id` → `dim_shift.shift_id`
- `fact_defect.station_id` → `dim_station.station_id`
- `fact_defect.defect_id` → `dim_defect.defect_id`
- `fact_downtime.station_id` → `dim_station.station_id`
- `report_preference.user_id` → Supabase `auth.users.id` (on hosted Supabase only)

`vehicle_id` is a degenerate identifier stored on the facts. There is no separate vehicle dimension in this demo. Defect and downtime records are separate fact tables and join to station/defect dimensions, rather than directly to a station-event row. The event partition children inherit the parent fact's keys and constraints. The report-preference foreign key is added by `sql/migrations/20261123_report_preference_auth_fk.sql`. Run that migration in the Supabase SQL Editor to see the Auth relationship in the schema diagram. A public-schema-only diagram may still omit the referenced `auth.users` table because it belongs to Supabase's `auth` schema.
