# Architecture and data flow

```mermaid
flowchart LR
  A[Python generator] -->|raw CSV exports| B[data/raw]
  B --> C[Extract and clean with Pandas]
  C -->|clean CSV and metrics JSON| D[data/processed]
  D -->|transactional demo load| E[(PostgreSQL star schema)]
  H[Simulated event stream] --> E
  E --> F[FastAPI read-only metrics endpoints]
  F --> G[Streamlit dashboard]
  G -->|no API_URL in hosted app| H2[Session-local cloud simulator]
  H2 --> G
```

## Why these components?

- **Generator:** creates repeatable fake machine exports without external data access.
- **Pandas transform:** exposes the cleaning rules in a familiar table-oriented style.
- **PostgreSQL:** stores facts separately from descriptive dimensions and runs analytical SQL.
- **FastAPI:** keeps database access out of the dashboard and gives the UI a small API contract.
- **Streamlit:** provides a quick visual layer without needing a separate JavaScript frontend.

The batch ETL is still available so I can inspect raw and processed CSV files. Docker Compose starts a simulator that appends a vehicle's station events to PostgreSQL every 15 seconds; the dashboard refreshes at the same interval. The hosted Streamlit mode has no database or API dependency: each browser session keeps its own synthetic event stream and adds a vehicle every 15 seconds. Both modes are clearly labeled and neither connects to real factory equipment.

I looked for a public live source before adding the simulator. I found a [public OPC UA test server with simulated bottling-line values](https://www.sondahub.com/opc-ua-test-server/), but it does not provide vehicle-assembly events with this project's defect and downtime fields. I kept the demo stream inside this repository so the schema stays consistent and the project can run without depending on an outside server.
