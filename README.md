# CareMetrics

Healthcare claims analytics and fraud detection backend built with Python, FastAPI, PostgreSQL, and Docker. Works on synthetic Medicare-style claims (1M claims, 1.65M service lines) with injected fraud patterns and a ground-truth file for measuring detection quality.

## Status
In progress. Done: data model, synthetic data generator, idempotent bulk loader, validation with rejected-rows table, tests. Next: analytics API, rule-based anomaly detection with precision/recall, index optimization with before/after benchmarks.

## Quick Start

```bash
docker compose up --build
docker compose exec api alembic upgrade head
docker compose exec api python -m etl.generate_data --seed 42 --out data
docker compose exec api python -m etl.generate_claims --claims 1000000 --seed 42 --out data
docker compose exec api python -m etl.load_validated --data data
docker compose exec api python -m pytest -q
```

API docs: http://localhost:8000/docs

## Data Model

```
providers             npi PK, name, specialty, state
beneficiaries         bene_id PK, birth_year, sex, state
claims                claim_id PK, bene_id FK, npi FK, service_date, diagnosis_code
claim_lines           PK (claim_id, line_num), FK claim_id, hcpcs_code, units, billed_amount, paid_amount
provider_risk_scores  PK (npi, period), score, reasons JSONB
rejected_rows         source_table, reason, raw_row JSONB, row_hash (unique per table)
```

Only primary-key indexes exist for now, so there is a clean baseline for later optimization.

## Benchmarks
Local, Apple silicon, Docker Desktop, PostgreSQL 16, single runs.

| Step | Rows | Time | Throughput |
|------|------|------|------------|
| Initial load, no validation | 2.76M | 20.3s | ~135K rows/s |
| Initial load, with validation (clean data) | 2.76M | 25.5s | ~108K rows/s |
| Re-import, all duplicates skipped | 2.76M | 6.4s | n/a (no writes) |

Validation adds ~26% overhead. The re-import is fast only because nothing is written.

## Data Validation Results
Injected 2,765 faults (about 0.1% of rows) across 7 fault types into a copy of the data. The loader completed without failing and rejected 4,417 rows: the count for each injected fault type matched exactly, plus 1,652 service lines orphaned by rejected claims (cascade). Re-importing the same dirty file added 0 rows to `rejected_rows`.

## Design Decisions

### 1. Deterministic IDs and reproducible generation
- **Decision:** NPIs are sequential from 1,000,000,000; bene_ids are a prefix plus zero-padded index. All randomness comes from one seeded RNG.
- **Why:** Guarantees unique IDs, and the same seed gives byte-identical files, so benchmarks and detection metrics are comparable across runs.
- **Trade-off:** IDs are unrealistic (real NPIs have a check digit). Adding a random call changes downstream data for the same seed.
- **Verified by:** Identical MD5 checksums across two runs with the same seed.

### 2. Header-detail claims model
- **Decision:** `claims` has one row per claim; `claim_lines` has one row per service line, keyed by (claim_id, line_num).
- **Why:** A claim can have several service lines. A claim_id-only key would collide on line 2+, and ON CONFLICT DO NOTHING would silently drop them.
- **Trade-off:** Analytics must distinguish claim-level counts (COUNT DISTINCT claim_id) from line-level counts, and queries need an extra join.
- **Verified by:** Loaded row counts match the generator output exactly.

### 3. Long-tailed synthetic data with injected fraud
- **Decision:** Provider and beneficiary activity use log-normal weights; each provider bills a fixed subset of codes. About 2% of providers (100) get one of three patterns: high volume, inflated unit price, duplicate claims. Ground truth is saved separately.
- **Why:** Uniform data makes anomaly detection trivially easy. Known labels allow real precision/recall.
- **Trade-off:** Rule-injected patterns overstate real-world detection performance. Prices are synthetic.
- **Verified by:** Ground truth has 100 providers split 33/34/33 across the three types.

### 4. Staging table + COPY + ON CONFLICT DO NOTHING
- **Decision:** CSVs are loaded with COPY into a temp staging table, then inserted into the real table with ON CONFLICT DO NOTHING.
- **Why:** COPY is much faster than row-by-row INSERT, and staging makes re-imports idempotent.
- **Trade-off:** DO NOTHING keeps the old row if a source row changes (e.g. a claim adjustment). Real data would need DO UPDATE or versioning.
- **Verified by:** Second run inserts 0 rows; counts stay at 5,000 / 100,000 / 1,000,755 / 1,650,522.

### 5. Validation with a rejected_rows table
- **Decision:** Rows are COPYed into an all-text staging table, validated in SQL (format, range, foreign-key existence, orphan lines). Bad rows go to `rejected_rows` with a reason and the raw row as JSONB; valid rows continue.
- **Why:** With typed staging, one bad value fails the whole COPY. Silently dropping rows hides data problems.
- **Trade-off:** Extra pass over the data (about 26% slower). Rejecting a claim orphans its lines, so rejection counts cascade.
- **Verified by:** pytest with one case per fault type; dirty-file re-import leaves `rejected_rows` unchanged.

### 6. Constraints in the database
- **Decision:** CHECK constraints (units > 0, amounts >= 0) and foreign keys live in PostgreSQL, not only in application code.
- **Why:** Bad data cannot get in through any path.
- **Trade-off:** Constraints add write overhead.

## Known Limitations
- Synthetic data does not reproduce real-world claim distributions, prices, or NPI structure.
- Fraud patterns are injected by rule, so detection results overstate real-world performance.
- ON CONFLICT DO NOTHING ignores corrected versions of an existing claim.
- Benchmarks are single local runs, not medians of repeated runs.
- No analytics API, anomaly detection, or index optimization yet.