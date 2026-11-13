"""Keep ownership alive during processing; commit effects only through repository."""

import threading


def process_claim(repository, claim, process=None, renew_seconds=3, telemetry=None):
    """process is a side-effect-free preparation callback, also used by tests.

    Shutdown does not release an active callback's claim. If the process is
    killed, PostgreSQL retains the claim until its lease expires.
    """
    finished = threading.Event()
    lost = threading.Event()

    def heartbeat():
        while not finished.wait(renew_seconds):
            try:
                if repository.renew(claim):
                    continue
            except Exception:
                if telemetry is not None:
                    telemetry.errors.labels(operation="renew").inc()
                    telemetry.log(
                        "lease_renewal_error", severity="ERROR", job_id=claim.job_id
                    )
                # stop all business updates and let expiry recover.
                pass
            lost.set()
            return

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    failed = False
    try:
        if process is not None:
            process(claim)
    except Exception:
        failed = True
    finally:
        finished.set()
        thread.join()
    if lost.is_set():
        return "claim_lost"
    if failed:
        return "failure_recorded" if repository.fail(claim) else "claim_lost"
    try:
        return "job_completed" if repository.complete(claim) else "claim_lost"
    except RuntimeError:
        return (
            "failure_recorded"
            if repository.fail(claim, "inventory_invariant_failed")
            else "claim_lost"
        )
