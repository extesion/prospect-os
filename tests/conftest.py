import os

import pytest

# Must be set before pytest imports any application module during collection.
os.environ["DATABASE_URL"] = "sqlite:///./test_prospector.db"
os.environ["SECRET_KEY"] = "test-secret-key-12345"

from backend.database.connection import Base, engine
import backend.database.models  # noqa: F401 - register complete application schema
import qualifier.models  # noqa: F401 - register qualification schema
from backend.seed import seed


@pytest.fixture(autouse=True)
def complete_test_schema():
    """Keep every test independent from collection/import order and prior DB teardown."""
    Base.metadata.create_all(bind=engine)
    seed()
    yield
