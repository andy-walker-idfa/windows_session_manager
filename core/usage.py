"""Daily usage records.

Each writer (one installed tracker) owns one file per local day:

    {"schema": 1, "writer_id": "...", "date": "2026-10-26",
     "accounts": {"sam": {"minutes": 42.5, "last_seen": "2026-10-26T14:30:00+00:00"}}}

Only its writer ever changes it, so files from different writers never conflict; a person's usage
is the sum over all writers.
"""

import datetime
import json
from dataclasses import dataclass, field

RECORD_SCHEMA = 1
MAX_RECORD_BYTES = 64 * 1024


class RecordError(ValueError):
    """Raised when a record file cannot be parsed or fails validation."""


class NewerSchemaError(RecordError):
    """The file was written by a newer version; skip it rather than misread it."""


@dataclass
class AccountUsage:
    minutes: float = 0.0
    last_seen: str | None = None


@dataclass
class DailyRecord:
    writer_id: str
    date: str
    accounts: dict[str, AccountUsage] = field(default_factory=dict)

    def credit(self, account: str, minutes: float, now_utc: datetime.datetime) -> None:
        usage = self.accounts.setdefault(account, AccountUsage())
        usage.minutes = round(usage.minutes + max(0.0, minutes), 2)
        usage.last_seen = now_utc.isoformat(timespec="seconds")

    def merge_max(self, other: "DailyRecord") -> bool:
        """Per account, keep the larger minute count. Returns True if anything changed."""
        changed = False
        for account, theirs in other.accounts.items():
            mine = self.accounts.get(account)
            if mine is None or theirs.minutes > mine.minutes:
                self.accounts[account] = AccountUsage(theirs.minutes, theirs.last_seen)
                changed = True
        return changed


def serialize_record(record: DailyRecord) -> bytes:
    data = {
        "schema": RECORD_SCHEMA,
        "writer_id": record.writer_id,
        "date": record.date,
        "accounts": {a: {"minutes": u.minutes, "last_seen": u.last_seen} for a, u in sorted(record.accounts.items())},
    }
    return json.dumps(data, indent=1).encode("utf-8")


def parse_record(data: bytes, expected_writer: str | None = None, expected_date: str | None = None) -> DailyRecord:
    """Parse and strictly validate a record file. Raises RecordError / NewerSchemaError."""
    if len(data) > MAX_RECORD_BYTES:
        raise RecordError(f"record is larger than {MAX_RECORD_BYTES} bytes")
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise RecordError(f"record is not valid JSON: {e}") from e
    if not isinstance(raw, dict):
        raise RecordError("record must be a JSON object")
    schema = raw.get("schema")
    if not isinstance(schema, int) or isinstance(schema, bool):
        raise RecordError("record has no valid schema number")
    if schema > RECORD_SCHEMA:
        raise NewerSchemaError(f"record schema {schema} is newer than supported {RECORD_SCHEMA}")
    writer_id, date = raw.get("writer_id"), raw.get("date")
    if not isinstance(writer_id, str) or not isinstance(date, str):
        raise RecordError("record needs writer_id and date strings")
    try:
        datetime.date.fromisoformat(date)
    except ValueError as e:
        raise RecordError(f"record date '{date}' is not YYYY-MM-DD") from e
    if expected_writer is not None and writer_id != expected_writer:
        raise RecordError(f"record belongs to writer {writer_id}, expected {expected_writer}")
    if expected_date is not None and date != expected_date:
        raise RecordError(f"record is for {date}, expected {expected_date}")
    accounts_raw = raw.get("accounts")
    if not isinstance(accounts_raw, dict):
        raise RecordError("record accounts must be an object")
    accounts = {}
    for account, usage in accounts_raw.items():
        if not isinstance(usage, dict):
            raise RecordError(f"usage of '{account}' must be an object")
        minutes = usage.get("minutes")
        if not isinstance(minutes, (int, float)) or isinstance(minutes, bool) or not 0 <= minutes <= 1440:
            raise RecordError(f"minutes of '{account}' must be a number 0-1440")
        last_seen = usage.get("last_seen")
        if last_seen is not None and not isinstance(last_seen, str):
            raise RecordError(f"last_seen of '{account}' must be a string")
        accounts[account] = AccountUsage(float(minutes), last_seen)
    return DailyRecord(writer_id, date, accounts)


def usage_by_person(records, account_index: dict[str, str]) -> dict[str, float]:
    """Sum minutes per person over records from all writers. Unmapped accounts are ignored."""
    totals: dict[str, float] = {}
    for record in records:
        for account, usage in record.accounts.items():
            person = account_index.get(account)
            if person is not None:
                totals[person] = totals.get(person, 0.0) + usage.minutes
    return totals


def elapsed_credit(monotonic_now: float, monotonic_previous: float | None, interval_minutes: float) -> float:
    """Minutes to credit for one tracker cycle.

    Measured with the process's monotonic clock so wall clock jumps cannot affect it, capped at the
    check interval so time spent asleep never counts. The first cycle credits one interval.
    """
    if monotonic_previous is None:
        return float(interval_minutes)
    delta = (monotonic_now - monotonic_previous) / 60
    return max(0.0, min(delta, float(interval_minutes)))
