import pytest
from safepay.db import init_db, make_engine


@pytest.fixture()
def sf():
    engine = make_engine()
    yield init_db(engine)
    engine.dispose()
