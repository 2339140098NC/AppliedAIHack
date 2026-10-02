"""Query string for the case workspace."""

from urllib.parse import urlencode

from fastapi import Request

PROVIDERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("montefiore", "Montefiore Nyack Hospital", ("montefiore", "nyack")),
    ("haggerty", "Advanced Rockland Chiropractic", ("haggerty", "rockland chiro")),
    ("sportscare", "SportsCare Physical Therapy", ("sportscare", "sports care")),
    ("newhorizon", "New Horizon Surgical Center", ("new horizon", "newhorizon")),
)
PROVIDER_IDS = {item[0] for item in PROVIDERS}


class WorkspaceQuery:
    """Firm or provider view, plus the open page."""

    def __init__(
        self,
        *,
        view: str,
        provider: str,
        tab: str,
        document: str,
        page: int,
        quote: str,
        ev: str,
        selected: str,
        drawer: str,
        panel: str = "",
    ) -> None:
        self.view = "provider" if view == "provider" else "firm"
        self.provider = provider if provider in PROVIDER_IDS else "montefiore"
        self.tab = _tab(self.view, tab)
        self.document = document
        self.page = page if page > 0 else 0
        self.quote = quote
        self.ev = "all" if ev == "all" else "compared"
        self.selected = selected
        self.drawer = "1" if drawer == "1" else ""
        self.panel = "extract" if panel == "extract" and self.view == "firm" else ""

    @property
    def firm(self) -> bool:
        return self.view == "firm"

    def provider_name(self) -> str:
        for key, name, _tokens in PROVIDERS:
            if key == self.provider:
                return name
        return PROVIDERS[0][1]

    def url(self, **changes: object) -> str:
        data = {
            "view": self.view,
            "provider": self.provider,
            "tab": self.tab,
            "document": self.document,
            "page": self.page or "",
            "quote": self.quote,
            "ev": self.ev if self.ev != "compared" else "",
            "sel": self.selected,
            "drawer": self.drawer,
            "panel": changes.get("panel", ""),
        }
        data.update(changes)
        view = str(data["view"])
        data["tab"] = _tab(view, str(data["tab"]))
        kept = {key: value for key, value in data.items() if value not in ("", 0, None)}
        return "/?" + urlencode(kept)


def parse_query(request: Request) -> WorkspaceQuery:
    params = request.query_params
    view = params.get("view") or params.get("audience") or "firm"
    try:
        page = int(params.get("page") or "0")
    except ValueError:
        page = 0
    return WorkspaceQuery(
        view=view,
        provider=params.get("provider") or "montefiore",
        tab=params.get("tab") or "timeline",
        document=params.get("document") or "",
        page=page,
        quote=params.get("quote") or "",
        ev=params.get("ev") or "compared",
        selected=params.get("sel") or "",
        drawer=params.get("drawer") or "",
        panel=params.get("panel") or "",
    )


def _tab(view: str, tab: str) -> str:
    if view == "provider":
        return tab if tab in ("timeline", "records") else "timeline"
    return tab if tab in ("timeline", "evidence", "todo") else "timeline"
