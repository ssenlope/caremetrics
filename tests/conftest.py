import psycopg
import pytest
from sqlalchemy import create_engine

from app import models  # noqa: F401
from app.config import settings
from app.db import Base

ADMIN_DSN = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
TEST_DSN = ADMIN_DSN.rsplit("/", 1)[0] + "/caremetrics_test"


@pytest.fixture(scope="session")
def test_dsn():
    with psycopg.connect(ADMIN_DSN, autocommit=True) as c:
        exists = c.execute("SELECT 1 FROM pg_database WHERE datname = 'caremetrics_test'").fetchone()
        if not exists:
            c.execute("CREATE DATABASE caremetrics_test")
    return TEST_DSN


@pytest.fixture()
def clean_db(test_dsn):
    engine = create_engine(test_dsn.replace("postgresql://", "postgresql+psycopg://"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield test_dsn
    engine.dispose()
