"""Single in-process job so extract and sync do not overlap."""

import threading

from caseboard.errors import CaseboardError


class Job:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running = False
        self.name = ""
        self.message = "Idle"
        self.error = ""

    def start(self, name: str) -> None:
        with self._lock:
            if self.running:
                raise CaseboardError("Another job is already running")
            self.running = True
            self.name = name
            self.error = ""
            self.message = "Starting"

    def update(self, message: str) -> None:
        with self._lock:
            self.message = message

    def finish(self, message: str, error: str = "") -> None:
        with self._lock:
            self.running = False
            self.message = message
            self.error = error

    def snapshot(self) -> dict[str, str | bool]:
        with self._lock:
            return {
                "running": self.running,
                "name": self.name,
                "message": self.message,
                "error": self.error,
            }
