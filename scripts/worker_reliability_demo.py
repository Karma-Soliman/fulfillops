"""Collect real worker reliability evidence using existing isolated test scenarios."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import xml.etree.ElementTree as ET

from sqlalchemy.engine import make_url


SCENARIOS = (
    "test_two_real_workers_expose_health_and_recover_killed_peer",
    "test_poison_processing_callback_reaches_durable_failure",
    "test_third_crashed_attempt_is_failed_without_fourth_claim",
    "test_sigterm_during_active_completion_finishes_without_claiming_more",
)


def validate_target(environment):
    if environment.get("APP_ENV") != "test":
        raise ValueError("APP_ENV must be test")
    raw = environment.get("TEST_DATABASE_URL", "")
    try:
        url = make_url(raw)
    except Exception:
        raise ValueError("Provide a valid TEST_DATABASE_URL") from None
    if (
        url.drivername != "postgresql+psycopg"
        or not (url.database or "").startswith("fulfillops_test")
        or url.host not in {"127.0.0.1", "localhost", "::1"}
    ):
        raise ValueError(
            "Requires local postgresql+psycopg and a dedicated fulfillops_test* database"
        )
    return url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="New evidence directory; must not already exist"
    )
    args = parser.parse_args()
    try:
        url = validate_target(os.environ)
    except ValueError as error:
        parser.error(str(error))
    root = Path(__file__).resolve().parents[1]
    started = datetime.now(timezone.utc)
    output = (
        args.output
        or root
        / "docs"
        / "evidence"
        / f"worker-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:6]}"
    ).resolve()
    output.mkdir(parents=True, exist_ok=False)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        f"--junitxml={output / 'results.xml'}",
    ]
    command.extend(f"tests/worker/test_repository.py::{name}" for name in SCENARIOS)
    environment = dict(os.environ, WORKER_EVIDENCE_DIR=str(output), APP_ENV="test")
    result = subprocess.run(
        command,
        cwd=root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    def redact(content):
        secrets = [
            os.environ["TEST_DATABASE_URL"],
            url.render_as_string(hide_password=False),
            url.password,
        ]
        for secret in sorted((s for s in secrets if s), key=len, reverse=True):
            content = content.replace(secret, "[REDACTED]")
        return content

    (output / "test-output.txt").write_text(redact(result.stdout))
    # Redact test reports and retained logs too, including diagnostics on failures.
    for path in output.rglob("*"):
        if path.is_file():
            path.write_text(redact(path.read_text()))
    cases = []
    if (output / "results.xml").exists():
        for case in ET.parse(output / "results.xml").iter("testcase"):
            status = next(
                (
                    tag
                    for tag in ("failure", "error", "skipped")
                    if case.find(tag) is not None
                ),
                "passed",
            )
            cases.append({"name": case.get("name"), "status": status})
    success = (
        result.returncode == 0
        and len(cases) == len(SCENARIOS)
        and all(case["status"] == "passed" for case in cases)
    )
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    changes = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=root, text=True
    )
    summary = {
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "git_revision": revision,
        "working_tree_status": changes.splitlines(),
        "python_version": sys.version.split()[0],
        "status": "passed" if success else "failed",
        "pytest_exit_code": result.returncode,
        "scenarios": cases,
        "limitations": [
            "Local Python processes and real PostgreSQL; not a container or Kubernetes drill.",
            "Crash-recovery scenario uses four-second leases and natural expiry.",
            "Poison callback runs in test harness; retries are made due via fixture SQL after backoff checks.",
            "Third-crash scenario advances expiry through fixture SQL.",
            "Database snapshots omit customers, keys and lease tokens. URL/password diagnostics are redacted.",
            "Each scenario drops only its own schema after saving evidence.",
            "Metric counters are process-local; killed processes can lose unscripted scrape intervals.",
        ],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(redact(result.stdout), end="")
    print(f"Worker evidence: {output}\nStatus: {summary['status']}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
