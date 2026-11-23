# SQL performance lab

There is intentionally no claimed speedup in this starter: no benchmark has been run yet. Capture actual measurements before adding a CV result.

1. Generate a fixed sample, record the vehicle count and resulting fact row count, then load it.
2. Select one representative query in `sql/analytics.sql`. Prefer a date-range query, because it can benefit from the `start_ts` index and partition pruning.
3. Run `EXPLAIN (ANALYZE, BUFFERS)` and save the full plan, PostgreSQL version, row count, and elapsed time.
4. On a disposable local database, compare with the relevant index absent, then present. Recreate the database between comparisons so cached plans and stale data do not mislead you. Do not drop indexes on a shared database.
5. Repeat each case several times and report a median. Keep machine, Docker resource limits, dataset seed, and command fixed.
6. Inspect whether the plan actually uses an index or prunes a partition. On small tables, a sequential scan is often the sensible choice.

The default schema adds indexes for event start/end time, station plus time, shift plus status, defect record time, and station-based defect/downtime lookups. The event fact has a yearly range partition and a default partition. These are teaching examples: an index has write/storage cost, and partitioning is most useful when large tables are commonly filtered by the partition key.

Record results in this format:

| Query | Rows | Index state | Median execution time | Plan observation |
|---|---:|---|---:|---|
| Date range by station | Fill after measurement | no index / index | Fill after measurement | scan or index, buffers |
