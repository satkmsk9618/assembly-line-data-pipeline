# Assembly Line Data Pipeline and Dashboard

A portfolio project for learning how raw factory exports become trusted analytics. The factory is simulated: there is no real vehicle or production data. The project intentionally includes messy exports so the cleaning rules can be demonstrated and tested.

## What this project does

1. Generates station events, quality defects, and downtime CSV exports.
2. Cleans duplicate, missing, and invalid station rows with Pandas.
3. Calculates cycle time, takt deviation, first-pass yield, and station bottleneck candidates.
4. Loads the cleaned data into PostgreSQL tables arranged as a small star schema.
5. Serves read-only metrics through FastAPI and displays them in Streamlit.

## Run it locally

You need Docker Compose and Python 3.11 or newer. In the project folder:

```bash
cp .env.example .env
docker compose up --build -d
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -e '.[dashboard,dev]'
assembly-line generate --vehicles 1000 --seed 7
assembly-line run
assembly-line load
```

Open the dashboard at <http://localhost:8501> and the interactive API docs at <http://localhost:8000/docs>. The database initializes from `sql/schema.sql` on its first start. `docker compose down -v` removes the demo database and its data.

The files in `data/raw/` are ignored by Git because they are generated. To keep a source checkout light, regenerate them with the command above. You can use `--vehicles` to change the sample size and `--seed` to make a repeatable alternative sample.

Compose publishes PostgreSQL on `localhost:5433` so it can run alongside a local PostgreSQL installation that already uses port 5432. If you change `POSTGRES_HOST_PORT` in `.env`, update the port in `DATABASE_URL` to match.

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
src/assembly_line/   generator, transform, loader, API, dashboard, CLI
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
- The dashboard refreshes metrics every 15 seconds and keeps the metric definitions visible.

## SQL performance exercise

Start Postgres, load the generated sample, and run selected queries from `sql/analytics.sql` with `EXPLAIN (ANALYZE, BUFFERS)`. Save the output, dataset row count, PostgreSQL version, and timings in `docs/sql-performance.md`. Compare a date-filtered query before and after dropping/recreating its supporting index on a disposable local database. Never invent speedup numbers: with a small sample, the sequential scan may be faster and timings can be dominated by noise. See the measurement guide for a reproducible approach and caveats.

## Tests and CI

The repository includes pytest checks for core cleaning and metric behavior. Run `pytest` locally. GitHub Actions runs the same test suite on pushes and pull requests.

## Pull request practice and project board

Use a short branch for each feature, open a pull request, and write a review checklist even when reviewing your own work. The [GitHub Project board](https://github.com/users/satkmsk9618/projects/2) tracks the features; its tickets and status are described in `docs/project-board.md`. The board is currently private to the account owner. A self-review is useful practice but should be described honestly as self-review.

## What I learned / next steps

This project makes assumptions visible: a metric is only meaningful when its input and denominator are clear. Next improvements are a bad-row quarantine file, a proper availability/performance OEE calculation, configurable date and shift filters, incremental loading, and a benchmark using a larger generated dataset. The measured runtime and record count should be added to a CV only after collecting them on a documented run.
