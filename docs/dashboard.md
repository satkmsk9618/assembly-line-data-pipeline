# Dashboard guide

Open <http://localhost:8501> after the services are running and after loading data. The dashboard refreshes its metrics every 15 seconds. Use the sidebar to filter by station, shift, and (optionally) date range. The top cards show unique vehicles, station-event count, average cycle time, and first-pass yield. The bar chart orders average cycle time by station; the table also shows event and rework counts.

The dashboard calls `/dimensions`, `/metrics/summary`, and `/metrics/stations` on the FastAPI service. If there are no database rows yet, load a dataset. If the API is unavailable, confirm the Compose services are healthy and check <http://localhost:8000/health>.

The chart flags candidates, not root causes. A useful next improvement is to compare stations across matching date ranges and shift mixes, so the chart is less affected by changes in the production mix.
