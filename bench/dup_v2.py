"""Window-function (LAG) version of the duplicate_billing rule, plus an equivalence check.

Usage (output is SQL, redirect to a file):
    python -m bench.dup_v2 explain   > bench/dup_new.sql
    python -m bench.dup_v2 compare   > bench/dup_compare.sql
"""
import sys

from app.services.risk_rules import DuplicateRule, clip01


def new_sql(grain: str = "quarter", rule: DuplicateRule = DuplicateRule()) -> str:
    g = grain
    w = int(rule.window_days)
    score = clip01("rate", rule.rate_low, rule.rate_high)
    return f"""
        WITH pc AS (
            SELECT npi, date_trunc('{g}', service_date)::date AS period, COUNT(*) AS claim_count
            FROM claims GROUP BY 1, 2
        ), cl AS (
            SELECT DISTINCT c.claim_id, c.bene_id, c.npi, c.service_date, l.hcpcs_code
            FROM claims c JOIN claim_lines l ON l.claim_id = c.claim_id
        ), lagged AS (
            SELECT claim_id, npi, service_date,
                   service_date - LAG(service_date) OVER (
                       PARTITION BY bene_id, npi, hcpcs_code
                       ORDER BY service_date, claim_id) AS gap
            FROM cl
        ), dup AS (
            SELECT DISTINCT claim_id, npi, date_trunc('{g}', service_date)::date AS period
            FROM lagged WHERE gap <= {w}
        ), dc AS (
            SELECT npi, period, COUNT(*) AS dup_claims FROM dup GROUP BY 1, 2
        ), r AS (
            SELECT pc.npi, pc.period, pc.claim_count,
                   COALESCE(dc.dup_claims, 0) AS dup_claims,
                   COALESCE(dc.dup_claims, 0)::float8 / pc.claim_count AS rate
            FROM pc LEFT JOIN dc ON dc.npi = pc.npi AND dc.period = pc.period
        )
        SELECT npi, period, rate AS raw, {score} AS score,
               jsonb_build_object('duplicate_claims', dup_claims, 'claims', claim_count,
                                  'rate', round(rate::numeric, 3)) AS detail
        FROM r
    """


def main():
    mode = sys.argv[1]
    old = DuplicateRule().sql("quarter")
    new = new_sql("quarter")
    if mode == "explain":
        print("EXPLAIN (ANALYZE, BUFFERS)")
        print(new + ";")
    elif mode == "compare":
        print(f"""
        SELECT 'old_minus_new' AS check, COUNT(*) AS differing_rows FROM
          (SELECT * FROM ({old}) o EXCEPT SELECT * FROM ({new}) n) x
        UNION ALL
        SELECT 'new_minus_old', COUNT(*) FROM
          (SELECT * FROM ({new}) n EXCEPT SELECT * FROM ({old}) o) y
        UNION ALL
        SELECT 'rows_in_new', COUNT(*) FROM ({new}) z;
        """)


if __name__ == "__main__":
    main()
