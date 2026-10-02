"""Persist the Clio token in Upstash, with a local file when Redis is not configured."""

import json
import time
from pathlib import Path
from typing import Protocol

SESSION_COOKIE = "clio_session"
_TOKEN_KEY = "cb:clio:token"


class TokenCache(Protocol):
    """The two Redis commands the Clio session needs."""

    def get(self, key: str) -> str | None:
        """Return the stored JSON, or None when the key is missing."""

    def set(self, key: str, value: str) -> object:
        """Store the JSON payload."""


class TokenStore:
    def __init__(self, path: Path, cache: TokenCache | None = None) -> None:
        self._path = path
        self._cache = cache

    def load(self) -> dict | None:
        remote = self._read_cache()
        if remote is not None:
            return remote
        if not self._path.exists():
            return None
        return json.loads(self._path.read_text())

    def save(self, payload: dict) -> None:
        body = dict(payload)
        body["obtained_at"] = time.time()
        self._write(body)

    def adopt(self, raw: str | None) -> None:
        """Copy a browser cookie in when this store does not already have a token."""
        if self.connected() or not raw:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        if payload.get("refresh_token") or payload.get("access_token"):
            self._write(payload)

    def export(self) -> str | None:
        data = self.load()
        if not data or not (data.get("refresh_token") or data.get("access_token")):
            return None
        return json.dumps(data)

    def connected(self) -> bool:
        data = self.load()
        return bool(data and (data.get("refresh_token") or data.get("access_token")))

    def _read_cache(self) -> dict | None:
        if self._cache is None:
            return None
        raw = self._cache.get(_TOKEN_KEY)
        if not raw:
            return None
        return json.loads(raw)

    def _write(self, payload: dict) -> None:
        text = json.dumps(payload)
        if self._cache is not None:
            self._cache.set(_TOKEN_KEY, text)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(text)
