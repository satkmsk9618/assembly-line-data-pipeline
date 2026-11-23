# Dashboard guide

For the hosted demo, open the project app on Streamlit Community Cloud. It runs without a local database: a session-local simulator generates synthetic events and appends a vehicle every 15 seconds. The dashboard also refreshes every 15 seconds and offers a 1, 6, or 24 hour view. The hosted sample data is separate for each viewer session.

For the full local architecture, start Docker Compose and open <http://localhost:8501>. Its simulator writes recent demo events to PostgreSQL, and the dashboard retrieves metrics through FastAPI. This mode lets me inspect the ETL files, database schema, and API as well as the dashboard.

The dashboard calls the live summary, throughput trend, station health, quality, and downtime endpoints on FastAPI. The overview compares station average and 90th percentile cycle times with the 8-minute takt target, flags stations with takt misses, and reports rework. Quality shows a defect Pareto and severity breakdown, with the top defect called out. Downtime shows minutes by reason and station, with the largest stop called out. If the feed appears stale, confirm the `simulator` container is running with `docker compose ps`; if the API is unavailable, check <http://localhost:8000/health>.

The charts point to areas to investigate, not root causes. All streamed records are synthetic. To use real line data, a machine or historian connection and its approved data contract still need to be provided.
