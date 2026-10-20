"""Synthetic data generator for CareMetrics.

Usage (inside the api container):
    python -m etl.generate_data --providers 5000 --benes 100000 --seed 42 --out data
"""
import argparse
import csv
import random
from pathlib import Path

from faker import Faker

SPECIALTIES = [
    ("DME Supplier", 0.25),
    ("Internal Medicine", 0.25),
    ("Cardiology", 0.10),
    ("Orthopedics", 0.10),
    ("Family Practice", 0.20),
    ("Home Health", 0.10),
]

STATES = [
    "CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI",
    "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI",
]

NPI_START = 1_000_000_000  # 10-digit NPIs, assigned sequentially => always unique


def generate_providers(n: int, rng: random.Random, fake: Faker, out_dir: Path) -> None:
    names = [s for s, _ in SPECIALTIES]
    weights = [w for _, w in SPECIALTIES]
    path = out_dir / "providers.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["npi", "name", "specialty", "state"])
        for i in range(n):
            npi = str(NPI_START + i)
            specialty = rng.choices(names, weights=weights, k=1)[0]
            if specialty in ("DME Supplier", "Home Health"):
                name = fake.company()
            else:
                name = f"Dr. {fake.name()}"
            w.writerow([npi, name, specialty, rng.choice(STATES)])
    print(f"wrote {n} providers -> {path}")


def generate_beneficiaries(n: int, rng: random.Random, out_dir: Path) -> None:
    path = out_dir / "beneficiaries.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bene_id", "birth_year", "sex", "state"])
        for i in range(n):
            bene_id = f"B{i:09d}"
            birth_year = rng.randint(1925, 1960)  # Medicare-age population
            sex = rng.choice(["M", "F"])
            w.writerow([bene_id, birth_year, sex, rng.choice(STATES)])
    print(f"wrote {n} beneficiaries -> {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", type=int, default=5000)
    parser.add_argument("--benes", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="data")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    fake = Faker()
    Faker.seed(args.seed)

    generate_providers(args.providers, rng, fake, out_dir)
    generate_beneficiaries(args.benes, rng, out_dir)


if __name__ == "__main__":
    main()
