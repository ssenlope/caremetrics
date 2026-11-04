import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app


@pytest.fixture()
def client(clean_db):
    with psycopg.connect(clean_db) as c:
        c.execute("INSERT INTO providers VALUES "
                  "('1000000000','Acme DME','DME Supplier','CA'),"
                  "('1000000001','Dr. Who','Cardiology','TX')")
        c.execute("INSERT INTO beneficiaries VALUES ('B000000000',1940,'M','CA')")
        c.execute("INSERT INTO claims VALUES "
                  "('C1','B000000000','1000000000','2023-03-05','I10'),"
                  "('C2','B000000000','1000000000','2023-03-20','I10'),"
                  "('C3','B000000000','1000000000','2023-04-02','I10')")
        c.execute("INSERT INTO claim_lines VALUES "
                  "('C1',1,'E1390',1,100.00,80.00),"
                  "('C1',2,'A4604',2,40.00,30.00),"
                  "('C2',1,'E1390',1,200.00,160.00),"
                  "('C3',1,'A4604',1,10.00,8.00),"
                  "('C3',2,'A4604',1,10.00,8.00),"
                  "('C3',3,'A4604',1,10.00,8.00)")
        c.commit()

    engine = create_engine(clean_db.replace("postgresql://", "postgresql+psycopg://"))
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


def test_provider_summary_uses_correct_grain(client):
    r = client.get("/providers/1000000000")
    assert r.status_code == 200
    d = r.json()
    assert d["claim_count"] == 3      # not 6 (that would be the line count)
    assert d["line_count"] == 6
    assert d["total_billed"] == pytest.approx(370.0)
    assert d["total_paid"] == pytest.approx(294.0)


def test_provider_without_claims_returns_zeros(client):
    d = client.get("/providers/1000000001").json()
    assert d["claim_count"] == 0 and d["line_count"] == 0


def test_unknown_provider_404(client):
    assert client.get("/providers/9999999999").status_code == 404
    assert client.get("/providers/9999999999/claims").status_code == 404


def test_claims_pagination_and_date_filter(client):
    d = client.get("/providers/1000000000/claims?page=1&size=2").json()
    assert d["total"] == 3 and len(d["items"]) == 2
    d2 = client.get("/providers/1000000000/claims?page=2&size=2").json()
    assert len(d2["items"]) == 1
    d3 = client.get("/providers/1000000000/claims?start=2023-04-01").json()
    assert d3["total"] == 1 and d3["items"][0]["claim_id"] == "C3"
    assert d3["items"][0]["line_count"] == 3


def test_page_size_limit(client):
    assert client.get("/providers/1000000000/claims?size=101").status_code == 422


def test_monthly_volume(client):
    d = client.get("/analytics/provider-monthly-volume?month=2023-03").json()
    assert len(d) == 1
    assert d[0]["claim_count"] == 2 and d[0]["line_count"] == 3
    assert client.get("/analytics/provider-monthly-volume?month=2023-13").status_code == 422


def test_hcpcs_pricing_is_unit_weighted(client):
    d = {x["hcpcs_code"]: x for x in client.get("/analytics/hcpcs-pricing").json()}
    assert d["E1390"]["avg_unit_billed"] == pytest.approx(150.0)   # 300 / 2 units
    assert d["A4604"]["total_units"] == 5                          # 2 + 1 + 1 + 1


def test_state_spend(client):
    d = client.get("/analytics/state-spend").json()
    assert len(d) == 1 and d[0]["state"] == "CA"
    assert d[0]["claim_count"] == 3 and d[0]["line_count"] == 6
