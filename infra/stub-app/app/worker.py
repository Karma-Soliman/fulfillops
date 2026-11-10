import json
import logging
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), stream=__import__("sys").stdout)
logger = logging.getLogger("fulfillops.stub.worker")
HEARTBEATS = Counter("fulfillops_worker_heartbeats_total", "Worker heartbeat count")
stopping = threading.Event()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health/live":
            body, status, content_type = b'{"status":"ok"}', 200, "application/json"
        elif self.path == "/metrics":
            body, status, content_type = generate_latest(), 200, CONTENT_TYPE_LATEST
        else:
            body, status, content_type = b"not found", 404, "text/plain"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


def main():
    server = ThreadingHTTPServer(("0.0.0.0", 9100), Handler)
    server.timeout = 0.25
    server_thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True)
    server_thread.start()

    def stop(_signum, _frame):
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping.is_set():
            HEARTBEATS.inc()
            logger.info(json.dumps({"event": "heartbeat", "hostname": os.getenv("HOSTNAME", "unknown")}))
            stopping.wait(2)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=1)


if __name__ == "__main__":
    main()
