from threading import Event
from unittest.mock import Mock

from worker.processor import process_claim


def test_processing_failure_records_retry_without_completion():
    repo = Mock()
    repo.fail.return_value = True

    def poison(_claim):
        raise ValueError("deterministic test poison")

    assert process_claim(repo, "claim", poison) == "failure_recorded"
    repo.fail.assert_called_once_with("claim")
    repo.complete.assert_not_called()


def test_heartbeat_keeps_active_processing_owned():
    repo = Mock()
    renewed = Event()

    def renew(_claim):
        renewed.set()
        return True

    repo.renew.side_effect = renew
    repo.complete.return_value = True

    def prepare(_claim):
        assert renewed.wait(2)

    assert process_claim(repo, "claim", prepare, renew_seconds=0.01) == "job_completed"
    repo.renew.assert_called()
    repo.complete.assert_called_once_with("claim")


def test_uncertain_renewal_prevents_all_finalization():
    repo = Mock()
    attempted = Event()

    def broken_renew(_claim):
        attempted.set()
        raise ConnectionError("database offline")

    repo.renew.side_effect = broken_renew

    def prepare(_claim):
        assert attempted.wait(2)

    assert process_claim(repo, "claim", prepare, renew_seconds=0.01) == "claim_lost"
    repo.complete.assert_not_called()
    repo.fail.assert_not_called()


def test_recorded_ownership_loss_prevents_finalization():
    repo = Mock()
    attempted = Event()

    def renew(_claim):
        attempted.set()
        return False

    repo.renew.side_effect = renew

    def prepare(_claim):
        assert attempted.wait(2)

    assert process_claim(repo, "claim", prepare, renew_seconds=0.01) == "claim_lost"
    repo.complete.assert_not_called()
    repo.fail.assert_not_called()
