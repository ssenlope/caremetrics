"""Benchmark key queries with EXPLAIN (ANALYZE) and save results.

Usage:
    python -m bench.run --label baseline
    python -m bench.run --label indexed --compare baseline
"""
import argparse
import json
import statistics
from pathlib import Path

import psycopg

from app.config import settings
from app.services.risk_rules import DuplicateRule, PriceRule

NPI = "1000000000"

QUERIES = {
    "provider_summary": f"""
        SELECT p.npi, p.name, p.specialty, p.state,
               COUNT(DISTINCT c.claim_id), COUNT(l.line_num),
               COALESCE(SUM(l.billed_amount), 0), COALESCE(SUM(l.paid_amount), 0)
        FROM providers p
        LEFT JOIN claims c      ON c.npi = p.npi
        LEFT JOIN claim_lines l ON l.claim_id = c.claim_id
        WHERE p.npi = '{NPI}'
        GROUP BY p.npi, p.name, p.specialty, p.state
    """,
    "provider_claims": f"""
        SELECT c.claim_id, c.bene_id, c.service_date, c.diagnosis_code,
               COUNT(l.line_num), COALESCE(SUM(l.billed_amount), 0), COALESCE(SUM(l.paid_amount), 0)
        FROM claims c
        LEFT JOIN claim_lines l ON l.claim_id = c.claim_id
        WHERE c.npi = '{NPI}' AND c.service_date >= '2024-01-01' AND c.service_date <= '2024-06-30'
        GROUP BY c.claim_id, c.bene_id, c.service_date, c.diagnosis_code
        ORDER BY c.service_date, c.claim_id
        LIMIT 20 OFFSET 0
    """,
    "monthly_volume": """
        SELECT p.npi, p.name, p.specialty, p.state,
               COUNT(DISTINCT c.claim_id), COUNT(l.line_num), SUM(l.billed_amount)
        FROM claims c
        JOIN providers p   ON p.npi = c.npi
        JOIN claim_lines l ON l.claim_id = c.claim_id
        WHERE c.service_date >= '2024-03-01' AND c.service_date < '2024-04-01'
        GROUP BY p.npi, p.name, p.specialty, p.state
        ORDER BY 5 DESC, p.npi
        LIMIT 20
    """,
    "hcpcs_pricing": """
        SELECT hcpcs_code, COUNT(*), SUM(units),
               SUM(billed_amount) / SUM(units), SUM(paid_amount) / SUM(units)
        FROM claim_lines
        GROUP BY hcpcs_code
        ORDER BY 4 DESC
        LIMIT 50
    """,
    "state_spend": """
        SELECT p.state, COUNT(DISTINCT p.npi), COUNT(DISTINCT c.claim_id),
               COUNT(l.line_num), SUM(l.billed_amount), SUM(l.paid_amount)
        FROM claims c
        JOIN providers p   ON p.npi = c.npi
        JOIN claim_lines l ON l.claim_id = c.claim_id
        GROUP BY p.state
        ORDER BY 6 DESC
    """,
    "rule_price_inflation": PriceRule().sql("quarter"),
    "rule_duplicate_billing": DuplicateRule().sql("quarter"),
}

RUNS = 5


def scans(node, out):
    if "Relation Name" in node:
        kind = node["Node Type"]
        idx = node.get("Index Name")
        out.add(f"{kind}:{node['Relation Name']}" + (f"({idx})" if idx else ""))
    for child in node.get("Plans", []):
        scans(child, out)
    return out


def bench(dsn):
    results = {}
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("ANALYZE")
        for name, sql in QUERIES.items():
            times, plan = [], None
            for _ in range(RUNS):
                row = conn.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}").fetchone()[0]
                plan = row[0]
                times.append(plan["Execution Time"])
            results[name] = {
                "median_ms": round(statistics.median(times), 1),
                "runs_ms": [round(t, 1) for t in times],
                "scans": sorted(scans(plan["Plan"], set())),
            }
            print(f"{name:24s} median={results[name]['median_ms']:>9.1f} ms   "
                  f"runs={results[name]['runs_ms']}")
            print(f"{'':24s} {', '.join(results[name]['scans'])}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--compare", default=None)
    args = ap.parse_args()
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")

    res = bench(dsn)
    out = Path("bench") / f"results_{args.label}.json"
    out.write_text(json.dumps(res, indent=2))
    print(f"\nsaved -> {out}")

    if args.compare:
        before = json.loads((Path("bench") / f"results_{args.compare}.json").read_text())
        print(f"\n{'query':24s}{args.compare:>12s}{args.label:>12s}{'speedup':>10s}")
        for name, r in res.items():
            b, a = before[name]["median_ms"], r["median_ms"]
            print(f"{name:24s}{b:>10.1f}ms{a:>10.1f}ms{b / a:>9.1f}x")


if __name__ == "__main__":
    main()
