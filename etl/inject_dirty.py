"""Create a dirty copy of the CSVs by corrupting ~0.1% of claims and claim_lines.

Does NOT touch the generator, so clean data stays byte-reproducible.
Writes a manifest of every injected fault.

Usage:
    python -m etl.inject_dirty --src data --out data/dirty --rate 0.001 --seed 7
"""
import argparse
import csv
import random
import shutil
from collections import Counter
from pathlib import Path

CLAIM_KINDS = ["bad_date_format", "date_out_of_range", "unknown_npi", "unknown_bene"]
LINE_KINDS = ["non_positive_units", "negative_amount", "bad_number_format", "orphan_line"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data")
    ap.add_argument("--out", default="data/dirty")
    ap.add_argument("--rate", type=float, default=0.001)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    manifest = []

    for name in ("providers.csv", "beneficiaries.csv"):
        shutil.copy(src / name, out / name)

    # claims: claim_id, bene_id, npi, service_date, diagnosis_code
    with (src / "claims.csv").open() as fin, (out / "claims.csv").open("w", newline="") as fout:
        r, w = csv.reader(fin), csv.writer(fout)
        w.writerow(next(r))
        for row in r:
            if rng.random() < args.rate:
                kind = rng.choice(CLAIM_KINDS)
                if kind == "bad_date_format":
                    row[3] = "03/15/2023"
                elif kind == "date_out_of_range":
                    row[3] = "1900-01-01"
                elif kind == "unknown_npi":
                    row[2] = "9999999999"
                else:
                    row[1] = "BXXXXXXXXX"
                manifest.append(("claims", row[0], kind))
            w.writerow(row)

    # claim_lines: claim_id, line_num, hcpcs_code, units, billed_amount, paid_amount
    orphan_n = 0
    with (src / "claim_lines.csv").open() as fin, (out / "claim_lines.csv").open("w", newline="") as fout:
        r, w = csv.reader(fin), csv.writer(fout)
        w.writerow(next(r))
        for row in r:
            if rng.random() < args.rate:
                kind = rng.choice(LINE_KINDS)
                key = f"{row[0]}:{row[1]}"
                if kind == "non_positive_units":
                    row[3] = "0"
                elif kind == "negative_amount":
                    row[4] = "-" + row[4]
                elif kind == "bad_number_format":
                    row[3] = "abc"
                else:
                    orphan_n += 1
                    row[0] = f"CX{orphan_n:08d}"
                manifest.append(("claim_lines", key, kind))
            w.writerow(row)

    with (out / "dirty_manifest.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["table", "key", "injected_fault"])
        w.writerows(manifest)

    for (table, kind), n in sorted(Counter((t, k) for t, _, k in manifest).items()):
        print(f"{table:12s} {kind:20s} {n}")
    print(f"total injected faults: {len(manifest)} -> {out}")


if __name__ == "__main__":
    main()
