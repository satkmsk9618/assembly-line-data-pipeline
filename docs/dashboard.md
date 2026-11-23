# Dashboard guide

Open <http://localhost:8501> after Docker Compose is running. The simulator begins writing recent demo events automatically, so the dashboard can show activity without first running the batch ETL. It refreshes every 5, 15, or 30 seconds and offers a 1, 6, or 24 hour view.

The dashboard calls the live summary, throughput trend, station health, quality, and downtime endpoints on FastAPI. The overview compares station average and 90th percentile cycle times with the 8-minute takt target, flags stations with takt misses, and reports rework. Quality shows a defect Pareto and severity breakdown, with the top defect called out. Downtime shows minutes by reason and station, with the largest stop called out. If the feed appears stale, confirm the `simulator` container is running with `docker compose ps`; if the API is unavailable, check <http://localhost:8000/health>.

The charts point to areas to investigate, not root causes. All streamed records are synthetic. To use real line data, a machine or historian connection and its approved data contract still need to be provided.
