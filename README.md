# Assembly Line Data Pipeline and Dashboard

I built an end-to-end pipeline that turns messy simulated assembly-line exports into production metrics and a live dashboard. The records are generated for this project; there is no real factory data feed.

## What this project does

1. Generates station events, quality defects, and downtime CSV exports.
2. Cleans duplicate, missing, and invalid station rows with Pandas.
3. Calculates cycle time, takt deviation, first-pass yield, and station bottleneck candidates.
4. Loads the cleaned data into PostgreSQL tables arranged as a small star schema.
5. Serves read-only metrics through FastAPI and displays them in Streamlit.
6. Can email a daily summary of a fresh, simulated 24-hour sample through GitHub Actions.

## Hosted dashboard

The Streamlit Community Cloud entrypoint is `src/assembly_line/dashboard.py`. Without an `API_URL`, it runs a self-contained demo simulator in the viewer's Streamlit session and refreshes its charts every 15 seconds. This hosted mode needs no local Docker setup, database, API credentials, or secrets. Its sample records are synthetic and session-local; they are not shared with the PostgreSQL database used by the Docker deployment.

The [daily email report](docs/daily-report.md) runs separately from the Streamlit viewer. It generates a new synthetic sample once a day and emails the same project metrics; configure SMTP credentials as GitHub repository secrets.

