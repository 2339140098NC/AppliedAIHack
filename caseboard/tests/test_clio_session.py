"""OAuth state and the cookie token survive a new server instance."""

import json
from pathlib import Path

import pytest

from caseboard.clio.session import check_state, issue_state
from caseboard.clio.tokens import TokenStore
from caseboard.errors import CaseboardError


def test_signed_state_round_trips() -> None:
    state = issue_state("secret")
    check_state("secret", state)


def test_forged_state_is_rejected() -> None:
    state = issue_state("secret")
    with pytest.raises(CaseboardError):
        check_state("other", state)


def test_cookie_adopts_only_when_the_file_is_missing(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "clio-token.json")
    store.adopt(json.dumps({"refresh_token": "refresh", "access_token": "access"}))
    assert store.connected()
    store.adopt(json.dumps({"refresh_token": "newer"}))
    assert store.load()["refresh_token"] == "refresh"
