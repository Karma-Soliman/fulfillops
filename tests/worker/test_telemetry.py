import io
import json
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
from prometheus_client import generate_latest

from worker.telemetry import HealthServer, Telemetry


def test_health_and_metrics_are_available_without_database():
    telemetry = Telemetry("test-worker", stream=io.StringIO())
    server = HealthServer(telemetry, host="127.0.0.1", port=0)
    server.start()
    base = f"http://127.0.0.1:{server.server.server_port}"
    try:
        with urlopen(base + "/health/live", timeout=2) as response:
            assert response.status == 200
            assert json.load(response) == {"status": "ok"}
        with urlopen(base + "/metrics", timeout=2) as response:
            assert response.headers["Content-Type"].startswith("text/plain")
            output = response.read().decode()
            for name in ("fulfillops_worker_claims_total", "fulfillops_orders_failed_total",
                         "fulfillops_worker_retries_total", "fulfillops_worker_active_jobs"):
                assert name in output
        with pytest.raises(HTTPError) as error:
            urlopen(base + "/unknown", timeout=2)
        assert error.value.code == 404
        error.value.close()
    finally:
        server.close()
    assert not server.thread.is_alive()


def test_replica_registries_are_independent_and_labels_are_bounded():
    first = Telemetry("worker-one", stream=io.StringIO())
    second = Telemetry("worker-two", stream=io.StringIO())
    first.record("job_claimed", attempt=1, recovered=False, job_id="test-id")
    first.record("job_claimed", attempt=2, recovered=True, job_id="test-id")
    first.record("retry_scheduled", delay_seconds=1)
    first.record("job_failed")
    first.duration.labels(outcome="failure_recorded").observe(0.1)
    assert first.registry.get_sample_value("fulfillops_worker_claims_total") == 2
    assert first.registry.get_sample_value("fulfillops_worker_retries_total") == 1
    assert first.registry.get_sample_value("fulfillops_worker_recoveries_total") == 1
    assert first.registry.get_sample_value("fulfillops_orders_failed_total") == 1
    assert second.registry.get_sample_value("fulfillops_worker_claims_total") == 0
    assert first.registry.get_sample_value("fulfillops_worker_processing_duration_seconds_count",
                                          {"outcome": "failure_recorded"}) == 1
    text = generate_latest(first.registry).decode()
    assert "test-id" not in text and "worker-one" not in text


def test_json_logging_filters_secrets_and_honors_log_level():
    stream = io.StringIO()
    telemetry = Telemetry("worker", stream=stream, level="WARNING")
    telemetry.log("hidden_info")
    telemetry.log("safe_error", severity="ERROR", job_id="job", password="secret",
                  lease_token="token", idempotency_key="client-secret", exception="raw SQL")
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(records) == 1
    assert records[0]["level"] == "ERROR"
    assert records[0]["timestamp"].endswith("+00:00")
    assert records[0]["job_id"] == "job"
    assert set(records[0]) == {"timestamp", "level", "event", "worker_id", "job_id"}
