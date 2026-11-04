"""Run all rules and write weighted risk scores to provider_risk_scores.

Usage:
    python -m app.services.risk_engine --grain quarter
"""
import argparse
import time

import psycopg

from app.config import settings
from app.services.risk_rules import DEFAULT_RULES

HIT_THRESHOLD = 0.5  # a rule appears in `reasons` when its score >= this


def run_scoring(dsn: str, grain: str = "quarter", rules=None, verbose: bool = False) -> int:
    rules = rules or DEFAULT_RULES
    total_w = float(sum(r.weight for r in rules))
    t_all = time.perf_counter()

    with psycopg.connect(dsn) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TEMP TABLE rule_scores (
                rule text, w float8, npi varchar(10), period date,
                raw float8, score float8, detail jsonb
            ) ON COMMIT DROP
        """)
        for r in rules:
            t0 = time.perf_counter()
            cur.execute(
                f"INSERT INTO rule_scores "
                f"SELECT '{r.name}', {float(r.weight)}, q.npi, q.period, q.raw, q.score, q.detail "
                f"FROM ({r.sql(grain)}) q"
            )
            if verbose:
                print(f"{r.name:18s} rows={cur.rowcount:>8,}  time={time.perf_counter() - t0:6.1f}s")

        # Scores are derived data: rebuild from scratch so re-runs are idempotent.
        cur.execute("DELETE FROM provider_risk_scores")
        cur.execute(f"""
            INSERT INTO provider_risk_scores (npi, period, score, reasons)
            SELECT npi, period,
                   round((SUM(score * w) / {total_w})::numeric, 3),
                   COALESCE(
                     jsonb_object_agg(rule, detail || jsonb_build_object(
                         'score', round(score::numeric, 3), 'weight', w))
                       FILTER (WHERE score >= {HIT_THRESHOLD}),
                     '{{}}'::jsonb)
            FROM rule_scores
            GROUP BY npi, period
        """)
        written = cur.rowcount
    if verbose:
        print(f"TOTAL scores written={written:,} grain={grain} time={time.perf_counter() - t_all:.1f}s")
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grain", default="quarter", choices=["month", "quarter", "year"])
    args = ap.parse_args()
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    run_scoring(dsn, args.grain, verbose=True)


if __name__ == "__main__":
    main()
