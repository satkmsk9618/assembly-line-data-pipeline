# Dashboard guide

For a quick hosted preview, open the project app on Streamlit Community Cloud. With no database configured, a session-local simulator produces synthetic events. The preview is session-local and cannot be queried as saved past-day history.

To keep hosted history, add a private PostgreSQL `DATABASE_URL` to the Streamlit app's secrets. The hosted simulator then writes one shared synthetic stream to PostgreSQL every 15 seconds. In **Recent**, choose a recent window or **All time** to query all records in the database. In **Historical**, choose inclusive start and end dates. Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to show verified email/password and Google sign-in. The detailed PDF download covers whichever reporting window is selected.

For the full local architecture, start Docker Compose and open <http://localhost:8501>. Its simulator writes demo events to PostgreSQL, and the dashboard retrieves metrics through FastAPI. Dashboard auto-refresh is paused by default to keep the page accessible; use **Refresh dashboard now** to fetch the latest rows, or turn on the 15-second auto-refresh. The dashboard can inspect recent windows, all stored records, or historical dates.

The dashboard calls the live summary, throughput trend, station health, quality, and downtime endpoints on FastAPI. The overview compares station average and 90th percentile cycle times with the 8-minute takt target, flags stations with takt misses, and reports rework. Quality shows a defect Pareto and severity breakdown, with the top defect called out. Downtime shows minutes by reason and station, with the largest stop called out. If the feed appears stale, confirm the `simulator` container is running with `docker compose ps`; if the API is unavailable, check <http://localhost:8000/health>.

The charts point to areas to investigate, not root causes. All streamed records are synthetic. To use real line data, a machine or historian connection and its approved data contract still need to be provided. The optional daily report is sent only after a signed-in account opts in; it summarizes stored records for the previous local calendar day and includes a PDF attachment.
