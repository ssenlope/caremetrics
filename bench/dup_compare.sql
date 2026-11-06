
        SELECT 'old_minus_new' AS check, COUNT(*) AS differing_rows FROM
          (SELECT * FROM (
        WITH pc AS (
            SELECT npi, date_trunc('quarter', service_date)::date AS period, COUNT(*) AS claim_count
            FROM claims GROUP BY 1, 2
        ), cl AS (
            SELECT DISTINCT c.claim_id, c.bene_id, c.npi, c.service_date, l.hcpcs_code
            FROM claims c JOIN claim_lines l ON l.claim_id = c.claim_id
        ), dup AS (
            SELECT DISTINCT b.claim_id, b.npi,
                   date_trunc('quarter', b.service_date)::date AS period
            FROM cl a JOIN cl b
              ON a.bene_id = b.bene_id AND a.npi = b.npi AND a.hcpcs_code = b.hcpcs_code
             AND a.claim_id <> b.claim_id
             AND b.service_date BETWEEN a.service_date AND a.service_date + 3
             AND (b.service_date > a.service_date OR b.claim_id > a.claim_id)
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
        ) o EXCEPT SELECT * FROM (
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
    ) n) x
        UNION ALL
        SELECT 'new_minus_old', COUNT(*) FROM
          (SELECT * FROM (
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
    ) n EXCEPT SELECT * FROM (
        WITH pc AS (
            SELECT npi, date_trunc('quarter', service_date)::date AS period, COUNT(*) AS claim_count
            FROM claims GROUP BY 1, 2
        ), cl AS (
            SELECT DISTINCT c.claim_id, c.bene_id, c.npi, c.service_date, l.hcpcs_code
            FROM claims c JOIN claim_lines l ON l.claim_id = c.claim_id
        ), dup AS (
            SELECT DISTINCT b.claim_id, b.npi,
                   date_trunc('quarter', b.service_date)::date AS period
            FROM cl a JOIN cl b
              ON a.bene_id = b.bene_id AND a.npi = b.npi AND a.hcpcs_code = b.hcpcs_code
             AND a.claim_id <> b.claim_id
             AND b.service_date BETWEEN a.service_date AND a.service_date + 3
             AND (b.service_date > a.service_date OR b.claim_id > a.claim_id)
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
        ) o) y
        UNION ALL
        SELECT 'rows_in_new', COUNT(*) FROM (
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
    ) z;
        
