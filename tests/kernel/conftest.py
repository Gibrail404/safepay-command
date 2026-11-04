import os
import pytest
from safepay.db import Base, init_db, make_engine

# Set SAFEPAY_TEST_DATABASE_URL to run the same tests against PostgreSQL (see docker-compose.yml). Default is in-memory SQLite.
TEST_DB_URL = os.environ.get("SAFEPAY_TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")


def fresh_engine():
    engine = make_engine(TEST_DB_URL)
    Base.metadata.drop_all(engine)
    return engine


@pytest.fixture()
def sf():
    engine = fresh_engine()
    yield init_db(engine)
    engine.dispose()
