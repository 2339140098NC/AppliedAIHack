"""Names and clock times from a Clio communication payload."""


def party_name(value: object) -> str:
    """A person's name from a Clio user, contact, or participant. Ids are ignored."""
    if not isinstance(value, dict):
        return ""
    name = str(value.get("name") or "").strip()
    if name:
        return name
    for key in ("user", "contact"):
        nested = value.get(key)
        if isinstance(nested, dict):
            nested_name = str(nested.get("name") or "").strip()
            if nested_name:
                return nested_name
    return ""


def party_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        name = party_name(item)
        if name and name not in names:
            names.append(name)
    return names


def event_when(date: str | None, received_at: str | None = None) -> tuple[str | None, str]:
    """The day the communication happened. A later save time is not that day."""
    day, _ignored = split_stamp(date)
    received_day, clock = split_stamp(received_at)
    return day or received_day, clock


def split_stamp(value: str | None) -> tuple[str | None, str]:
    """Calendar day and a 12-hour clock. A date with no time has an empty clock."""
    if not value:
        return None, ""
    text = str(value).strip()
    day = text[:10] if len(text) >= 10 and text[4] == "-" else None
    rest = text[10:].strip(" T")
    if len(rest) < 5 or rest[2] != ":" or not rest[:2].isdigit():
        return day, ""
    hour = int(rest[:2])
    minute = rest[3:5]
    if not minute.isdigit():
        return day, ""
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return day, f"{hour12}:{minute} {suffix}"


def other_party(author: str, *groups: object) -> str:
    """The first named person who is not the one who logged the record."""
    for group in groups:
        for name in party_names(group) if isinstance(group, list) else [party_name(group)]:
            if name and name != author:
                return name
    return ""
