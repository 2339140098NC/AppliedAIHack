"""Pick Upstash when it is configured, otherwise the local SQLite file."""

from upstash_redis import Redis

from caseboard.clio.tokens import TokenStore
from caseboard.config import Settings
from caseboard.store.documents import DocumentStore
from caseboard.store.upstash import UpstashDocumentStore


def open_store(settings: Settings) -> DocumentStore | UpstashDocumentStore:
    """Return the document store for this process."""
    client = _redis(settings)
    if client is None:
        return DocumentStore(settings.db_path)
    return UpstashDocumentStore(client)


def open_tokens(settings: Settings) -> TokenStore:
    """Return the Clio token store. Upstash keeps it across instances."""
    return TokenStore(settings.token_path, _redis(settings))


def _redis(settings: Settings) -> Redis | None:
    if not settings.upstash_ready:
        return None
    return Redis(url=settings.upstash_redis_rest_url, token=settings.upstash_redis_rest_token)
