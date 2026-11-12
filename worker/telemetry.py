"""Process-local worker metrics and safe JSON events; scrape each replica."""
import json
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client import CONTENT_TYPE_LATEST


class Telemetry:
    def __init__(self, worker_id, stream=None, level="INFO"):
        self.worker_id = worker_id
        self.stream = stream if stream is not None else sys.stdout
        self.level = level.upper()
        self._log_lock = threading.Lock()
        self.registry = CollectorRegistry()
        self.claims = Counter("fulfillops_worker_claims_total", "Committed claims including reclaims", registry=self.registry)
        self.retries = Counter("fulfillops_worker_retries_total", "Committed claims after the first attempt", registry=self.registry)
        self.recovered = Counter("fulfillops_worker_recoveries_total", "Committed reclaims after lease expiry", registry=self.registry)
        self.completed = Counter("fulfillops_worker_completed_total", "Committed fulfilled orders", registry=self.registry)
        self.failed = Counter("fulfillops_orders_failed_total", "Committed terminally failed orders", registry=self.registry)
        self.scheduled = Counter("fulfillops_worker_retries_scheduled_total", "Committed retry schedules", registry=self.registry)
        self.renewals = Counter("fulfillops_worker_lease_renewals_total", "Committed lease renewals", registry=self.registry)
        self.lost = Counter("fulfillops_worker_claims_lost_total", "Attempts abandoned without valid ownership", registry=self.registry)
        self.errors = Counter("fulfillops_worker_database_errors_total", "Database operation errors", ["operation"], registry=self.registry)
        self.active = Gauge("fulfillops_worker_active_jobs", "Jobs currently processed by this worker", registry=self.registry)
        self.duration = Histogram("fulfillops_worker_processing_duration_seconds", "Attempt duration, excluding queue time", ["outcome"], registry=self.registry)

    def log(self, event, severity="INFO", **fields):
        priorities = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        if priorities[severity] < priorities.get(self.level, 20):
            return
        # Only explicitly allowed fields can enter output, never exception objects.
        safe = {key: value for key, value in fields.items()
                if key in {"job_id", "order_id", "attempt", "recovered", "delay_seconds", "reason", "operation"}}
        record = {"timestamp": datetime.now(timezone.utc).isoformat(),
                  "level": severity, "event": event, "worker_id": self.worker_id, **safe}
        with self._log_lock:
            print(json.dumps(record, default=str), file=self.stream, flush=True)

    def record(self, event, **fields):
        """Called by the repository only after successful transaction commit."""
        if event == "job_claimed":
            self.claims.inc()
            if fields["attempt"] > 1:
                self.retries.inc()
            if fields["recovered"]:
                self.recovered.inc()
        elif event == "job_completed":
            self.completed.inc()
        elif event == "job_failed":
            self.failed.inc()
        elif event == "retry_scheduled":
            self.scheduled.inc()
        elif event == "lease_renewed":
            self.renewals.inc()
        self.log(event, severity="DEBUG" if event == "lease_renewed" else "INFO", **fields)


class HealthServer:
    def __init__(self, telemetry, host="0.0.0.0", port=9100):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/health/live":
                    body, status, content_type = b'{"status":"ok"}', 200, "application/json"
                elif self.path == "/metrics":
                    body, status, content_type = generate_latest(telemetry.registry), 200, CONTENT_TYPE_LATEST
                else:
                    body, status, content_type = b"not found", 404, "text/plain"
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.1}, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
