import csv

import psycopg

from etl.load_validated import run_load


def write(path, header, rows):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def make_data(d):
    write(d / "providers.csv", ["npi", "name", "specialty", "state"],
          [["1000000000", "Acme DME", "DME Supplier", "CA"],
           ["1000000001", "Dr. Who", "Cardiology", "TX"]])
    write(d / "beneficiaries.csv", ["bene_id", "birth_year", "sex", "state"],
          [["B000000000", "1940", "M", "CA"], ["B000000001", "1945", "F", "TX"]])
    write(d / "claims.csv", ["claim_id", "bene_id", "npi", "service_date", "diagnosis_code"],
          [["C1", "B000000000", "1000000000", "2023-05-01", "I10"],
           ["C2", "B000000001", "1000000001", "2023-06-01", "E11.9"],
           ["C3", "B000000000", "9999999999", "2023-07-01", "I10"],      # unknown_npi
           ["C4", "B000000000", "1000000000", "03/15/2023", "I10"],     # bad_date_format
           ["C5", "B000000000", "1000000000", "1900-01-01", "I10"],     # date_out_of_range
           ["C6", "BXXXXXXXXX", "1000000000", "2023-08-01", "I10"]])    # unknown_bene
    write(d / "claim_lines.csv",
          ["claim_id", "line_num", "hcpcs_code", "units", "billed_amount", "paid_amount"],
          [["C1", "1", "E1390", "1", "450.00", "360.00"],
           ["C1", "2", "A4604", "0", "40.00", "30.00"],                 # non_positive_units
           ["C2", "1", "99213", "1", "90.00", "70.00"],
           ["C2", "2", "93000", "1", "50.00", "40.00"],
           ["C2", "3", "99214", "1", "-5.00", "-4.00"],                 # negative_amount
           ["C3", "1", "E1390", "1", "450.00", "360.00"],               # orphan (C3 rejected)
           ["CX1", "1", "E1390", "1", "450.00", "360.00"]])             # orphan (never existed)


def count(dsn, sql):
    with psycopg.connect(dsn) as c:
        return c.execute(sql).fetchone()[0]


def test_bad_rows_go_to_rejected_rows(clean_db, tmp_path):
    make_data(tmp_path)
    run_load(clean_db, tmp_path)  # must not raise

    assert count(clean_db, "SELECT count(*) FROM claims") == 2
    assert count(clean_db, "SELECT count(*) FROM claim_lines") == 3
    with psycopg.connect(clean_db) as c:
        reasons = dict(c.execute("SELECT reason, count(*) FROM rejected_rows GROUP BY reason").fetchall())
    assert reasons == {
        "unknown_npi": 1, "bad_date_format": 1, "date_out_of_range": 1, "unknown_bene": 1,
        "non_positive_units": 1, "negative_amount": 1, "orphan_line": 2,
    }


def test_reimport_is_idempotent(clean_db, tmp_path):
    make_data(tmp_path)
    run_load(clean_db, tmp_path)
    before = [count(clean_db, f"SELECT count(*) FROM {t}")
              for t in ("claims", "claim_lines", "rejected_rows")]
    run_load(clean_db, tmp_path)
    after = [count(clean_db, f"SELECT count(*) FROM {t}")
             for t in ("claims", "claim_lines", "rejected_rows")]
    assert before == after == [2, 3, 8]
