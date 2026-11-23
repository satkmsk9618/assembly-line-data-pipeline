# Assembly Line Data Pipeline

[![CI](https://github.com/satkmsk9618/assembly-line-data-pipeline/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/satkmsk9618/assembly-line-data-pipeline/actions/workflows/ci.yml)

I built this project to practice an end-to-end data engineering workflow for a simulated vehicle assembly line. It creates imperfect machine-style exports, cleans and analyzes station events, stores history in PostgreSQL, and displays production and quality metrics in Streamlit.

I chose an assembly-line scenario because it brings together event processing, quality checks, operational metrics, and historical reporting in one project. All production events are synthetic; the dashboard is a demonstration and is not connected to factory equipment or a public live production feed.

**Hosted dashboard:** [Open the Streamlit app](https://dashboardpy-ccqdte4aobbtrah4pw3u6z.streamlit.app/)

**Repository:** [satkmsk9618/assembly-line-data-pipeline](https://github.com/satkmsk9618/assembly-line-data-pipeline)

## Quick start

Requirements: Git and Docker Desktop with Docker Compose.

```bash
git clone https://github.com/satkmsk9618/assembly-line-data-pipeline.git && cd assembly-line-data-pipeline
cp .env.example .env
docker compose up --build -d
```

Open the dashboard at <http://localhost:8501>. The FastAPI docs are at <http://localhost:8000/docs>. The simulator writes synthetic events to PostgreSQL every 15 seconds. To run the batch CSV pipeline too, follow [Run the batch ETL](#run-the-batch-etl).

## Results from a reproducible sample run

With `--vehicles 1000 --seed 7`, the batch ETL read **5,024 raw station rows**, kept **4,972 cleaned rows**, and excluded **52 rows** from the clean output, including **23 exact duplicates**. The sample covered **1,000 vehicles** across five stations, with a **6.99-minute average cycle time** against an 8-minute takt target and **86.1% first-pass yield**. These are results from this seeded synthetic batch, not live factory performance.

## What it does

- Generates station, defect, and downtime records, including duplicates, missing timestamps, shuffled events, and invalid cycle times.
- Uses Pandas to parse timestamps, remove duplicate events, reject unusable rows, calculate cycle time, and produce a run audit.
- Loads cleaned records into a PostgreSQL dimensional model and retains historical records across loads.
- Exposes summary, trend, station, quality, and downtime metrics through FastAPI.
- Displays throughput, cycle time against an 8-minute takt target, station performance, rework, defects, and downtime in Streamlit.
- Lets users view recent windows, select **All time** for stored records, or choose a date range in Historical view.
- Supports date-filtered history, optional Supabase email/password or Google sign-in, downloadable PDF reports, and opt-in daily report emails.

## Skills and ideas I practiced

I built this project to get hands-on practice with the full path from imperfect machine-style exports to useful operational reporting. The simulated data lets me explore how ETL, SQL, data quality, dashboards, and documentation fit together without relying on access to a real production system.

| Project area | What I implemented |
|---|---|
| ETL and data preparation | A repeatable Python/Pandas flow generates raw exports, cleans station events, calculates metrics, and loads PostgreSQL. |
| SQL and relational data | PostgreSQL facts and dimensions, analytical query examples, date-filtered history, and a documented `EXPLAIN ANALYZE` exercise. |
| Data quality | The generator includes duplicates, missing timestamps, shuffled rows, and invalid cycle times. The transform removes duplicates, rejects invalid station events, and reports row counts. |
| Dashboards and documentation | Streamlit views surface takt misses, cycle time, rework, defects, and downtime. The repository documents the data model, dashboard, setup, and data flow. |
| Backend and frontend | FastAPI serves dashboard metrics; Streamlit provides the interactive user interface. |
| Version control and automated checks | GitHub hosts the code; pytest and GitHub Actions provide repeatable checks. |

I’m continuing to build out monitoring and troubleshooting. The project currently has pipeline audit counts, application logging, an API health endpoint, and automated tests. It does **not** yet include a Splunk deployment, freshness or volume anomaly alerts, or a full validation-monitoring layer. Those are possible next steps, along with a tested prompt-driven query assistant. Project planning and technical notes currently live in GitHub Projects and `/docs`.

## How the pieces fit together

```mermaid
flowchart LR
    subgraph Batch[Batch ETL]
        A[Python data generator] --> B[Raw CSV files]
        B --> C[Pandas ETL: clean station events and calculate metrics]
        C --> D[Processed CSV files and metrics JSON]
        D --> E[Database loader]
    end
    subgraph Live[Separate simulated feed]
        F[15-second event simulator]
    end
    E --> G[(PostgreSQL history)]
    F --> G
    subgraph Local[Local Docker Compose]
        G --> H[FastAPI metrics endpoints]
        H --> I[Streamlit dashboard]
    end
    subgraph Hosted[Hosted app with DATABASE_URL]
        G --> J[In-app metric functions]
        J --> K[Streamlit dashboard]
        L[Hosted simulator thread] --> G
    end
    M[Session preview simulator] --> K
    N[Supabase Auth, optional] --> K
    G --> O[Daily report workflow]
    O --> P[PDF email]
```

The diagram shows two data-ingestion paths. The batch ETL generates raw CSV files, cleans station-event records with Pandas, writes processed files and a metrics report, then loads the records into PostgreSQL. Defect and downtime CSVs are currently extracted and loaded, but receive less cleaning than station events. Separately, the 15-second simulator creates new events and writes them directly to PostgreSQL; it does not pass through the batch CSV-cleaning steps. In Docker Compose, that simulator is a separate service. In the hosted database mode, it runs as a background thread while the app is active.

The dashboard connection depends on where it runs. Locally, Streamlit requests metrics from FastAPI. In the hosted app with `DATABASE_URL` configured and `API_URL` unset, Streamlit calls the same metric functions in-process, and those functions query PostgreSQL directly. Without a database connection, the hosted preview uses session-local simulated data and has no persistent history. Recent-window auto-refresh starts paused; **All time** turns it on automatically so new stored batches appear every 15 seconds.

PostgreSQL is the history store. The dashboard’s Historical view queries that stored data for a selected date range. History begins accumulating after a database connection is configured; session-only preview events are not backfilled into PostgreSQL.

## Technologies

| Area | Tools | How I use them |
|---|---|---|
| Data generation and ETL | Python, Pandas | Generate repeatable CSV exports, clean event records, calculate metrics, and report rejected/duplicate counts. |
| Storage and modeling | PostgreSQL, SQL | Store station events and related dimensions/facts, preserve history, and support analytical queries. |
| API | FastAPI, Uvicorn | Provide health and dashboard metric endpoints backed by PostgreSQL. |
| Dashboard | Streamlit, Altair | Build the interactive line, quality, station, and downtime views. |
| Reports and accounts | ReportLab, Supabase Auth | Create PDF summaries and optionally authenticate users for report preferences. |
| Local environment | Docker Compose | Start PostgreSQL, the API, simulator, and dashboard together. |
| Quality checks | pytest, GitHub Actions | Run unit tests locally and automatically on pushes and pull requests. |

## Run locally

### Requirements

- Git
- Docker Desktop with Docker Compose
- Python 3.11 or newer for the CLI and tests

### Start the dashboard stack

The [Quick start](#quick-start) commands launch the services. Wait for them to become healthy, then open:

- Dashboard: <http://localhost:8501>
- FastAPI interactive docs: <http://localhost:8000/docs>
- PostgreSQL: `localhost:5433` (the Compose port; the container listens on 5432)

The first database start applies `sql/schema.sql`. The local simulator begins adding synthetic records every 15 seconds. Recent-window dashboard auto-refresh starts paused; **All time** refreshes automatically every 15 seconds so it picks up new records. Use the sidebar switch to pause it or click **Refresh dashboard now** to query the newest rows manually.

### Run the batch ETL

The batch CLI generates a reproducible sample, cleans it, and loads it into the PostgreSQL database. In a second terminal opened at the repository root, create a Python environment and install the project:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dashboard,dev]'
assembly-line generate --vehicles 1000 --seed 7
assembly-line run
assembly-line load
```

On Windows PowerShell, activate the environment with `.\.venv\Scripts\Activate.ps1`. The generator writes to `data/raw/`; the cleaning step writes cleaned files and `metrics.json` under `data/processed/`. These generated data files are ignored by Git so each person can create their own sample.

The loader appends records and skips event keys it has already loaded. To stop the local services, run `docker compose down`. To remove the local database and its stored history as well, run `docker compose down -v`.

## Hosted Streamlit setup

The public demo can run in session-only preview mode without PostgreSQL. To enable persistent history, configure the app’s private Streamlit secrets with a PostgreSQL `DATABASE_URL` (Supabase PostgreSQL works). Leave `API_URL` unset for the hosted database mode. Run `sql/schema.sql` in the database before connecting it.

Optional email/password and Google sign-in use `SUPABASE_URL` and `SUPABASE_ANON_KEY`. Google OAuth also needs a Google OAuth client configured in Supabase Auth and matching redirect URLs; the setup guide includes the steps. Do not put the database password, Supabase service-role key, Google Client Secret, or SMTP password in this README or commit them to Git. Keep private values in the service settings described in [the account, history, and daily report guide](docs/daily-report.md).

To deploy or update the dashboard, connect this repository to [Streamlit Community Cloud](https://share.streamlit.io/) and choose branch `main` and main file `src/assembly_line/dashboard.py`. New commits to `main` are then available for the app to deploy.

## Data model and metrics

The main fact tables store station events, quality defects, and downtime. Dimension tables describe stations, shifts, and defect types. See [`sql/schema.sql`](sql/schema.sql) and the [data dictionary](docs/data-dictionary.md) for column details.

In Supabase, `report_preference.user_id` is a UUID foreign key to `auth.users.id`; deleting an Auth account removes its email-report preference. Existing Supabase projects can apply [`sql/migrations/20261123_report_preference_auth_fk.sql`](sql/migrations/20261123_report_preference_auth_fk.sql) to add the relationship. Local Docker PostgreSQL does not include Supabase's `auth` schema, so the FK is added conditionally there.

- **Cycle time:** `end_ts - start_ts`, in minutes for one station event.
- **Takt deviation:** event cycle time minus the configured target, which defaults to 8 minutes. A positive deviation means the event took longer than target.
- **First-pass yield:** vehicles with complete records at all observed stations and no rework, divided by the vehicles in scope.
- **Station to investigate:** a screening indicator based on station cycle-time and over-takt counts. It points to a place to investigate; it does not prove a production bottleneck.
- **OEE-style quality proxy:** the current quality percentage uses first-pass yield. Full OEE is not claimed because the simulator does not provide all scheduled-time and ideal-rate inputs needed for availability and performance.

## SQL, testing, and documentation

[`sql/analytics.sql`](sql/analytics.sql) contains analytical query examples, including aggregations and window-function patterns. The measurement guide in [`docs/sql-performance.md`](docs/sql-performance.md) explains how to compare plans with `EXPLAIN (ANALYZE, BUFFERS)`. I have not claimed a query speedup without recording a reproducible benchmark.

Run the test suite with:

```bash
pytest
```

GitHub Actions runs the tests on pushes and pull requests. Project notes include the [architecture](docs/architecture.md), [dashboard guide](docs/dashboard.md), [data dictionary](docs/data-dictionary.md), [troubleshooting notes](docs/version-1-troubleshooting.md), and [project board](docs/project-board.md).

## Trade-offs and next steps

I chose Pandas and Streamlit to keep the transformation and dashboard code understandable while still using production-relevant tools. PostgreSQL provides a real store for history, while Docker Compose makes the local services easier to start together. The simulated records make the project self-contained but cannot represent every behavior of real manufacturing data.

The current dataset is small, so indexes and partitioning are learning exercises rather than evidence of high-volume performance. A next step is to generate a larger benchmark dataset and record query plans and timings. Other improvements include adding a quarantine table for rejected records, expanding shift/station filters, and calculating full OEE once the required source fields exist.
