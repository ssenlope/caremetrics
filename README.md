# CareMetrics

Healthcare claims analytics and fraud detection backend.
Built with Python, FastAPI, PostgreSQL, Docker.

## Status
In progress.

## Quick Start
docker compose up --build
Open http://localhost:8000/docs

## Design Decisions

### 1. Deterministic IDs for synthetic data
- **Decision:** ...
- **Why:** ...
- **Trade-off:** ...
- **Verified by:** ...

## Known Limitations
- Synthetic data does not reproduce real-world claim distributions or NPI structure.

### Staging table + COPY + ON CONFLICT DO NOTHING
- **Decision:** CSVs are loaded with COPY into an unconstrained temp staging table, then inserted into the real table with ON CONFLICT DO NOTHING.
- **Why:** COPY is far faster than row-by-row INSERT; the staging step makes re-imports idempotent instead of failing on the first duplicate key.
- **Trade-off:** DO NOTHING keeps the old row if a source row changes (e.g. a claim adjustment). Real data would need DO UPDATE or versioning. Validation of bad rows is not yet implemented.
- **Verified by:** Second run inserts 0 rows; table counts unchanged.
