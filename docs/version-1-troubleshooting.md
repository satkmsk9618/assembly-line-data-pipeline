# Notes from my first local run

I built this project to practise a small data engineering workflow. My first attempt did not work from beginning to end, and the error messages looked like several separate problems. Most of the later file errors happened because the first command had already stopped.

## The generator bug

The generator intentionally creates messy records, including missing timestamps and negative cycle times. In the first version, the very first generated event matched both fault rules. The generator blanked its start timestamp, then immediately tried to parse that blank value to create a negative cycle. Python stopped with:

```text
ValueError: Invalid isoformat string: ''
```

I changed the negative-cycle rule to run only when the start timestamp is present. I also added a small test that generates one vehicle, because the first event is where the two fault rules overlap.

## Why the next two commands failed

`assembly-line run` reported that `data/raw/station_events.csv` was missing. `assembly-line load` then reported that the cleaned CSV was missing too. Those were cascading errors: generation had failed before it could write the raw data, so the later steps had no input. Once generation worked, I ran the commands in order and both later steps completed.

## Starting Docker and avoiding a port clash

I first saw a Docker socket error because Docker Desktop was not running. Starting Docker Desktop made the Docker service available.

After that, PostgreSQL could not bind to port `5432` because my Mac already had a local PostgreSQL server using it. I changed the Compose host port to `5433` and updated the example `.env` connection string to match. Inside Compose, the API still connects to the database on its normal container port, `5432`.

## Running commands from the right folder

Some setup commands were also tried from `Downloads`. That folder does not contain this project's `.env.example`, `docker-compose.yml`, or `pyproject.toml`, so the copy, Compose, and Python install commands could not work there. I now clone the repository and change into its folder before setup. The project URL by itself is not a shell command. `git clone` needs to come before it. If the destination folder already exists, I open that folder and update it instead of trying to clone over it.

## The working run I checked

With Docker Desktop running, I started the Compose services, created the virtual environment, installed the project, and ran:

```bash
assembly-line generate --vehicles 1000 --seed 7
assembly-line run
assembly-line load
```

The local run produced 5,024 raw station rows. Cleaning kept 4,972, rejected 52 rows with missing or invalid cycle times, and removed 23 duplicate events. PostgreSQL accepted all 4,972 cleaned events. The API health check returned `{"status":"ok"}`, and its summary endpoint returned 1,000 vehicles and 4,972 station events. I confirmed the dashboard and API containers were running.

These numbers describe one generated sample. I have not benchmarked SQL speedup or processed millions of records, so I would not put those claims on my CV yet. My next step is to collect repeatable query timings on a larger dataset.

## Quick troubleshooting checklist

- If Docker says it cannot connect to `docker.sock`, open Docker Desktop and wait for it to finish starting.
- If port `5433` is also busy, set `POSTGRES_HOST_PORT` in `.env` to another available port and change the port in `DATABASE_URL` to the same value.
- If the generator says a raw file is missing, run `assembly-line generate` first and check that the terminal is in the repository folder.
- If the loader cannot connect, confirm the database container is healthy with `docker compose ps` and that `.env` uses the same host port as Compose.
- To stop the demo services, run `docker compose down`. Add `-v` only when you also want to remove the demo database volume.

## Altair `TypedDict` crash on the hosted dashboard

The hosted app once failed when Streamlit tried to draw its first line chart. The traceback ended in Altair 5.5 with `TypeError: _TypedDictMeta.__new__() got an unexpected keyword argument 'closed'` on the Cloud Python 3.14 runtime. I pinned the app to Streamlit 1.67 and Altair 6.3, which supports that runtime, and added an import/version check to GitHub Actions. After the dependency update deploys, reload the app. No data reset is needed.
