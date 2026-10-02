"""Upstash document store against an in-memory Redis stand-in."""

from caseboard.domain.enums import DocType, EventKind, Sensitivity
from caseboard.domain.models import SourceFile, TimelineEvent
from caseboard.store.upstash import UpstashDocumentStore


class _Pipe:
    def __init__(self, redis: "MemoryRedis") -> None:
        self._redis = redis
        self._ops: list[tuple] = []

    def set(self, key: str, value: str) -> "_Pipe":
        self._ops.append(("set", (key, value)))
        return self

    def sadd(self, key: str, *members: str) -> "_Pipe":
        self._ops.append(("sadd", (key, *members)))
        return self

    def delete(self, *keys: str) -> "_Pipe":
        self._ops.append(("delete", keys))
        return self

    def srem(self, key: str, *members: str) -> "_Pipe":
        self._ops.append(("srem", (key, *members)))
        return self

    def scard(self, key: str) -> "_Pipe":
        self._ops.append(("scard", (key,)))
        return self

    def smembers(self, key: str) -> "_Pipe":
        self._ops.append(("smembers", (key,)))
        return self

    def mget(self, *keys: str) -> "_Pipe":
        self._ops.append(("mget", keys))
        return self

    def get(self, key: str) -> "_Pipe":
        self._ops.append(("get", (key,)))
        return self

    def exec(self) -> list:
        return [getattr(self._redis, name)(*args) for name, args in self._ops]


class MemoryRedis:
    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}

    def pipeline(self) -> _Pipe:
        return _Pipe(self)

    def set(self, key: str, value: str) -> str:
        self.strings[key] = value
        return "OK"

    def get(self, key: str) -> str | None:
        return self.strings.get(key)

    def sadd(self, key: str, *members: str) -> int:
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        bucket.update(str(member) for member in members)
        return len(bucket) - before

    def smembers(self, key: str) -> list[str]:
        return sorted(self.sets.get(key, set()))

    def mget(self, *keys: str) -> list[str | None]:
        return [self.strings.get(key) for key in keys]

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += int(self.strings.pop(key, None) is not None)
            removed += int(self.sets.pop(key, None) is not None)
        return removed

    def srem(self, key: str, *members: str) -> int:
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        bucket.difference_update(str(member) for member in members)
        return before - len(bucket)

    def scard(self, key: str) -> int:
        return len(self.sets.get(key, set()))


def test_upstash_store_round_trip() -> None:
    store = UpstashDocumentStore(MemoryRedis())  # type: ignore[arg-type]
    store.put(DocType.source, "letter.pdf", SourceFile(filename="letter.pdf", clio_document_id="9"))
    store.put(
        DocType.timeline_event,
        "call-1",
        TimelineEvent(
            id="call-1",
            label="Called the client",
            kind=EventKind.call,
            sensitivity=Sensitivity.firm_only,
            sensitivity_reason="Clio communication",
            origin="clio",
        ),
    )
    store.put(
        DocType.timeline_event,
        "pdf-1",
        TimelineEvent(
            id="pdf-1",
            label="Office visit",
            kind=EventKind.treatment,
            sensitivity=Sensitivity.provider_visible,
            sensitivity_reason="clinical",
            origin="pdf",
        ),
    )
    names = [row["filename"] for row in store.list_type(DocType.source)]
    assert names == ["letter.pdf"]
    loaded = store.list_types([DocType.source, DocType.timeline_event, DocType.portrait])
    assert [row["id"] for row in loaded[DocType.source]] == ["letter.pdf"]
    assert {row["id"] for row in loaded[DocType.timeline_event]} == {"call-1", "pdf-1"}
    assert loaded[DocType.portrait] == []
    assert store.get(DocType.source, "letter.pdf")["filename"] == "letter.pdf"
    assert store.list_type(DocType.source)[0]["id"] == "letter.pdf"
    visible = store.list_type(DocType.timeline_event, sensitivity="provider_visible")
    assert [row["id"] for row in visible] == ["pdf-1"]
    store.delete_type(DocType.timeline_event, origin="clio")
    remaining = [row["id"] for row in store.list_type(DocType.timeline_event)]
    assert remaining == ["pdf-1"]
    store.delete_ids(DocType.source, ["letter.pdf"])
    assert store.list_type(DocType.source) == []
    assert store.counts() == {"timeline_event": 1}
