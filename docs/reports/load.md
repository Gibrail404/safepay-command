# Local load test (generated; do not edit by hand)

Concurrent clients against a locally running API with PostgreSQL. Client and server run on the same laptop and share its CPU, so these numbers are conservative for the server and are **not** a prediction for a cloud deployment. Rate limiting was switched off for the test. Every request used a fresh idempotency key.

Machine: macOS-26.5.2-arm64-arm-64bit-Mach-O, 8 CPU cores, Python 3.14.7

## 1 server process

Each level ran for 8.0 seconds.

| Endpoint | Concurrent clients | Requests per second | Median (ms) | 95th percentile (ms) | 99th percentile (ms) | Failed requests |
|---|---|---|---|---|---|---|
| health check (no database) | 1 | 1221 | 0.8 | 0.9 | 1.2 | 0 |
| health check (no database) | 8 | 1857 | 3.9 | 4.5 | 9.1 | 0 |
| health check (no database) | 32 | 557 | 37.6 | 177.8 | 288.8 | 0 |
| list cases (database read) | 1 | 131 | 7.5 | 10.6 | 13.3 | 0 |
| list cases (database read) | 8 | 472 | 16.1 | 23.6 | 28.8 | 0 |
| list cases (database read) | 32 | 326 | 70.5 | 264.0 | 431.6 | 0 |
| decision (database write and ledger append) | 1 | 131 | 7.4 | 10.5 | 15.4 | 0 |
| decision (database write and ledger append) | 8 | 442 | 17.5 | 25.7 | 33.8 | 0 |
| decision (database write and ledger append) | 32 | 428 | 61.7 | 129.7 | 154.9 | 0 |
| name screening (matcher, a few ms of CPU) | 1 | 72 | 14.1 | 16.8 | 18.2 | 0 |
| name screening (matcher, a few ms of CPU) | 8 | 261 | 29.8 | 37.1 | 49.9 | 0 |
| name screening (matcher, a few ms of CPU) | 32 | 256 | 129.1 | 185.2 | 218.5 | 0 |

## 4 server processes

Each level ran for 8.0 seconds.

| Endpoint | Concurrent clients | Requests per second | Median (ms) | 95th percentile (ms) | 99th percentile (ms) | Failed requests |
|---|---|---|---|---|---|---|
| health check (no database) | 1 | 1220 | 0.8 | 1.0 | 1.2 | 0 |
| health check (no database) | 8 | 1328 | 3.9 | 5.0 | 15.1 | 0 |
| health check (no database) | 32 | 560 | 36.4 | 181.2 | 288.7 | 0 |
| list cases (database read) | 1 | 142 | 6.7 | 10.3 | 13.0 | 0 |
| list cases (database read) | 8 | 716 | 11.0 | 16.6 | 21.7 | 0 |
| list cases (database read) | 32 | 333 | 66.6 | 286.1 | 427.6 | 0 |
| decision (database write and ledger append) | 1 | 125 | 7.8 | 11.3 | 12.8 | 0 |
| decision (database write and ledger append) | 8 | 481 | 16.4 | 25.3 | 29.8 | 0 |
| decision (database write and ledger append) | 32 | 449 | 42.6 | 171.4 | 207.4 | 0 |
| name screening (matcher, a few ms of CPU) | 1 | 184 | 5.3 | 7.2 | 8.7 | 0 |
| name screening (matcher, a few ms of CPU) | 8 | 556 | 14.2 | 25.6 | 32.2 | 0 |
| name screening (matcher, a few ms of CPU) | 32 | 436 | 25.4 | 217.3 | 283.6 | 0 |

## How to read the results

- Up to 8 clients the numbers describe the server. At 32 clients the load generator itself becomes the bottleneck: even the health check, which touches no database, falls from about 1,800 to about 560 requests per second in both setups. Treat the 32-client rows as a floor, not as the server's limit.
- Four server processes helped most for the CPU-heavy name screening (about 261 to about 556 requests per second at 8 clients); database-bound endpoints were limited by PostgreSQL and the shared machine.

## Limits (read these)

- One machine, localhost, no network latency, client and server competing for the same CPU cores.
- Short runs (a few seconds per level), one repeat, so percentiles beyond the 95th are noisy.
- A database that starts nearly empty; ledger appends take a per-tenant lock, so writes for one tenant are serialised by design.
- No test of the AI model path (rate limits and cost make a load test of it meaningless here).
