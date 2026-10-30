"""Shared activity: event journals of all installations and the per-computer usage table.

Each installation writes its own journal per local day, one JSON object per line:

    events/<writer_id>/<YYYY-MM-DD>.jsonl
    {"time": "2026-10-29T15:42:10+00:00", "computer": "LAPTOP (windows)", "event": "logged_off",
     "person": "sam", "account": "sam.k", "reason": "daily_limit", "used": 92, "limit": 90}

Only its writer changes a journal, so journals never conflict; the combined activity log is all
journals of a day merged by time.
"""

import csv
import datetime
import io
import json

MAX_EVENTS_BYTES = 512 * 1024
MAX_EVENTS_PER_DAY = 2000

EVENT_TEXT = {
    "tracker_started": "tracker started",
    "session_counted": "session counted",
    "screen_locked": "screen locked, not counted",
    "session_background": "user switched away, not counted",
    "session_ended": "session ended",
    "near_limit": "close to the daily limit",
    "logged_off": "logged off",
    "offline": "network store unreachable, offline limits apply",
    "online": "network store reachable again",
}
REASON_TEXT = {
    "daily_limit": "daily limit reached",
    "login_hours": "outside allowed login hours",
}
_FIELDS = ("time", "computer", "os", "writer_id", "event", "person", "account", "reason", "used", "limit", "detail")


def serialize_events(events: list[dict]) -> bytes:
    return "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in events).encode("utf-8")


def parse_events(data: bytes, writer_id: str | None = None) -> list[dict]:
    """Parse a journal. Lines that are not valid events are skipped, never trusted."""
    events = []
    if len(data) > MAX_EVENTS_BYTES:
        data = data[:MAX_EVENTS_BYTES]
    for line in data.decode("utf-8", errors="replace").splitlines():
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict) or not isinstance(raw.get("event"), str):
            continue
        try:
            datetime.datetime.fromisoformat(raw.get("time"))
        except (TypeError, ValueError):
            continue
        event = {k: raw[k] for k in _FIELDS if k in raw and isinstance(raw[k], (str, int, float))
                 and not isinstance(raw[k], bool)}
        for number in ("used", "limit"):  # must be numbers, they are formatted as such
            if number in event and not isinstance(event[number], (int, float)):
                del event[number]
        if writer_id is not None:
            event["writer_id"] = writer_id
        events.append(event)
        if len(events) >= MAX_EVENTS_PER_DAY:
            break
    return events


def merge_events(journals: list[list[dict]]) -> list[dict]:
    """All journals of a day as one timeline, oldest first."""
    merged = [e for journal in journals for e in journal]
    return sorted(merged, key=lambda e: datetime.datetime.fromisoformat(e["time"]))


def describe(event: dict) -> str:
    """Human readable text of one event, without time and computer."""
    text = EVENT_TEXT.get(event["event"], event["event"].replace("_", " "))
    if event.get("reason"):
        text += ": " + REASON_TEXT.get(event["reason"], str(event["reason"]).replace("_", " "))
    if event.get("used") is not None and event.get("limit") is not None:
        text += f" ({event['used']:.0f} of {event['limit']} min used)"
    elif event.get("used") is not None:
        text += f" ({event['used']:.0f} min used)"
    if event.get("detail"):
        text += f" [{event['detail']}]"
    who = event.get("person")
    if who and event.get("account") and event["account"] != who:
        who = f"{who} ({event['account']})"
    return f"{who}: {text}" if who else text


def local_time(event: dict, tz=None) -> datetime.datetime:
    return datetime.datetime.fromisoformat(event["time"]).astimezone(tz)


def usage_table(records, labels: dict[str, str], account_index: dict[str, str]):
    """Minutes per person per computer.

    records: DailyRecord objects of one day (any number of writers).
    labels: writer_id -> computer label.
    Returns (computers, rows); rows are (person, {computer: minutes}, total). Accounts that belong
    to nobody are listed by account name, marked "(not managed)".
    """
    per_person: dict[str, dict[str, float]] = {}
    computers: list[str] = []
    for record in records:
        computer = labels.get(record.writer_id) or record.writer_id[:8]
        if computer not in computers:
            computers.append(computer)
        for account, usage in record.accounts.items():
            person = account_index.get(account) or f"{account} (not managed)"
            cells = per_person.setdefault(person, {})
            cells[computer] = cells.get(computer, 0.0) + usage.minutes
    computers.sort()
    rows = [(person, cells, sum(cells.values())) for person, cells in sorted(per_person.items())]
    return computers, rows


def events_csv(events: list[dict], tz=None) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["local_time", "utc_time", "computer", "person", "account", "event", "reason", "used_min",
                     "limit_min", "description"])
    for e in events:
        writer.writerow([local_time(e, tz).strftime("%Y-%m-%d %H:%M:%S"), e["time"], e.get("computer", ""),
                         e.get("person", ""), e.get("account", ""), e["event"], e.get("reason", ""),
                         e.get("used", ""), e.get("limit", ""), describe(e)])
    return out.getvalue()


def usage_csv(date: str, computers: list[str], rows) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "person", *computers, "total_min"])
    for person, cells, total in rows:
        writer.writerow([date, person, *[round(cells.get(c, 0.0), 1) for c in computers], round(total, 1)])
    return out.getvalue()
