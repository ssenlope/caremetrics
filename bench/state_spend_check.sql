WITH old AS (
    SELECT p.state, COUNT(DISTINCT p.npi) AS provider_count,
           COUNT(DISTINCT c.claim_id) AS claim_count, COUNT(l.line_num) AS line_count,
           SUM(l.billed_amount) AS total_billed, SUM(l.paid_amount) AS total_paid
    FROM claims c
    JOIN providers p   ON p.npi = c.npi
    JOIN claim_lines l ON l.claim_id = c.claim_id
    GROUP BY p.state
), line_agg AS (
    SELECT claim_id, COUNT(*) AS n, SUM(billed_amount) AS b, SUM(paid_amount) AS pd
    FROM claim_lines GROUP BY claim_id
), per_provider AS (
    SELECT c.npi, COUNT(*) AS claims, SUM(la.n) AS lines,
           SUM(la.b) AS billed, SUM(la.pd) AS paid
    FROM claims c JOIN line_agg la ON la.claim_id = c.claim_id
    GROUP BY c.npi
), new AS (
    SELECT p.state, COUNT(*) AS provider_count,
           SUM(pp.claims)::bigint AS claim_count, SUM(pp.lines)::bigint AS line_count,
           SUM(pp.billed) AS total_billed, SUM(pp.paid) AS total_paid
    FROM per_provider pp JOIN providers p ON p.npi = pp.npi
    GROUP BY p.state
)
SELECT 'old_minus_new' AS check, COUNT(*) AS differing_rows
FROM (SELECT * FROM old EXCEPT SELECT * FROM new) a
UNION ALL
SELECT 'new_minus_old', COUNT(*)
FROM (SELECT * FROM new EXCEPT SELECT * FROM old) b
UNION ALL
SELECT 'rows_in_new', COUNT(*) FROM new;
