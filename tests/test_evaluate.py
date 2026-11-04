import psycopg
import pytest

from app.services.evaluate import evaluate


def test_precision_recall_and_hit_rates(clean_db, tmp_path):
    with psycopg.connect(clean_db) as c:
        c.execute("INSERT INTO providers VALUES "
                  "('1000000000','A','DME Supplier','CA'),"
                  "('1000000001','B','DME Supplier','CA'),"
                  "('1000000002','C','DME Supplier','CA')")
        c.execute("INSERT INTO provider_risk_scores VALUES "
                  "('1000000000','2023-01-01',0.9,'{\"high_volume\": {}}'),"
                  "('1000000001','2023-01-01',0.5,'{}'),"
                  "('1000000002','2023-01-01',0.1,'{}')")
        c.commit()
    truth = tmp_path / "gt.csv"
    truth.write_text("npi,fraud_type\n1000000000,high_volume\n")

    res = evaluate(clean_db, str(truth), ks=(1, 2))
    assert res["overall"][1]["precision"] == 1.0
    assert res["overall"][2]["precision"] == pytest.approx(0.5)
    assert res["overall"][2]["recall"] == 1.0
    assert res["base_rate"] == pytest.approx(1 / 3)
    assert res["hit_rates"]["high_volume"]["high_volume"] == 1.0
    assert res["hit_rates"]["not_fraud"]["high_volume"] == 0.0
