"""Bulk load CSVs into PostgreSQL via staging tables + COPY.

Idempotent: re-running leaves row counts unchanged (ON CONFLICT DO NOTHING).

Usage:
    python -m etl.load --data data
"""
import argparse
import time
from pathlib import Path

import psycopg

from app.config import settings

# (table, csv file, columns, conflict key)
TABLES = [
    ("providers", "providers.csv", ["npi", "name", "specialty", "state"], "(npi)"),
    ("beneficiaries", "beneficiaries.csv",
     ["bene_id", "birth_year", "sex", "state"], "(bene_id)"),
    ("claims", "claims.csv",
     ["claim_id", "bene_id", "npi", "service_date", "diagnosis_code"], "(claim_id)"),
    ("claim_lines", "claim_lines.csv",
     ["claim_id", "line_num", "hcpcs_code", "units", "billed_amount", "paid_amount"],
     "(claim_id, line_num)"),
]


def load_table(conn, data_dir, table, csv_name, cols, conflict):
    col_list = ", ".join(cols)
    staging = f"stg_{table}"
    path = data_dir / csv_name
    t0 = time.perf_counter()

    with conn.cursor() as cur:
        # Staging table: same columns, no constraints, dropped at end of transaction
        cur.execute(f"CREATE TEMP TABLE {staging} (LIKE {table} INCLUDING DEFAULTS) ON COMMIT DROP")

        # Fast bulk copy into staging
        with path.open("rb") as f, cur.copy(
            f"COPY {staging} ({col_list}) FROM STDIN WITH (FORMAT csv, HEADER true)"
        ) as copy:
            while chunk := f.read(1 << 20):
                copy.write(chunk)

        cur.execute(f"SELECT count(*) FROM {staging}")
        staged = cur.fetchone()[0]

        # Move to real table; duplicates are skipped => idempotent
        cur.execute(
            f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM {staging} "
            f"ON CONFLICT {conflict} DO NOTHING"
        )
        inserted = cur.rowcount

    conn.commit()
    secs = time.perf_counter() - t0
    rate = staged / secs if secs else 0
    print(f"{table:14s} staged={staged:>10,} inserted={inserted:>10,} "
          f"skipped={staged - inserted:>8,} time={secs:6.1f}s  {rate:>10,.0f} rows/s")
    return staged, inserted, secs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    args = ap.parse_args()
    data_dir = Path(args.data)

    # psycopg wants a plain postgresql:// URL, not the SQLAlchemy "+psycopg" form
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")

    total_rows, total_secs = 0, 0.0
    with psycopg.connect(dsn) as conn:
        for table, csv_name, cols, conflict in TABLES:
            staged, _, secs = load_table(conn, data_dir, table, csv_name, cols, conflict)
            total_rows += staged
            total_secs += secs

    print(f"TOTAL staged={total_rows:,} time={total_secs:.1f}s "
          f"{total_rows / total_secs:,.0f} rows/s")


if __name__ == "__main__":
    main()
