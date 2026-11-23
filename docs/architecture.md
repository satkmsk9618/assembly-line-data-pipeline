# Architecture and data flow

```mermaid
flowchart LR
  subgraph Batch[Batch ETL]
    A[Python generator] -->|raw CSV exports| B[data/raw]
    B --> C[Pandas ETL: clean station events and calculate metrics]
    C -->|processed CSVs and metrics JSON| D[data/processed]
    D --> L[Database loader]
  end
  subgraph Feed[Separate simulated feed]
    H[15-second simulator]
  end
  L -->|append and deduplicate| E[(PostgreSQL history)]
  H --> E
  subgraph Local[Local Docker Compose]
    E --> F[FastAPI metrics endpoints]
    F --> G[Streamlit dashboard]
  end
  subgraph Hosted[Hosted app with DATABASE_URL]
    E --> M[In-process metric functions]
    M --> N[Streamlit dashboard]
    O[Background simulator thread] --> E
  end
  P[Session-local preview simulator] --> N
  Q[Optional Supabase Auth] --> G
  Q --> N
  E --> J[Daily report workflow]
  J -->|PDF email| K[Account email]
```

## Why these components?

- **Generator:** creates repeatable fake machine exports without external data access.
- **Pandas transform:** exposes the cleaning rules in a familiar table-oriented style. Station events get duplicate, timestamp, and cycle-time checks; defect and downtime CSVs currently receive less validation.
- **PostgreSQL:** stores facts separately from descriptive dimensions and runs analytical SQL.
- **FastAPI:** gives the local Compose dashboard a small metrics API. In hosted database mode, Streamlit calls the same metric functions in-process instead of making a network request to FastAPI.
- **Streamlit:** provides a quick visual layer without needing a separate JavaScript frontend.

The batch ETL and the live simulator are separate ingestion paths. The batch path generates CSV exports, cleans station events, writes processed files, and loads the database. The simulator writes new synthetic events directly to PostgreSQL every 15 seconds; it does not use the batch cleaning step. Docker Compose runs the simulator as its own service. In hosted database mode, the app starts a background simulator thread that saves to PostgreSQL while the app is active. Without a database connection, the hosted preview uses session-local simulated events that are not persistent. The dashboard can select stored history or filter past dates when PostgreSQL is configured. Recent-window auto-refresh is paused by default, and the All time view refreshes automatically every 15 seconds.

Daily email is opt-in per signed-in account. An hourly GitHub Actions run checks each saved time zone and send hour, summarizes the prior local calendar day from PostgreSQL, and attaches a PDF. The generated report does not invent a data sample when the database has no records.

I looked for a public live source before adding the simulator. I found a [public OPC UA test server with simulated bottling-line values](https://www.sondahub.com/opc-ua-test-server/), but it does not provide vehicle-assembly events with this project's defect and downtime fields. I kept the demo stream inside this repository so the schema stays consistent and the project can run without depending on an outside server.
