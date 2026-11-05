EXPLAIN (ANALYZE, BUFFERS)
WITH line_agg AS (
    SELECT claim_id, COUNT(*) AS n, SUM(billed_amount) AS b, SUM(paid_amount) AS pd
    FROM claim_lines GROUP BY claim_id
), per_provider AS (
    SELECT c.npi, COUNT(*) AS claims, SUM(la.n) AS lines,
           SUM(la.b) AS billed, SUM(la.pd) AS paid
    FROM claims c JOIN line_agg la ON la.claim_id = c.claim_id
    GROUP BY c.npi
)
SELECT p.state, COUNT(*) AS provider_count,
       SUM(pp.claims)::bigint AS claim_count, SUM(pp.lines)::bigint AS line_count,
       SUM(pp.billed) AS total_billed, SUM(pp.paid) AS total_paid
FROM per_provider pp JOIN providers p ON p.npi = pp.npi
GROUP BY p.state
ORDER BY 6 DESC;
