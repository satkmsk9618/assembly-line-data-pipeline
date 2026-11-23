# Project board

Live board: [Assembly Line Data Pipeline](https://github.com/users/satkmsk9618/projects/2). The board is currently private to the account owner and contains draft tickets. The available statuses are Todo, In Progress, and Done. Keep each pull request small enough to explain in a few sentences.

| Ticket | Acceptance check |
|---|---|
| Generate simulated exports | Seed and vehicle count are configurable, and three raw files are produced |
| Clean station events | Duplicate, missing, and non-positive rows are counted and excluded |
| Calculate line metrics | Cycle time, takt deviation, FPY, and bottleneck candidate are reported |
| Create dimensional schema | Dimensions and event, defect, downtime facts initialize with Docker |
| Load processed data | A repeat load replaces demo facts atomically |
| Add metrics API | Health, summary, and station endpoints return JSON |
| Create dashboard | Cards and station chart display API data |
| Write analytical SQL | Ten examples include CTEs, aggregation, and windows |
| Measure a query | Before/after plans and timings are recorded with the dataset context |
| Add tests and CI | Pytest runs locally and in GitHub Actions |
| Email daily line report | Scheduled workflow creates a recent 24-hour synthetic report and emails it over configured SMTP |
| Document the project | Data dictionary, flow, setup, dashboard, and trade-offs are explained |

For each pull request, describe the project change, how it was checked, and one trade-off. Ask a peer to review when possible. If self-reviewing, label it as self-review.
