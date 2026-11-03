"""Validating bulk loader: bad rows go to rejected_rows instead of failing the load.

Flow per table (claims, claim_lines):
  COPY into all-text staging -> compute `reason` per row in SQL
  -> rejected rows to rejected_rows (deduped by hash) -> valid rows to the real table.

Usage:
    python -m etl.load_validated --data data/dirty
"""
import argparse
import time
from pathlib import Path

import psycopg

from app.config import settings
from etl.load import TABLES, load_table

CLAIM_COLS = ["claim_id", "bene_id", "npi", "service_date", "diagnosis_code"]
LINE_COLS = ["claim_id", "line_num", "hcpcs_code", "units", "billed_amount", "paid_amount"]

CLAIMS_REASON = r"""
CASE
  WHEN COALESCE(s.claim_id, '') = '' THEN 'missing_claim_id'
  WHEN COALESCE(s.service_date, '') !~ '^\d{4}-\d{2}-\d{2}$'
       OR NOT pg_input_is_valid(s.service_date, 'date') THEN 'bad_date_format'
  WHEN s.service_date::date NOT BETWEEN DATE '2023-01-01' AND DATE '2024-12-31'
       THEN 'date_out_of_range'
  WHEN NOT EXISTS (SELECT 1 FROM providers p WHERE p.npi = s.npi) THEN 'unknown_npi'
  WHEN NOT EXISTS (SELECT 1 FROM beneficiaries b WHERE b.bene_id = s.bene_id) THEN 'unknown_bene'
END
"""
CLAIMS_SELECT = "claim_id, bene_id, npi, service_date::date, diagnosis_code"

LINES_REASON = r"""
CASE
  WHEN COALESCE(s.line_num, '') !~ '^\d+$'
       OR COALESCE(s.units, '') !~ '^-?\d+$'
       OR COALESCE(s.billed_amount, '') !~ '^-?\d+(\.\d+)?$'
       OR COALESCE(s.paid_amount, '') !~ '^-?\d+(\.\d+)?$' THEN 'bad_number_format'
  WHEN s.units::int <= 0 THEN 'non_positive_units'
  WHEN s.billed_amount::numeric < 0 OR s.paid_amount::numeric < 0 THEN 'negative_amount'
  WHEN NOT EXISTS (SELECT 1 FROM claims c WHERE c.claim_id = s.claim_id) THEN 'orphan_line'
END
"""
LINES_SELECT = ("claim_id, line_num::int, hcpcs_code, units::int, "
                "billed_amount::numeric, paid_amount::numeric")


def load_checked(conn, data_dir, table, csv_name, cols, conflict, reason_sql, select_sql):
    stg, chk = f"stg_{table}", f"stg_{table}_checked"
    col_list = ", ".join(cols)
    t0 = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE {stg} ({', '.join(c + ' text' for c in cols)}) ON COMMIT DROP")
        with (data_dir / csv_name).open("rb") as f, cur.copy(
            f"COPY {stg} ({col_list}) FROM STDIN WITH (FORMAT csv, HEADER true)"
        ) as cp:
            while chunk := f.read(1 << 20):
                cp.write(chunk)

        cur.execute(f"CREATE TEMP TABLE {chk} ON COMMIT DROP AS "
                    f"SELECT s.*, {reason_sql} AS reason FROM {stg} s")
        cur.execute(f"SELECT count(*), count(reason) FROM {chk}")
        staged, bad = cur.fetchone()

        cur.execute(
            f"INSERT INTO rejected_rows (source_table, reason, raw_row, row_hash) "
            f"SELECT %s, reason, j, md5(j::text) FROM "
            f"(SELECT reason, to_jsonb(c) - 'reason' AS j FROM {chk} c WHERE reason IS NOT NULL) t "
            f"ON CONFLICT (source_table, row_hash) DO NOTHING",
            (table,),
        )
        cur.execute(
            f"INSERT INTO {table} ({col_list}) SELECT {select_sql} FROM {chk} "
            f"WHERE reason IS NULL ON CONFLICT {conflict} DO NOTHING"
        )
        inserted = cur.rowcount
    conn.commit()
    secs = time.perf_counter() - t0
    print(f"{table:14s} staged={staged:>10,} rejected={bad:>7,} inserted={inserted:>10,} "
          f"time={secs:6.1f}s")
    return secs


def run_load(dsn, data_dir):
    data_dir = Path(data_dir)
    t0 = time.perf_counter()
    with psycopg.connect(dsn) as conn:
        for table, csv_name, cols, conflict in TABLES[:2]:  # providers, beneficiaries
            load_table(conn, data_dir, table, csv_name, cols, conflict)
        load_checked(conn, data_dir, "claims", "claims.csv", CLAIM_COLS,
                     "(claim_id)", CLAIMS_REASON, CLAIMS_SELECT)
        load_checked(conn, data_dir, "claim_lines", "claim_lines.csv", LINE_COLS,
                     "(claim_id, line_num)", LINES_REASON, LINES_SELECT)
    print(f"TOTAL time={time.perf_counter() - t0:.1f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--dsn", default=None)
    args = ap.parse_args()
    dsn = args.dsn or settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    run_load(dsn, args.data)


if __name__ == "__main__":
    main()
