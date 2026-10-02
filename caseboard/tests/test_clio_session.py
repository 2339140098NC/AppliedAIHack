"""OAuth state and the cookie token survive a new server instance."""

import json
from pathlib import Path

import pytest

from caseboard.clio.client import ClioClient
from caseboard.clio.session import check_state, issue_state
from caseboard.clio.tokens import TokenStore
from caseboard.config import Settings
from caseboard.errors import CaseboardError
from tests.test_upstash_store import MemoryRedis


def test_signed_state_round_trips() -> None:
    state = issue_state("secret")
    check_state("secret", state)


def test_forged_state_is_rejected() -> None:
    state = issue_state("secret")
    with pytest.raises(CaseboardError):
        check_state("other", state)


def test_client_exposes_the_token_store(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "clio-token.json")
    client = ClioClient(Settings(), store)
    assert client.tokens is store


def test_cookie_adopts_only_when_the_file_is_missing(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "clio-token.json")
    store.adopt(json.dumps({"refresh_token": "refresh", "access_token": "access"}))
    assert store.connected()
    store.adopt(json.dumps({"refresh_token": "newer"}))
    assert store.load()["refresh_token"] == "refresh"


def test_upstash_keeps_the_token_for_the_next_instance(tmp_path: Path) -> None:
    cache = MemoryRedis()
    first = TokenStore(tmp_path / "one.json", cache)
    first.save({"refresh_token": "refresh", "access_token": "access", "expires_in": 3600})
    second = TokenStore(tmp_path / "two.json", cache)
    assert second.connected()
    assert second.load()["refresh_token"] == "refresh"
    second.adopt(json.dumps({"refresh_token": "newer", "access_token": "other"}))
    assert second.load()["refresh_token"] == "refresh"
