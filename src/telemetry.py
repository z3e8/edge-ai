"""tiny telemetry sender for tier1 mode"""

import json
import os
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
        spool_dir: str | None,
        spool_max_files: int,
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
        self.spool_dir = spool_dir.strip() if spool_dir else None
        self.spool_max_files = max(0, int(spool_max_files))
        self.logger = logger

        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()

        self.batches_sent = 0
        self.send_failures = 0

        self._worker = threading.Thread(target=self._run, daemon=True)

        if self.enabled and self.spool_dir:
            try:
                os.makedirs(self.spool_dir, exist_ok=True)
            except Exception as e:
                self.logger.warning(f"telemetry spool dir create failed: {e}")
                self.spool_dir = None

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
            "telemetry_spool_files": self._spool_count(),
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

    def _spool_count(self) -> int:
        if not self.enabled or not self.spool_dir:
            return 0
        try:
            return len(self._list_spool_files())
        except Exception:
            return 0

    def _list_spool_files(self) -> list[str]:
        if not self.spool_dir:
            return []
        files = []
        for name in os.listdir(self.spool_dir):
            if name.endswith(".json"):
                files.append(os.path.join(self.spool_dir, name))
        files.sort()
        return files

    def _enforce_spool_cap(self):
        if not self.spool_dir or self.spool_max_files <= 0:
            return
        try:
            files = self._list_spool_files()
            if len(files) <= self.spool_max_files:
                return
            extra = len(files) - self.spool_max_files
            for path in files[:extra]:
                try:
                    os.remove(path)
                except Exception:
                    pass
            self.logger.warning(f"telemetry spool cap hit, dropped {extra} files")
        except Exception:
            # if this breaks, we still want inference to run
            pass

    def _spool_write(self, events: list[dict]):
        if not self.spool_dir:
            return
        try:
            ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            fname = f"{ts}_{int(time.time() * 1000)}.json"
            path = os.path.join(self.spool_dir, fname)
            with open(path, "w") as f:
                json.dump({"events": events}, f)
            self._enforce_spool_cap()
        except Exception as e:
            self.logger.warning(f"telemetry spool write failed: {e}")

    def _drain_spool_once(self) -> bool:
        if not self.spool_dir:
            return True
        files = self._list_spool_files()
        if not files:
            return True

        path = files[0]
        try:
            with open(path, "r") as f:
                data = json.load(f)
            events = data.get("events") if isinstance(data, dict) else None
            if not isinstance(events, list):
                os.remove(path)
                return True
        except Exception:
            # corrupted file, just drop it
            try:
                os.remove(path)
            except Exception:
                pass
            return True

        ok = self._send_batch(events)
        if ok:
            try:
                os.remove(path)
            except Exception:
                pass
        return ok

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

            cp_ok = True
            # drain old stuff first so ordering is roughly preserved
            while self.spool_dir:
                try:
                    ok = self._drain_spool_once()
                    if not ok:
                        cp_ok = False
                        break
                except Exception:
                    break
                # only do one per loop unless we have backlog
                if self._spool_count() == 0:
                    break

            events = self._drain_events()
            if not events:
                continue

            if not cp_ok:
                self._spool_write(events)
                continue

            ok = self._send_batch(events)
            if not ok:
                self._spool_write(events)

