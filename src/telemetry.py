"""tiny telemetry sender for tier1 mode"""

import queue
import threading
import time
from datetime import datetime, timezone

import requests


class TelemetryClient:
    """best-effort telemetry batching + send loop"""

    def __init__(
        self,
        *,
        enabled: bool,
        device_id: str,
        identity_provider,
        control_plane_url: str,
        telemetry_path: str,
        device_token: str | None,
        flush_interval_s: float,
        batch_size: int,
        logger,
    ):
        self.enabled = enabled
        self.device_id = device_id
        self.identity_provider = identity_provider
        self.control_plane_url = control_plane_url.rstrip("/")
        self.telemetry_path = telemetry_path if telemetry_path.startswith("/") else f"/{telemetry_path}"
        self.device_token = device_token
        self.flush_interval_s = flush_interval_s
        self.batch_size = batch_size
        self.logger = logger

        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()

        self.batches_sent = 0
        self.send_failures = 0

        self._worker = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if not self.enabled:
            return
        self._worker.start()

    def stop(self):
        if not self.enabled:
            return
        self._stop.set()

    def enqueue(self, event: dict):
        if not self.enabled:
            return
        try:
            self._q.put_nowait(event)
        except Exception:
            # if this somehow fails, dont break inference
            pass

    def backlog(self) -> int:
        if not self.enabled:
            return 0
        return self._q.qsize()

    def stats(self) -> dict:
        return {
            "telemetry_enabled": bool(self.enabled),
            "telemetry_backlog_events": self.backlog(),
            "telemetry_batches_sent": self.batches_sent,
            "telemetry_send_failures": self.send_failures,
        }

    def _make_payload(self, events: list[dict]) -> dict:
        ident = {}
        try:
            ident = self.identity_provider() or {}
        except Exception:
            ident = {}

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "device_id": self.device_id,
            "edge_time": now,
            "model_version": ident.get("model_version", "unknown"),
            "model_sha256": ident.get("model_sha256", "unknown"),
            "events": events,
        }

    def _send_batch(self, events: list[dict]) -> bool:
        url = f"{self.control_plane_url}{self.telemetry_path}"
        headers = {"content-type": "application/json"}
        if self.device_token:
            headers["authorization"] = f"Bearer {self.device_token}"

        payload = self._make_payload(events)
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=3)
            if 200 <= resp.status_code < 300:
                self.batches_sent += 1
                return True
            self.send_failures += 1
            self.logger.warning(
                f"telemetry send failed: {resp.status_code}",
                extra={"telemetry_url": url},
            )
            return False
        except Exception as e:
            self.send_failures += 1
            self.logger.warning(
                f"telemetry send error: {e}",
                extra={"telemetry_url": url},
            )
            return False

    def _drain_events(self) -> list[dict]:
        events: list[dict] = []
        try:
            first = self._q.get(timeout=self.flush_interval_s)
            events.append(first)
        except queue.Empty:
            return []

        while len(events) < self.batch_size:
            try:
                events.append(self._q.get_nowait())
            except queue.Empty:
                break

        return events

    def _run(self):
        # best effort loop - should never crash the process
        while not self._stop.is_set():
            if not self.enabled:
                time.sleep(1)
                continue

            events = self._drain_events()
            if not events:
                continue

            ok = self._send_batch(events)
            if not ok:
                # for now we drop; commit 5 adds disk spool
                pass

