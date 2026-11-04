import psycopg

from app.services.risk_engine import run_scoring


def seed(dsn):
    with psycopg.connect(dsn) as c:
        c.execute("INSERT INTO providers VALUES "
                  "('1000000000','P1','DME Supplier','CA'),"
                  "('1000000001','P2','DME Supplier','CA'),"
                  "('1000000002','P3','DME Supplier','CA')")
        c.execute("INSERT INTO beneficiaries VALUES ('B000000000',1940,'M','CA')")
        c.execute("INSERT INTO claims VALUES "
                  "('C1','B000000000','1000000000','2023-03-01','I10'),"
                  "('C2','B000000000','1000000000','2023-03-02','I10'),"  # duplicate of C1
                  "('C3','B000000000','1000000001','2023-03-05','I10'),"
                  "('C4','B000000000','1000000002','2023-03-06','I10')")
        c.execute("INSERT INTO claim_lines VALUES "
                  "('C1',1,'E1390',1,100.00,80.00),"
                  "('C2',1,'E1390',1,100.00,80.00),"
                  "('C3',1,'E1390',1,100.00,80.00),"
                  "('C4',1,'E1390',1,300.00,240.00)")                      # 3x median price
        c.commit()


def reasons_by_npi(dsn):
    with psycopg.connect(dsn) as c:
        return dict(c.execute("SELECT npi, reasons FROM provider_risk_scores").fetchall())


def test_rules_flag_expected_providers(clean_db):
    seed(clean_db)
    run_scoring(clean_db, grain="quarter")
    r = reasons_by_npi(clean_db)
    assert "duplicate_billing" in r["1000000000"]
    assert "price_inflation" in r["1000000002"]
    assert r["1000000001"] == {}


def test_scoring_is_idempotent(clean_db):
    seed(clean_db)
    n1 = run_scoring(clean_db, grain="quarter")
    n2 = run_scoring(clean_db, grain="quarter")
    with psycopg.connect(clean_db) as c:
        total = c.execute("SELECT count(*) FROM provider_risk_scores").fetchone()[0]
    assert n1 == n2 == total == 3
