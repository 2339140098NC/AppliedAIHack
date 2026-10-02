"""Environment settings. Secrets stay in .env."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT.parent / "Sapini documents"


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
    clio_redirect_uri: str = "http://127.0.0.1:8765/clio/callback"
    clio_region_host: str = "https://app.clio.com"
    clio_matter_id: str = ""
    corpus_dir: Path = DEFAULT_CORPUS
    db_path: Path = ROOT / "data" / "caseboard.sqlite"

    @field_validator("corpus_dir", mode="before")
    @classmethod
    def blank_corpus_uses_default(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_CORPUS
        return value
    token_path: Path = ROOT / "data" / "clio-token.json"
    compress_dir: Path = ROOT / "data" / "compressed"

    @property
    def gemini_ready(self) -> bool:
        return bool(self.gemini_api_key.strip())

    @property
    def clio_ready(self) -> bool:
        return bool(self.clio_client_id.strip() and self.clio_client_secret.strip())
