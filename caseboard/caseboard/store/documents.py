"""SQLite document store. Payloads are unstructured JSON."""

import json
import sqlite3
import threading
from pathlib import Path

from pydantic import BaseModel

from caseboard.domain.enums import DocType


class DocumentStore:
    """One collection of JSON documents, with a few keys copied out for filters."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    facet_key TEXT,
                    sensitivity TEXT,
                    matter_id TEXT,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(type)"
            )

    def put(self, doc_type: DocType, record_id: str, payload: BaseModel) -> None:
        body = payload.model_dump(mode="json")
        self._write(
            [(record_id, doc_type.value, _key(body), _sensitivity(body), _matter(body), body)]
        )

    def put_many(self, doc_type: DocType, rows: list[tuple[str, BaseModel]]) -> None:
        packed = []
        for record_id, payload in rows:
            body = payload.model_dump(mode="json")
            packed.append(
                (record_id, doc_type.value, _key(body), _sensitivity(body), _matter(body), body)
            )
        self._write(packed)

    def _write(self, rows: list[tuple[str, str, str | None, str | None, str | None, dict]]) -> None:
        if not rows:
            return
        with self._lock, self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO documents (id, type, facet_key, sensitivity, matter_id, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type = excluded.type,
                    facet_key = excluded.facet_key,
                    sensitivity = excluded.sensitivity,
                    matter_id = excluded.matter_id,
                    payload = excluded.payload
                """,
                [
                    (row[0], row[1], row[2], row[3], row[4], json.dumps(row[5]))
                    for row in rows
                ],
            )

    def delete_type(self, doc_type: DocType, *, origin: str | None = None) -> None:
        with self._lock, self._connect() as conn:
            if origin is None:
                conn.execute("DELETE FROM documents WHERE type = ?", (doc_type.value,))
                return
            conn.execute(
                """
                DELETE FROM documents
                WHERE type = ? AND json_extract(payload, '$.origin') = ?
                """,
                (doc_type.value, origin),
            )

    def list_types(self, doc_types: list[DocType]) -> dict[DocType, list[dict]]:
        return {doc_type: self.list_type(doc_type) for doc_type in doc_types}

    def get(self, doc_type: DocType, record_id: str) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM documents WHERE type = ? AND id = ?",
                (doc_type.value, record_id),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload"])
        payload["id"] = record_id
        return payload

    def list_type(
        self,
        doc_type: DocType,
        *,
        sensitivity: str | None = None,
    ) -> list[dict]:
        query = "SELECT id, payload FROM documents WHERE type = ?"
        params: list[str] = [doc_type.value]
        if sensitivity is not None:
            query += " AND sensitivity = ?"
            params.append(sensitivity)
        with self._lock, self._connect() as conn:
            found = conn.execute(query, params).fetchall()
        rows = []
        for row in found:
            payload = json.loads(row["payload"])
            payload["id"] = row["id"]
            rows.append(payload)
        return rows

    def delete_ids(self, doc_type: DocType, ids: list[str]) -> None:
        if not ids:
            return
        marks = ",".join("?" for _ in ids)
        with self._lock, self._connect() as conn:
            conn.execute(
                f"DELETE FROM documents WHERE type = ? AND id IN ({marks})",
                [doc_type.value, *ids],
            )

    def counts(self) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            found = conn.execute(
                "SELECT type, COUNT(*) AS n FROM documents GROUP BY type"
            ).fetchall()
        return {row["type"]: int(row["n"]) for row in found}


def _key(body: dict) -> str | None:
    value = body.get("facet_key")
    return str(value) if value else None


def _sensitivity(body: dict) -> str | None:
    value = body.get("sensitivity")
    return str(value) if value else None


def _matter(body: dict) -> str | None:
    value = body.get("matter_id")
    return str(value) if value else None
