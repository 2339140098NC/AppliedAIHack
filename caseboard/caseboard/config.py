"""Environment settings. Secrets stay in .env."""

import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT.parent / "Sapini documents"
DATA = Path("/tmp/caseboard") if os.environ.get("VERCEL") else ROOT / "data"


class Settings(BaseSettings):
    """Runtime configuration for extraction, Clio, and the local store."""

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    clio_client_id: str = ""
    clio_client_secret: str = ""
    clio_redirect_uri: str = ""
    clio_region_host: str = "https://app.clio.com"
    clio_matter_id: str = ""
    corpus_dir: Path = DEFAULT_CORPUS
    db_path: Path = DATA / "caseboard.sqlite"
    token_path: Path = DATA / "clio-token.json"
    docs_dir: Path = DATA / "clio-pdfs"
    compress_dir: Path = DATA / "compressed"
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    @field_validator("corpus_dir", mode="before")
    @classmethod
    def blank_corpus_uses_default(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_CORPUS
        return value

    @field_validator("clio_redirect_uri", mode="before")
    @classmethod
    def production_redirect(cls, value: object) -> object:
        if isinstance(value, str) and value.strip():
            return value
        host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or ""
        if host:
            return f"https://{host}/callback"
        return "http://127.0.0.1:8765/clio/callback"

    @property
    def gemini_ready(self) -> bool:
        return bool(self.gemini_api_key.strip())

    @property
    def clio_ready(self) -> bool:
        return bool(self.clio_client_id.strip() and self.clio_client_secret.strip())

    @property
    def upstash_ready(self) -> bool:
        return bool(self.upstash_redis_rest_url.strip() and self.upstash_redis_rest_token.strip())
