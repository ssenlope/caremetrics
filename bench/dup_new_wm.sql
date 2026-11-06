SET work_mem = '256MB';
EXPLAIN (ANALYZE, BUFFERS)

        WITH pc AS (
            SELECT npi, date_trunc('quarter', service_date)::date AS period, COUNT(*) AS claim_count
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
            SELECT DISTINCT claim_id, npi, date_trunc('quarter', service_date)::date AS period
            FROM lagged WHERE gap <= 3
        ), dc AS (
            SELECT npi, period, COUNT(*) AS dup_claims FROM dup GROUP BY 1, 2
        ), r AS (
            SELECT pc.npi, pc.period, pc.claim_count,
                   COALESCE(dc.dup_claims, 0) AS dup_claims,
                   COALESCE(dc.dup_claims, 0)::float8 / pc.claim_count AS rate
            FROM pc LEFT JOIN dc ON dc.npi = pc.npi AND dc.period = pc.period
        )
        SELECT npi, period, rate AS raw, LEAST(1.0, GREATEST(0.0, ((rate) - 0.02) / (0.1 - 0.02))) AS score,
               jsonb_build_object('duplicate_claims', dup_claims, 'claims', claim_count,
                                  'rate', round(rate::numeric, 3)) AS detail
        FROM r
    ;
