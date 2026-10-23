"""Generate synthetic claims, claim_lines and ground truth.

Requires providers.csv and beneficiaries.csv from etl.generate_data.

Usage:
    python -m etl.generate_claims --claims 1000000 --seed 42 --out data
"""
import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np

# Synthetic base prices (NOT real fee schedule values)
CODES_BY_SPECIALTY = {
    "DME Supplier": {"E0260": 900.0, "E1390": 450.0, "E1392": 600.0,
                     "K0001": 150.0, "A4604": 40.0, "L0650": 350.0, "E0601": 500.0},
    "Home Health": {"G0151": 120.0, "G0299": 95.0, "G0300": 80.0, "A4927": 25.0},
    "Internal Medicine": {"99213": 90.0, "99214": 130.0, "99203": 110.0, "93000": 50.0},
    "Family Practice": {"99213": 90.0, "99214": 130.0, "99203": 110.0, "90471": 30.0},
    "Cardiology": {"93000": 50.0, "93306": 250.0, "93015": 200.0, "99214": 130.0},
    "Orthopedics": {"99213": 90.0, "20610": 120.0, "73721": 300.0, "L1832": 280.0},
}
DIAGNOSES = ["E11.9", "I10", "J44.9", "M54.5", "I50.9", "N18.3", "G47.33", "Z99.81"]

START = date(2023, 1, 1)
DAYS = 730  # 2023-01-01 .. 2024-12-30
FRAUD_RATE = 0.02
CHUNK = 100_000


def load_csv(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", type=int, default=1_000_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    out = Path(args.out)
    rng = np.random.default_rng(args.seed)

    providers = load_csv(out / "providers.csv")
    benes = load_csv(out / "beneficiaries.csv")
    n_prov, n_bene = len(providers), len(benes)

    # --- provider setup: long-tail weights, fixed code subset ---
    prov_w = rng.lognormal(mean=0.0, sigma=1.0, size=n_prov)
    prov_codes = []  # list of (codes array, base prices array)
    for p in providers:
        pool = CODES_BY_SPECIALTY[p["specialty"]]
        names = list(pool.keys())
        k = min(len(names), int(rng.integers(3, 6)))
        chosen = rng.choice(names, size=k, replace=False)
        prov_codes.append((list(chosen), np.array([pool[c] for c in chosen])))

    # --- fraud assignment ---
    n_fraud = max(3, int(n_prov * FRAUD_RATE))
    fraud_idx = rng.choice(n_prov, size=n_fraud, replace=False)
    fraud_types = ["high_volume", "inflated_price", "duplicate"]
    fraud_map = {}  # provider index -> type
    for j, idx in enumerate(fraud_idx):
        fraud_map[int(idx)] = fraud_types[j % 3]
        if fraud_types[j % 3] == "high_volume":
            prov_w[idx] *= 8.0
    prov_p = prov_w / prov_w.sum()

    bene_w = rng.lognormal(mean=0.0, sigma=1.0, size=n_bene)
    bene_p = bene_w / bene_w.sum()

    inflate = {i: rng.uniform(2.0, 3.0) for i, t in fraud_map.items() if t == "inflated_price"}
    dup_set = {i for i, t in fraud_map.items() if t == "duplicate"}

    with (out / "ground_truth.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["npi", "fraud_type"])
        for i, t in sorted(fraud_map.items()):
            w.writerow([providers[i]["npi"], t])

    claims_f = (out / "claims.csv").open("w", newline="")
    lines_f = (out / "claim_lines.csv").open("w", newline="")
    cw, lw = csv.writer(claims_f), csv.writer(lines_f)
    cw.writerow(["claim_id", "bene_id", "npi", "service_date", "diagnosis_code"])
    lw.writerow(["claim_id", "line_num", "hcpcs_code", "units", "billed_amount", "paid_amount"])

    def write_claim(cid, bi, pi, day_offset, diag, lines):
        d = START + timedelta(days=int(day_offset))
        cw.writerow([cid, benes[bi]["bene_id"], providers[pi]["npi"], d.isoformat(), diag])
        for ln, (code, units, billed, paid) in enumerate(lines, start=1):
            lw.writerow([cid, ln, code, units, f"{billed:.2f}", f"{paid:.2f}"])

    counter = 0
    total_lines = 0
    remaining = args.claims
    while remaining > 0:
        n = min(CHUNK, remaining)
        pis = rng.choice(n_prov, size=n, p=prov_p)
        bis = rng.choice(n_bene, size=n, p=bene_p)
        days = rng.integers(0, DAYS, size=n)
        nlines = rng.choice([1, 2, 3, 4], size=n, p=[0.55, 0.30, 0.10, 0.05])
        diags = rng.choice(DIAGNOSES, size=n)
        dup_roll = rng.random(n)

        for k in range(n):
            pi, bi = int(pis[k]), int(bis[k])
            codes, prices = prov_codes[pi]
            lines = []
            for _ in range(int(nlines[k])):
                ci = int(rng.integers(0, len(codes)))
                units = int(rng.choice([1, 1, 1, 2, 2, 3, 5, 10]))
                unit_price = prices[ci] * rng.normal(1.0, 0.08)
                if pi in inflate:
                    unit_price *= inflate[pi]
                billed = max(0.01, unit_price * units)
                paid = billed * rng.uniform(0.7, 0.9)
                lines.append((codes[ci], units, billed, paid))
            counter += 1
            total_lines += len(lines)
            write_claim(f"C{counter:010d}", bi, pi, days[k], diags[k], lines)

            # duplicate fraud: copy the claim with a small date shift, new claim_id
            if pi in dup_set and dup_roll[k] < 0.15:
                counter += 1
                total_lines += len(lines)
                shift = int(rng.integers(0, 4))
                write_claim(f"C{counter:010d}", bi, pi,
                            min(DAYS - 1, int(days[k]) + shift), diags[k], lines)

        remaining -= n
        print(f"generated {counter:,} claims so far")

    claims_f.close()
    lines_f.close()
    print(f"done: {counter:,} claims, {total_lines:,} lines, "
          f"{len(fraud_map)} fraud providers -> {out}")


if __name__ == "__main__":
    main()
