import pytest


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "store.sqlite"
