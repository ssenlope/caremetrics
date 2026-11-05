# CareMetrics
![CI](https://github.com/ssenlope/caremetrics/actions/workflows/ci.yml/badge.svg)

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

### 7. Explicit grain in analytics queries
- **Decision:** Aggregations are hand-written SQL. Claim counts use COUNT(DISTINCT claim_id); line counts and amounts come from claim_lines; average unit price is SUM(billed)/SUM(units).
- **Why:** In a header-detail model, COUNT(*) after joining lines silently inflates claim counts (about 1.65x here), and averaging per-line prices ignores units.
- **Trade-off:** Offset pagination is simple but slows on deep pages; keyset pagination would fix that.
- **Verified by:** pytest on a hand-built dataset; per-state claim and line counts sum to 1,000,755 and 1,650,522.

### 8. Configurable rule engine with explainable scores
- **Decision:** Each rule (high volume, price inflation, duplicate billing) is an independent class with a name, weight and thresholds, producing a 0 to 1 score per provider per quarter. The risk score is the weighted average; rules scoring >= 0.5 are stored in `reasons` (JSONB).
- **Why:** Rules stay testable and tunable on their own, and every flagged provider comes with an explanation. Volume uses log counts and peer z-scores by specialty because claim volume is long-tailed.
- **Trade-off:** Rules were designed with knowledge of the injected patterns, and the price baseline is the dataset's own median, so results overstate real-world performance. Quarterly periods trade time resolution for less noise (about 8 claims per provider per month).
- **Verified by:** pytest on a hand-built dataset; re-running scoring rewrites the same rows.

## Detection Results (v1, untuned)
Provider score = mean of quarterly risk scores. Evaluated against 100 injected anomalous providers (2% base rate) out of 5,000.

| K | Precision@K | Recall@K | Lift vs random |
|---|---|---|---|
| 50 | 86% | 43% | 43x |
| 100 | 67% | 67% | 33.5x |
| 200 | 39% | 78% | 19.5x |

Recall@100 by fraud type: inflated price 100%, duplicate billing 64%, high volume 38%.

Findings:
- Price inflation is detected cleanly (0 false positives on the rule).
- High-volume detection is weakest: the injected 8x multiplier is close to natural long-tail variation, and the rule fires on about 1.9% of normal provider-quarters.
- Averaging rule scores dilutes providers that match only one pattern.

These scores overstate real-world performance: the rules were written knowing the injected patterns, and nothing was tuned on a held-out set.


## Index Optimization (round 1)
Method: EXPLAIN (ANALYZE) execution time, median of 5 runs, 1M claims / 1.65M lines, local.
Added `claims(npi, service_date)` and `claims(service_date)` via Alembic migration.

| Query | Before | After | Speedup |
|---|---|---|---|
| provider_summary | 15.4 ms | 0.5 ms | 31x |
| provider_claims (date range) | 16.5 ms | 0.1 ms | 165x |
| monthly_volume | 117.4 ms | 110.4 ms | 1.1x |
| hcpcs_pricing | 93.0 ms | 92.7 ms | 1.0x |
| state_spend | 2,558 ms | 2,552 ms | 1.0x |
| state_spend (EXPLAIN ANALYZE, Median)| 2,558 ms | 779 ms | about 3.3x|

Indexes add about 33 MB (claims primary key: 30 MB). Write overhead not yet measured.

Takeaway: indexes fixed lookups by provider but did nothing for full-table aggregations
(state_spend, hcpcs_pricing, rule scoring), which need a different approach.

## Known Limitations
- Synthetic data does not reproduce real-world claim distributions, prices, or NPI structure.
- Fraud patterns are injected by rule, so detection results overstate real-world performance.
- ON CONFLICT DO NOTHING ignores corrected versions of an existing claim.
- Benchmarks are single local runs, not medians of repeated runs.
- No analytics API, anomaly detection, or index optimization yet.
- CI runs unit tests on small hand-built datasets; the 1M-row load, scoring and evaluation are run locally.