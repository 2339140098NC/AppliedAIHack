"""JSON document store on Upstash Redis. Survives a new Vercel instance."""

import json
from collections.abc import Iterable

from pydantic import BaseModel
from upstash_redis import Redis

from caseboard.domain.enums import DocType

_BATCH = 80
_PRESENCE_ONLY = {DocType.portrait}


class UpstashDocumentStore:
    """Same operations as the SQLite store, keyed by document type and id."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def put(self, doc_type: DocType, record_id: str, payload: BaseModel) -> None:
        self.put_many(doc_type, [(record_id, payload)])

    def put_many(self, doc_type: DocType, rows: list[tuple[str, BaseModel]]) -> None:
        if not rows:
            return
        index = _index(doc_type)
        for batch in _chunks(rows, _BATCH):
            pipe = self._redis.pipeline()
            for record_id, payload in batch:
                body = payload.model_dump(mode="json")
                pipe.set(_doc_key(doc_type, record_id), json.dumps(body))
                pipe.sadd(index, record_id)
            pipe.exec()

    def delete_type(self, doc_type: DocType, *, origin: str | None = None) -> None:
        if origin is None:
            self.delete_ids(doc_type, self._members(doc_type))
            self._redis.delete(_index(doc_type))
            return
        matched = [
            str(row["id"])
            for row in self.list_type(doc_type)
            if row.get("origin") == origin
        ]
        self.delete_ids(doc_type, matched)

    def delete_ids(self, doc_type: DocType, ids: list[str]) -> None:
        if not ids:
            return
        index = _index(doc_type)
        for batch in _chunks(ids, _BATCH):
            pipe = self._redis.pipeline()
            pipe.delete(*[_doc_key(doc_type, record_id) for record_id in batch])
            pipe.srem(index, *batch)
            pipe.exec()

    def list_types(self, doc_types: list[DocType]) -> dict[DocType, list[dict]]:
        """Read several types in two round trips. Portrait stays a presence check."""
        grouped = {doc_type: [] for doc_type in doc_types}
        if not doc_types:
            return grouped
        pipe = self._redis.pipeline()
        for doc_type in doc_types:
            pipe.smembers(_index(doc_type))
        found = pipe.exec()
        keys: list[str] = []
        owners: list[tuple[DocType, str]] = []
        for doc_type, ids in zip(doc_types, found):
            members = [str(item) for item in (ids or [])]
            if doc_type in _PRESENCE_ONLY:
                grouped[doc_type] = [{"id": record_id} for record_id in members]
                continue
            for record_id in members:
                keys.append(_doc_key(doc_type, record_id))
                owners.append((doc_type, record_id))
        raws: list = []
        chunks = list(_chunks(keys, _BATCH))
        if chunks:
            pipe = self._redis.pipeline()
            for chunk in chunks:
                pipe.mget(*chunk)
            for chunk in pipe.exec() or []:
                raws.extend(chunk or [])
        for (doc_type, record_id), raw in zip(owners, raws):
            if not raw:
                continue
            payload = json.loads(raw)
            payload["id"] = record_id
            grouped[doc_type].append(payload)
        return grouped

    def get(self, doc_type: DocType, record_id: str) -> dict | None:
        raw = self._redis.get(_doc_key(doc_type, record_id))
        if not raw:
            return None
        payload = json.loads(raw)
        payload["id"] = record_id
        return payload

    def list_type(self, doc_type: DocType, *, sensitivity: str | None = None) -> list[dict]:
        ids = self._members(doc_type)
        rows: list[dict] = []
        for batch in _chunks(ids, _BATCH):
            found = self._redis.mget(*[_doc_key(doc_type, record_id) for record_id in batch])
            for record_id, raw in zip(batch, found or []):
                if not raw:
                    continue
                payload = json.loads(raw)
                if sensitivity is not None and str(payload.get("sensitivity") or "") != sensitivity:
                    continue
                payload["id"] = record_id
                rows.append(payload)
        return rows

    def counts(self) -> dict[str, int]:
        types = list(DocType)
        pipe = self._redis.pipeline()
        for doc_type in types:
            pipe.scard(_index(doc_type))
        found = pipe.exec()
        return {
            doc_type.value: int(count or 0)
            for doc_type, count in zip(types, found)
            if int(count or 0)
        }

    def _members(self, doc_type: DocType) -> list[str]:
        found = self._redis.smembers(_index(doc_type)) or []
        return [str(item) for item in found]


def _index(doc_type: DocType) -> str:
    return f"cb:type:{doc_type.value}"


def _doc_key(doc_type: DocType, record_id: str) -> str:
    return f"cb:doc:{doc_type.value}:{record_id}"


def _chunks(items: list, size: int) -> Iterable[list]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
