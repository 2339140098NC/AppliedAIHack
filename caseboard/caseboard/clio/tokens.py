"""Persist the Clio token in a local file and a browser cookie."""

import json
import time
from pathlib import Path

SESSION_COOKIE = "clio_session"


class TokenStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> dict | None:
        if not self._path.exists():
            return None
        return json.loads(self._path.read_text())

    def save(self, payload: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(payload)
        payload["obtained_at"] = time.time()
        self._path.write_text(json.dumps(payload))

    def adopt(self, raw: str | None) -> None:
        """Load a cookie onto this instance when the local file is missing."""
        if self._path.exists() or not raw:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        if payload.get("refresh_token") or payload.get("access_token"):
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(payload))

    def export(self) -> str | None:
        data = self.load()
        if not data or not (data.get("refresh_token") or data.get("access_token")):
            return None
        return json.dumps(data)

    def connected(self) -> bool:
        data = self.load()
        return bool(data and (data.get("refresh_token") or data.get("access_token")))
