"""Read phone logs, emails, notes, messages, and documents from Clio Manage."""

import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from caseboard.clio.session import check_state, issue_state
from caseboard.clio.tokens import TokenStore
from caseboard.config import Settings
from caseboard.errors import CaseboardError

FIELDS_COMM = "id,subject,body,type,date,received_at,created_at,user{id,name},senders{id,name,type},receivers{id,name,type}"
FIELDS_NOTE = "id,subject,detail,date,created_at,type,author{id,name},contact{id,name}"
FIELDS_CONVO = "id,subject"
FIELDS_MESSAGE = "id,body,created_at,sender{id,name}"
FIELDS_DOCUMENT = "id,name,latest_document_version{id,filename,content_type,fully_uploaded}"


class ClioClient:
    """Authorization-code OAuth for one firm, then a matter-scoped read."""

    def __init__(self, settings: Settings, tokens: TokenStore) -> None:
        self._settings = settings
        self._tokens = tokens
        host = settings.clio_region_host.rstrip("/")
        self._host = host
        self._http = httpx.Client(base_url=host, timeout=60, trust_env=False)

    @property
    def tokens(self) -> TokenStore:
        return self._tokens

    def authorize_url(self) -> str:
        self._require_app()
        state = issue_state(self._settings.clio_client_secret)
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._settings.clio_client_id,
                "redirect_uri": self._settings.clio_redirect_uri,
                "state": state,
            }
        )
        return f"{self._host}/oauth/authorize?{query}"

    def exchange(self, code: str, state: str) -> None:
        check_state(self._settings.clio_client_secret, state)
        response = self._http.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self._settings.clio_client_id,
                "client_secret": self._settings.clio_client_secret,
                "redirect_uri": self._settings.clio_redirect_uri,
            },
        )
        self._save_token_response(response)

    def connected(self) -> bool:
        return self._tokens.connected()

    def sync_matter(self) -> tuple[str, list[dict], list[dict], list[dict]]:
        matter_id = self._matter_id()
        communications = self._pages(
            "/api/v4/communications.json",
            {"matter_id": matter_id, "fields": FIELDS_COMM, "order": "date(desc)", "limit": 200},
        )
        notes = self._pages(
            "/api/v4/notes.json",
            {
                "matter_id": matter_id,
                "type": "Matter",
                "fields": FIELDS_NOTE,
                "order": "date(desc)",
                "limit": 200,
            },
        )
        conversations = self._pages(
            "/api/v4/conversations.json",
            {"matter_id": matter_id, "fields": FIELDS_CONVO, "limit": 200},
        )
        messages: list[dict] = []
        for conversation in conversations:
            messages.extend(
                self._pages(
                    "/api/v4/conversation_messages.json",
                    {
                        "conversation_id": conversation["id"],
                        "fields": FIELDS_MESSAGE,
                        "limit": 200,
                    },
                )
            )
        return matter_id, communications, notes, messages

    def list_documents(self, matter_id: str) -> list[dict]:
        return self._pages(
            "/api/v4/documents.json",
            {"matter_id": matter_id, "fields": FIELDS_DOCUMENT, "limit": 200},
        )

    def file_url(self, document_id: str) -> str:
        """Return Clio's short-lived file URL. Gemini can read it without a local copy."""
        response = self._request("GET", f"/api/v4/documents/{document_id}/download.json")
        location = response.headers.get("location")
        if response.status_code not in {301, 302, 303, 307, 308} or not location:
            raise CaseboardError(f"Clio did not return a file for document {document_id}")
        return location

    def pdf_bytes(self, document_id: str) -> bytes:
        """Read one PDF into memory for the page viewer."""
        with httpx.Client(timeout=120, trust_env=False, follow_redirects=True) as http:
            fetched = http.get(self.file_url(document_id))
        if fetched.status_code >= 400 or not fetched.content.startswith(b"%PDF-"):
            raise CaseboardError(f"Document {document_id} is not a PDF")
        return fetched.content

    def download_pdf(self, document_id: str, dest: Path) -> None:
        """Write one PDF to disk. Extraction does not use this."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.pdf_bytes(document_id))

    def _matter_id(self) -> str:
        if self._settings.clio_matter_id.strip():
            return self._settings.clio_matter_id.strip()
        matters = self._pages(
            "/api/v4/matters.json",
            {
                "query": "Sapini",
                "fields": "id,display_number,client{name}",
                "limit": 50,
            },
        )
        matches = [
            item
            for item in matters
            if "justin" in ((item.get("client") or {}).get("name") or "").lower()
            and "sapini" in ((item.get("client") or {}).get("name") or "").lower()
        ]
        if len(matches) != 1:
            labels = [
                f"{item.get('id')} {item.get('display_number')} {(item.get('client') or {}).get('name')}"
                for item in matters
            ]
            raise CaseboardError(
                "Expected one Clio matter for Justin Sapini. "
                + ("; ".join(labels) if labels else "No matters matched.")
            )
        return str(matches[0]["id"])

    def matter_id(self) -> str:
        return self._matter_id()

    def _pages(self, path: str, params: dict) -> list[dict]:
        items: list[dict] = []
        url: str | None = path
        first = True
        while url:
            response = self._request("GET", url, params=params if first else None)
            first = False
            body = response.json()
            items.extend(body.get("data") or [])
            url = ((body.get("meta") or {}).get("paging") or {}).get("next")
        return items

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        response = self._http.request(method, url, headers=self._auth_headers(), **kwargs)
        if response.status_code == 401:
            self._refresh()
            response = self._http.request(method, url, headers=self._auth_headers(), **kwargs)
        if response.status_code == 403:
            raise CaseboardError(
                "Clio accepted the login but this token cannot read data. "
                "In the Clio developer app, turn on read access for Matters, "
                "Communications, Notes, and Documents, then connect again."
            )
        if response.status_code >= 400:
            raise CaseboardError(f"Clio {response.status_code}: {response.text[:300]}")
        return response

    def _auth_headers(self) -> dict[str, str]:
        token = self._access_token()
        return {"Authorization": f"Bearer {token}"}

    def _access_token(self) -> str:
        data = self._tokens.load()
        if not data or not data.get("access_token"):
            raise CaseboardError("Connect Clio before syncing")
        expires_in = float(data.get("expires_in") or 0)
        obtained = float(data.get("obtained_at") or 0)
        if expires_in and time.time() > obtained + expires_in - 60:
            self._refresh()
            data = self._tokens.load() or {}
        token = data.get("access_token")
        if not token:
            raise CaseboardError("Clio token is missing")
        return str(token)

    def _refresh(self) -> None:
        data = self._tokens.load() or {}
        refresh = data.get("refresh_token")
        if not refresh:
            raise CaseboardError("Clio session expired. Connect again.")
        response = self._http.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": self._settings.clio_client_id,
                "client_secret": self._settings.clio_client_secret,
            },
        )
        self._save_token_response(response)

    def _save_token_response(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise CaseboardError(f"Clio token error {response.status_code}: {response.text[:300]}")
        self._tokens.save(response.json())

    def _require_app(self) -> None:
        if not self._settings.clio_ready:
            raise CaseboardError("CLIO_CLIENT_ID and CLIO_CLIENT_SECRET are not set")
