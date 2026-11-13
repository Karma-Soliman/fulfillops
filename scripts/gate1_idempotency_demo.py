
"""Reproducible Gate 1 proof: idempotency across two API replicas."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.client import HTTPException
from json import dumps, loads
from threading import Barrier
from time import sleep, time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import subprocess
import sys


PROJECT = "fulfillops-test"
BASE_URL = "http://127.0.0.1:18080"
COMPOSE = [
    "docker", "compose",
    "-f", "compose.yaml",
    "-f", "compose.test.yaml",
    "--project-name", PROJECT,
]
SAME_KEY = "gate1-same-key-20261113"
COMPETING_KEYS = [
    "gate1-competing-key-1-20261113",
    "gate1-competing-key-2-20261113",
]
SAME_PAYLOAD = {
    "customer_id": "gate1-same-key",
    "items": [{"sku": "KIT-100", "quantity": 1}],
}


def run(command):
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def database_snapshot():
    query = """
    SELECT json_build_object(
        'orders', (SELECT count(*)::int FROM orders),
        'jobs', (SELECT count(*)::int FROM jobs),
        'idempotency_keys',
            (SELECT count(*)::int FROM idempotency_keys),
        'inventory', (
            SELECT json_agg(
                json_build_object(
                    'sku', sku,
                    'on_hand', quantity_on_hand,
                    'reserved', quantity_reserved
                ) ORDER BY sku
            )
            FROM inventory
        )
    )::text;
    """
    output = run(
        COMPOSE
        + [
            "exec", "-T", "postgres",
            "psql", "-U", "postgres", "-d", "fulfillops",
            "-At", "-c", query,
        ]
    )
    return loads(output)


def kit_reserved(snapshot):
    for item in snapshot["inventory"]:
        if item["sku"] == "KIT-100":
            return item["reserved"]
    raise AssertionError("KIT-100 is missing from inventory")


def print_snapshot(label, snapshot):
    print(f"\n--- {label} ---", flush=True)
    print(dumps(snapshot, indent=2), flush=True)


def check_replicas():
    ids = run(COMPOSE + ["ps", "-q", "api"]).splitlines()
    if len(ids) != 2:
        raise AssertionError(f"Expected 2 API replicas; found {len(ids)}")

    for container_id in ids:
        health = run([
            "docker", "inspect",
            "--format={{.State.Health.Status}}",
            container_id,
        ])
        if health != "healthy":
            raise AssertionError(
                f"API replica {container_id[:12]} is {health}"
            )

    print("Both API replicas are healthy.", flush=True)
    return ids


def check_load_balancer():
    with urlopen(f"{BASE_URL}/health/ready", timeout=5) as response:
        body = loads(response.read())
        if response.status != 200 or body.get("status") != "ready":
            raise AssertionError(f"Load balancer readiness failed: {body}")
    print("Load balancer readiness: HTTP 200.", flush=True)


def post_order(key, payload, barrier=None):
    if barrier is not None:
        barrier.wait(timeout=15)

    request = Request(
        f"{BASE_URL}/api/v1/orders",
        data=dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": key,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            return response.status, loads(response.read())
    except HTTPError as error:
        return error.code, loads(error.read())


def concurrent_requests(requests):
    barrier = Barrier(len(requests))

    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        futures = [
            executor.submit(post_order, key, payload, barrier)
            for key, payload in requests
        ]
        return [future.result(timeout=30) for future in futures]


def wait_for_replicas():
    deadline = time() + 60

    while time() < deadline:
        try:
            check_replicas()
            check_load_balancer()
            return
        except (subprocess.CalledProcessError, AssertionError, URLError):
            sleep(2)

    raise AssertionError("API replicas did not become healthy within 60s")


def main():
    print("FulfillOps Gate 1 idempotency proof", flush=True)
    print(
        f"Started: {datetime.now(timezone.utc).isoformat()}",
        flush=True,
    )
    print(f"Project: {PROJECT}", flush=True)
    print(f"Load balancer: {BASE_URL}", flush=True)

    replica_ids = check_replicas()
    check_load_balancer()

    before = database_snapshot()
    print_snapshot("INITIAL DATABASE STATE", before)

    if (
        before["orders"] != 0
        or before["jobs"] != 0
        or before["idempotency_keys"] != 0
        or kit_reserved(before) != 0
    ):
        raise AssertionError(
            "Test database is not clean. Reset the isolated test project first."
        )

    # Test 1: eight simultaneous requests using the same key.
    print("\nTEST 1: Eight simultaneous same-key requests", flush=True)
    same_requests = [
        (SAME_KEY, SAME_PAYLOAD) for _ in range(8)
    ]
    same_results = concurrent_requests(same_requests)

    for index, (status, body) in enumerate(same_results, start=1):
        print(f"Request {index}: HTTP {status}, {body}", flush=True)

    if any(status != 202 for status, _ in same_results):
        raise AssertionError("Not all same-key requests returned HTTP 202.")

    same_order_ids = {body["order_id"] for _, body in same_results}
    if len(same_order_ids) != 1:
        raise AssertionError(f"Different order IDs returned: {same_order_ids}")

    original_order_id = same_order_ids.pop()
    after_same = database_snapshot()
    print_snapshot("DATABASE AFTER SAME-KEY TEST", after_same)

    if (
        after_same["orders"] != 1
        or after_same["jobs"] != 1
        or after_same["idempotency_keys"] != 1
        or kit_reserved(after_same) != 1
    ):
        raise AssertionError("Same-key test did not create exactly one order.")

    print(f"PASS: all 8 requests returned order {original_order_id}", flush=True)

    # Test 2: two different keys compete for four remaining KIT-100 units.
    print("\nTEST 2: Competing different-key requests", flush=True)
    competing_requests = [
        (
            COMPETING_KEYS[0],
            {
                "customer_id": "gate1-competing-1",
                "items": [{"sku": "KIT-100", "quantity": 4}],
            },
        ),
        (
            COMPETING_KEYS[1],
            {
                "customer_id": "gate1-competing-2",
                "items": [{"sku": "KIT-100", "quantity": 4}],
            },
        ),
    ]
    competing_results = concurrent_requests(competing_requests)

    for index, (status, body) in enumerate(competing_results, start=1):
        print(f"Request {index}: HTTP {status}, {body}", flush=True)

    statuses = sorted(status for status, _ in competing_results)
    if statuses != [202, 409]:
        raise AssertionError(
            f"Expected one HTTP 202 and one HTTP 409; got {statuses}"
        )

    after_competing = database_snapshot()
    print_snapshot("DATABASE AFTER COMPETING-KEY TEST", after_competing)

    if (
        after_competing["orders"] != 2
        or after_competing["jobs"] != 2
        or after_competing["idempotency_keys"] != 2
        or kit_reserved(after_competing) != 5
    ):
        raise AssertionError("Competing-key stock or database counts are wrong.")

    print("PASS: exactly one competing request succeeded.", flush=True)

    # Test 3: restart one API replica, then replay the original request.
    print("\nTEST 3: Restart one API replica and replay original request", flush=True)
    restarted_id = replica_ids[0]
    print(f"Restarting API container {restarted_id[:12]}", flush=True)
    run(["docker", "restart", restarted_id])
    wait_for_replicas()

    replay_status, replay_body = post_order(SAME_KEY, SAME_PAYLOAD)
    print(
        f"Replay: HTTP {replay_status}, {replay_body}",
        flush=True,
    )

    if replay_status != 202:
        raise AssertionError("Replay did not return HTTP 202.")

    if replay_body.get("order_id") != original_order_id:
        raise AssertionError("Replay returned a different order ID.")

    final = database_snapshot()
    print_snapshot("FINAL DATABASE STATE", final)

    if final != after_competing:
        raise AssertionError("Replay changed the database state.")

    print("\nPASS: replay returned the original order ID.", flush=True)
    print("PASS: replay created no duplicate order, job, or reservation.", flush=True)
    print("\nGATE 1 RESULT: ALL CHECKS PASSED", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (
        AssertionError,
        HTTPException,
        HTTPError,
        URLError,
        subprocess.CalledProcessError,
        KeyError,
        ValueError,
        TimeoutError,
    ) as error:
        print(f"\nGATE 1 RESULT: FAILED — {error}", file=sys.stderr, flush=True)
        sys.exit(1)
