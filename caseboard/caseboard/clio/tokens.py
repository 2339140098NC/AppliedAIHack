"""Persist the single-firm Clio refresh token outside git."""

import json
import time
from pathlib import Path


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

    def connected(self) -> bool:
        data = self.load()
        return bool(data and data.get("refresh_token") or (data and data.get("access_token")))