To deploy it, connect the public GitHub repository to [Streamlit Community Cloud](https://share.streamlit.io/), select branch `main` and file `src/assembly_line/dashboard.py`, then deploy. Streamlit Cloud reads the pinned dashboard dependencies from `requirements.txt`. The local Docker Compose setup remains available below when you want to inspect the ETL files, PostgreSQL schema, and FastAPI service.

## Run it locally

I tested this project on macOS with Docker Desktop and Python 3.13. Python 3.11 or newer and Docker Compose are required. Start Docker Desktop first, then open Terminal and run the commands from the repository folder. If you have not cloned the project yet:

```bash
git clone https://github.com/satkmsk9618/assembly-line-data-pipeline.git
cd assembly-line-data-pipeline
```

Then set up the database and Python environment:

```bash
cp .env.example .env
docker compose up --build -d
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dashboard,dev]'
```

The live demo stream starts automatically with Docker Compose and appends a new simulated vehicle every 15 seconds. The dashboard also refreshes every 15 seconds. You can open it immediately. The following optional batch commands generate a larger reproducible sample and load it into PostgreSQL:

```bash
assembly-line generate --vehicles 1000 --seed 7
assembly-line run
assembly-line load
```

On Windows PowerShell, create the environment with `py -m venv .venv` and activate it with `.\.venv\Scripts\Activate.ps1`, then run the same pip and `assembly-line` commands. Keep the terminal in the repository folder for every step; the project files such as `.env.example`, `docker-compose.yml`, and `pyproject.toml` are there.

Open the dashboard at <http://localhost:8501> and the interactive API docs at <http://localhost:8000/docs>. The dashboard refreshes every 15 seconds and includes recent throughput, cycle time versus takt, station rework, defect Pareto, and downtime views. The database initializes from `sql/schema.sql` on its first start. `docker compose down` stops the services. `docker compose down -v` also deletes the demo database and its data.

The files in `data/raw/` are ignored by Git because they are generated. To keep a source checkout light, regenerate them with the command above. You can use `--vehicles` to change the sample size and `--seed` to make a repeatable alternative sample.

Compose publishes PostgreSQL on `localhost:5433` so it can run alongside a local PostgreSQL installation that already uses port 5432. If you change `POSTGRES_HOST_PORT` in `.env`, update the port in `DATABASE_URL` to match.

## What went wrong in my first run

I hit a few setup problems while trying the first version. Writing them down helped me separate the actual code bug from the commands that were run in the wrong place.

| What I saw | Why it happened | What changed |
|---|---|---|
| `ValueError: Invalid isoformat string: ''` during `generate` | My test-data generator intentionally blanked a timestamp and also tried to use that same row to make a negative cycle. It tried to parse the blank value as a date. | The negative-cycle fault is now added only when the start timestamp exists. A one-vehicle regression test covers this overlap. |
| `Expected raw station file: data/raw/station_events.csv` and then a missing processed CSV | These were follow-on errors: generation had stopped before writing the raw files, so cleaning and loading had nothing to read. | After generation succeeds, run the three pipeline commands in order: `generate`, `run`, then `load`. |
| Docker could not connect to `docker.sock` | Docker Desktop was not running yet, so Compose could not reach the Docker service. | Start Docker Desktop, wait until it says it is running, then run `docker compose up --build -d`. |
| Port `5432` was already in use | PostgreSQL was already running locally on my Mac on that port. | Compose now publishes its database on port `5433`. The sample `.env` points the local loader to the same port. |
| `.env.example`, Compose, or Python project files were “not found” | I ran setup commands from `Downloads` instead of from the cloned repository. | Clone the repo, `cd assembly-line-data-pipeline`, and run the setup commands there. |

After applying the fixes, I ran the pipeline with the documented seed and 1,000 vehicles. It generated 5,024 raw station rows, kept 4,972 clean rows, rejected 52 invalid rows, and removed 23 duplicates. The 4,972 clean station events loaded into PostgreSQL. I also checked the API summary and station endpoints; the dashboard and API services were running in Compose. These are results from my local sample run, not a claim about millions of records or a measured query speedup.

For more help, see [the troubleshooting notes](docs/version-1-troubleshooting.md).

## Follow one row through the pipeline

Start with `station_events.csv`. Each record reports a vehicle, station, start and end timestamp, shift, and status. The generator shuffles the records as if machine exports arrived out of order and occasionally duplicates records or removes timestamps. `transform.clean_events` parses timestamps, calculates cycle time in minutes, removes exact duplicate keys, and rejects missing timestamps and cycles of zero or less. It returns row counts so the pipeline report explains what changed.

The valid records are sorted by event time, station, and vehicle and saved under `data/processed/`. The summary is written to `metrics.json`. `assembly-line load` then replaces the demonstration facts inside one database transaction. This is deliberately simple and repeatable; a production pipeline would use incremental upserts, a load identifier, and a separate quarantine table.

## Metric definitions and assumptions

- **Cycle time:** `end_ts - start_ts`, measured in minutes for one station event.
- **Takt deviation:** station-event cycle time minus the configured takt target (8 minutes by default). Positive means slower than takt.
- **First-pass yield:** vehicles whose station records are all marked `complete`, divided by all vehicles in scope. A single `rework` station means that vehicle did not pass the line first time.
- **Bottleneck candidate:** station with the highest average cycle time in the selected data. This is an investigation lead, not proof of a constraint; mix, shift, and downtime can affect the average.
- **OEE-style metric:** the initial quality proxy equals the first-pass percentage. True OEE needs scheduled time, ideal cycle time, and good output, so availability and performance are not claimed yet.

## Repository map

```text
src/assembly_line/   generator, transform, loader, simulator, API, dashboard, CLI
sql/schema.sql       PostgreSQL dimensions, facts, indexes, date partition
sql/analytics.sql    ten analytical query examples
docs/                data dictionary, architecture, dashboard, SQL measurement guide
tests/               small deterministic unit tests for transformations
.github/workflows/   GitHub Actions test workflow
```

## Engineering choices and trade-offs

- Python and Pandas keep the transformations readable for a first data-engineering project.
- PostgreSQL makes the dimensional model and analytical SQL concrete.
- One annual time partition plus a default partition demonstrates pruning while keeping the sample easy to load. At only thousands of rows, partitioning may not improve speed; query plans decide whether it helps.
- The loader replaces the demo facts transactionally. It is easy to rerun but unsuitable for a continuously running factory feed.
- The API exposes health, filter-dimension, summary, and station ranking endpoints. Summary and station results can be filtered by date range, station, and shift.
- The dashboard refreshes every 15 seconds and shows throughput, takt misses, station rework, defect Pareto, and downtime.
- A small simulator service appends clearly marked demo events every 15 seconds. It keeps the dashboard active without a real factory connection.

## SQL performance exercise

Start Postgres, load the generated sample, and run selected queries from `sql/analytics.sql` with `EXPLAIN (ANALYZE, BUFFERS)`. Save the output, dataset row count, PostgreSQL version, and timings in `docs/sql-performance.md`. Compare a date-filtered query before and after dropping/recreating its supporting index on a disposable local database. Never invent speedup numbers: with a small sample, the sequential scan may be faster and timings can be dominated by noise. See the measurement guide for a reproducible approach and caveats.

## Tests and CI

The repository includes pytest checks for core cleaning, metric behavior, and the hosted simulator. Run `pytest` locally. GitHub Actions runs the same test suite on pushes and pull requests.

## Pull request practice and project board

Use a short branch for each feature, open a pull request, and write a review checklist even when reviewing your own work. The [GitHub Project board](https://github.com/users/satkmsk9618/projects/2) tracks the features; its tickets and status are described in `docs/project-board.md`. The board is currently private to the account owner. A self-review is useful practice but should be described honestly as self-review.

## What I learned / next steps

This project makes assumptions visible: a metric is only meaningful when its input and denominator are clear. Next improvements are a bad-row quarantine file, a proper availability/performance OEE calculation, configurable date and shift filters, incremental loading, and a benchmark using a larger generated dataset. The measured runtime and record count should be added to a CV only after collecting them on a documented run.
