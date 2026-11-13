import pytest

from scripts.worker_reliability_demo import validate_target


@pytest.mark.parametrize("environment", [
    {},
    {"APP_ENV": "production", "TEST_DATABASE_URL": "postgresql+psycopg://localhost/fulfillops_test"},
    {"APP_ENV": "test", "TEST_DATABASE_URL": "postgresql+psycopg://localhost/fulfillops"},
    {"APP_ENV": "test", "TEST_DATABASE_URL": "postgresql+psycopg://remote.example/fulfillops_test"},
    {"APP_ENV": "test", "TEST_DATABASE_URL": "sqlite:///fulfillops_test"},
    {"APP_ENV": "test", "TEST_DATABASE_URL": "invalid"},
])
def test_evidence_runner_refuses_unsafe_targets(environment):
    with pytest.raises(ValueError):
        validate_target(environment)


def test_evidence_runner_accepts_local_dedicated_test_database():
    url = validate_target({"APP_ENV": "test",
                           "TEST_DATABASE_URL": "postgresql+psycopg://localhost/fulfillops_test_worker"})
    assert url.database == "fulfillops_test_worker"
