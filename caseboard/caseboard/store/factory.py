"""Pick Upstash when it is configured, otherwise the local SQLite file."""

from upstash_redis import Redis

from caseboard.config import Settings
from caseboard.store.documents import DocumentStore
from caseboard.store.upstash import UpstashDocumentStore


def open_store(settings: Settings) -> DocumentStore | UpstashDocumentStore:
    """Return the document store for this process."""
    if not settings.upstash_ready:
        return DocumentStore(settings.db_path)
    client = Redis(url=settings.upstash_redis_rest_url, token=settings.upstash_redis_rest_token)
    return UpstashDocumentStore(client)
