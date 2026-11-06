"""Rule definitions for provider risk scoring.

Each rule returns a SQL query yielding (npi, period, raw, score, detail):
  raw    = the underlying metric
  score  = 0..1 after mapping the metric between two thresholds
  detail = JSON shown in provider_risk_scores.reasons when the rule fires

All values interpolated into SQL are numeric config or whitelisted grains.
"""
from dataclasses import dataclass

GRAINS = {"month", "quarter", "year"}


def clip01(expr: str, lo: float, hi: float) -> str:
    return f"LEAST(1.0, GREATEST(0.0, (({expr}) - {float(lo)}) / ({float(hi)} - {float(lo)})))"


def _check(grain: str) -> str:
    if grain not in GRAINS:
        raise ValueError(f"grain must be one of {sorted(GRAINS)}")
    return grain


@dataclass(frozen=True)
class VolumeRule:
    name: str = "high_volume"
    weight: float = 1.0
    z_low: float = 1.0
    z_high: float = 3.0

    def sql(self, grain: str) -> str:
        g = _check(grain)
        score = clip01("COALESCE(z, 0)", self.z_low, self.z_high)
        return f"""
        WITH pc AS (
            SELECT npi, date_trunc('{g}', service_date)::date AS period, COUNT(*) AS claim_count
            FROM claims GROUP BY 1, 2
        ), st AS (
            SELECT pc.npi, pc.period, pc.claim_count, p.specialty,
                   ln(pc.claim_count::float8) AS lc
            FROM pc JOIN providers p ON p.npi = pc.npi
        ), zz AS (
            SELECT npi, period, claim_count,
                   (lc - avg(lc) OVER w) / NULLIF(stddev_samp(lc) OVER w, 0) AS z
            FROM st
            WINDOW w AS (PARTITION BY specialty, period)
        )
        SELECT npi, period, z AS raw, {score} AS score,
               jsonb_build_object('claim_count', claim_count,
                                  'z_log_count', round(z::numeric, 2)) AS detail
        FROM zz
        """


@dataclass(frozen=True)
class PriceRule:
    name: str = "price_inflation"
    weight: float = 1.0
    ratio_low: float = 1.15
    ratio_high: float = 1.8

    def sql(self, grain: str) -> str:
        g = _check(grain)
        score = clip01("avg_ratio", self.ratio_low, self.ratio_high)
        return f"""
        WITH base AS (
            SELECT hcpcs_code,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY (billed_amount / units)::float8) AS med
            FROM claim_lines GROUP BY hcpcs_code
        ), lr AS (
            SELECT c.npi, date_trunc('{g}', c.service_date)::date AS period,
                   (l.billed_amount / l.units)::float8 / b.med AS ratio
            FROM claim_lines l
            JOIN claims c ON c.claim_id = l.claim_id
            JOIN base b   ON b.hcpcs_code = l.hcpcs_code
        ), agg AS (
            SELECT npi, period, avg(ratio) AS avg_ratio, COUNT(*) AS n
            FROM lr GROUP BY 1, 2
        )
        SELECT npi, period, avg_ratio AS raw, {score} AS score,
               jsonb_build_object('avg_price_ratio', round(avg_ratio::numeric, 2),
                                  'lines', n) AS detail
        FROM agg
        """


@dataclass(frozen=True)
class DuplicateRule:
    name: str = "duplicate_billing"
    weight: float = 1.0
    window_days: int = 3
    rate_low: float = 0.02
    rate_high: float = 0.10

    def sql(self, grain: str) -> str:
        g = _check(grain)
        w = int(self.window_days)
        score = clip01("rate", self.rate_low, self.rate_high)
        # LAG over (bene, provider, code) ordered by date: one sort instead of a
        # self-join that sorted the same 1.4M rows twice. Proven equivalent to the
        # old self-join with a two-way EXCEPT (0 differing rows).
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


DEFAULT_RULES = [VolumeRule(), PriceRule(), DuplicateRule()]
