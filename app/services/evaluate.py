"""Evaluate provider risk scores against ground_truth.csv.

Provider score = mean of its per-period scores. Ranking is by score desc, npi asc.

Usage:
    python -m app.services.evaluate --truth data/ground_truth.csv
"""
import argparse

import psycopg

from app.config import settings

RULES = ["high_volume", "price_inflation", "duplicate_billing"]


def evaluate(dsn: str, truth_path: str, ks=(50, 100, 200)) -> dict:
    with psycopg.connect(dsn) as conn:
        cur = conn.cursor()
        cur.execute("CREATE TEMP TABLE gt (npi varchar(10), fraud_type text) ON COMMIT DROP")
        with open(truth_path, "rb") as f, cur.copy(
            "COPY gt (npi, fraud_type) FROM STDIN WITH (FORMAT csv, HEADER true)"
        ) as cp:
            while chunk := f.read(1 << 20):
                cp.write(chunk)

        cur.execute("""
            CREATE TEMP TABLE ranked ON COMMIT DROP AS
            SELECT s.npi, s.score,
                   row_number() OVER (ORDER BY s.score DESC, s.npi) AS rn,
                   g.fraud_type
            FROM (SELECT npi, avg(score) AS score
                  FROM provider_risk_scores GROUP BY npi) s
            LEFT JOIN gt g ON g.npi = s.npi
        """)
        n_truth = cur.execute("SELECT count(*) FROM gt").fetchone()[0]
        n_prov = cur.execute("SELECT count(*) FROM ranked").fetchone()[0]
        types = [r[0] for r in cur.execute(
            "SELECT DISTINCT fraud_type FROM gt ORDER BY 1").fetchall()]

        overall = {}
        for k in ks:
            tp = cur.execute(
                "SELECT count(*) FROM ranked WHERE rn <= %s AND fraud_type IS NOT NULL", (k,)
            ).fetchone()[0]
            overall[k] = {"tp": tp, "precision": tp / k, "recall": tp / n_truth}

        by_type = {}
        for t in types:
            total = cur.execute("SELECT count(*) FROM gt WHERE fraud_type = %s", (t,)).fetchone()[0]
            row = {"total": total}
            for k in ks:
                tp = cur.execute(
                    "SELECT count(*) FROM ranked WHERE rn <= %s AND fraud_type = %s", (k, t)
                ).fetchone()[0]
                row[k] = tp / total
            by_type[t] = row

        hit_cols = ", ".join(
            f"avg((r.reasons ? '{r}')::int) AS {r}" for r in RULES)
        rows = cur.execute(f"""
            SELECT COALESCE(g.fraud_type, 'not_fraud') AS grp, count(*) AS n, {hit_cols}
            FROM provider_risk_scores r LEFT JOIN gt g ON g.npi = r.npi
            GROUP BY 1 ORDER BY 1
        """).fetchall()
        hit_rates = {r[0]: {"n": r[1], **dict(zip(RULES, r[2:]))} for r in rows}

    return {"n_truth": n_truth, "n_providers": n_prov, "base_rate": n_truth / n_prov,
            "overall": overall, "by_type": by_type, "hit_rates": hit_rates}


def print_report(res: dict, ks=(50, 100, 200)) -> None:
    print(f"providers={res['n_providers']:,}  true anomalies={res['n_truth']}  "
          f"random baseline precision={res['base_rate']:.1%}\n")
    print("Overall")
    for k in ks:
        o = res["overall"][k]
        lift = o["precision"] / res["base_rate"]
        print(f"  K={k:<4} TP={o['tp']:<4} precision@K={o['precision']:.1%}  "
              f"recall@K={o['recall']:.1%}  lift={lift:.1f}x")
    print("\nRecall@K by fraud type")
    print("  " + f"{'type':16s}{'n':>4}" + "".join(f"{'@' + str(k):>8}" for k in ks))
    for t, row in res["by_type"].items():
        print("  " + f"{t:16s}{row['total']:>4}" + "".join(f"{row[k]:>8.0%}" for k in ks))
    print("\nRule hit rate (share of provider-periods where the rule fired)")
    print("  " + f"{'group':16s}{'n':>8}" + "".join(f"{r:>20}" for r in RULES))
    for g, row in res["hit_rates"].items():
        print("  " + f"{g:16s}{row['n']:>8,}" + "".join(f"{row[r]:>20.1%}" for r in RULES))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default="data/ground_truth.csv")
    args = ap.parse_args()
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    print_report(evaluate(dsn, args.truth))


if __name__ == "__main__":
    main()
