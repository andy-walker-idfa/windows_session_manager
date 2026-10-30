"""One tracker cycle: read sessions, credit usage, enforce, record events, sync.

Between cycles, quick_check() runs every few seconds to log off a managed user who logs in while
already over the limit or outside the allowed hours, without waiting for the next full cycle.
"""

import datetime
import logging
import time
from dataclasses import dataclass, field

from core.activity import MAX_EVENTS_PER_DAY
from core.config import build_account_index, get_settings, normalize_account
from core.enforcement import limit_reached, outside_login_window
from core.limits import resolve_limits, resolve_offline_limits
from core.usage import elapsed_credit, usage_by_person
from shared import defaults
from shared.instance import WriterIdentity, writer_info
from shared.logging_setup import set_level
from tracker.sync import Repository

WRITER_INFO_EVERY = datetime.timedelta(hours=1)


@dataclass
class CycleResult:
    online: bool
    credited: dict[str, float] = field(default_factory=dict)        # account -> minutes added
    usage: dict[str, float] = field(default_factory=dict)           # person -> minutes today
    logged_off: list[tuple[str, str]] = field(default_factory=list)  # (account, reason)
    interval_minutes: int = 5


class EventJournal:
    """This installation's shared activity log for the current day (events/<writer>/<date>.jsonl)."""

    def __init__(self, repo: Repository, identity: WriterIdentity, os_name: str):
        self.repo = repo
        self.identity = identity
        self.os_name = os_name
        self._date: str | None = None
        self._events: list[dict] = []

    def add(self, now_local: datetime.datetime, event: str, **fields) -> None:
        date = now_local.date().isoformat()
        try:
            if date != self._date:
                self._events = self.repo.load_own_events(date)
                self._date = date
            if len(self._events) >= MAX_EVENTS_PER_DAY:
                return
            entry = {"time": now_local.astimezone(datetime.timezone.utc).isoformat(timespec="seconds"),
                     "computer": self.identity.label, "os": self.os_name, "event": event}
            entry.update({k: (round(v, 1) if isinstance(v, float) else v) for k, v in fields.items() if v is not None})
            self._events.append(entry)
            self.repo.save_own_events(date, self._events)
        except Exception as e:  # the activity log must never stop enforcement
            logging.warning(f"Could not record event '{event}': {e}")


class Tracker:
    def __init__(self, platform, repo: Repository, identity: WriterIdentity, os_name: str,
                 dry_run: bool = False, clock=None, monotonic=None):
        self.platform = platform
        self.repo = repo
        self.identity = identity
        self.os_name = os_name
        self.dry_run = dry_run
        self.clock = clock or (lambda: datetime.datetime.now().astimezone())
        self.monotonic = monotonic or time.monotonic
        self.journal = EventJournal(repo, identity, os_name)
        self._previous_monotonic: float | None = None
        self._recovered = False
        self._started = False
        self._writer_published: datetime.datetime | None = None
        self._pruned_on: datetime.date | None = None
        self._log_level: str | None = None
        # What each managed account was doing last cycle, and who was warned near the limit.
        self._states: dict[str, tuple[str, str]] = {}      # account -> (person, state)
        self._near_limit: set[tuple[str, datetime.date]] = set()
        self._was_online: bool | None = None
        # Kept from the last full cycle for quick_check().
        self._last_config: dict | None = None
        self._last_usage: dict[str, float] = {}
        self._last_date: datetime.date | None = None

    # ----- helpers -------------------------------------------------------------------------
    def _limits(self, config, person, day, online) -> dict:
        return (resolve_limits if online else resolve_offline_limits)(config, person, day)

    def _log_off(self, session, person, reason_code: str, reason: str, result: CycleResult,
                 now_local, used=None, limit=None, detail=None) -> bool:
        if self.dry_run:
            logging.info(f"[dry run] Would log off {session.account}: {reason}.")
        else:
            try:
                self.platform.log_off(session)
                logging.info(f"Logged off {session.account}: {reason}.")
            except Exception as e:
                logging.error(f"Logging off {session.account} failed, will retry: {e}")
                return False
        result.logged_off.append((session.account, reason))
        self.journal.add(now_local, "logged_off", person=person, account=normalize_account(session.account),
                         reason=reason_code, used=used, limit=limit,
                         detail=("dry run" if self.dry_run else None) or detail)
        return True

    # ----- INFO log and shared activity log ------------------------------------------------
    def _report_changes(self, sessions, index, config, today, online, result, now_local) -> None:
        """When something changes for a managed person, write an INFO line and a shared event, so
        the logs tell each child's day without DEBUG: counting starts, screen locked, session ends,
        near the limit."""
        if self._was_online is not None and online != self._was_online:
            if online:
                logging.info("Network store reachable again; normal limits apply.")
            self.journal.add(now_local, "online" if online else "offline")
        elif self._was_online is None and not online:
            self.journal.add(now_local, "offline")
        self._was_online = online

        def numbers(person: str):
            try:
                return result.usage.get(person, 0.0), self._limits(config, person, today, online)["limit_minutes"]
            except Exception:
                return result.usage.get(person, 0.0), None

        def summary(person: str) -> str:
            used, limit = numbers(person)
            return f"{used:.0f} of {limit} min used today" if limit is not None else f"{used:.0f} min used today"

        logged_off = {normalize_account(account) for account, _ in result.logged_off}
        states: dict[str, tuple[str, str]] = {}
        for session in sessions:
            account = normalize_account(session.account)
            person = index.get(account)
            if person is None:
                continue
            state = "locked" if session.locked else ("counted" if session.active else "background")
            if account in logged_off:
                state = "logged off"
            if states.get(account, (None, None))[1] not in ("counted", "logged off"):
                states[account] = (person, state)

        for account in sorted(set(states) | set(self._states)):
            person, state = states.get(account) or (self._states[account][0], "ended")
            previous = self._states.get(account, (None, None))[1]
            if state == previous or state == "logged off":
                continue  # unchanged, or the logoff line already says what happened
            used, limit = numbers(person)
            if state == "ended":
                if previous != "logged off":
                    logging.info(f"{person} ({account}): session ended on this computer, {summary(person)}.")
                    self.journal.add(now_local, "session_ended", person=person, account=account, used=used, limit=limit)
            elif state == "counted":
                logging.info(f"{person} ({account}): session counted on this computer, {summary(person)}.")
                self.journal.add(now_local, "session_counted", person=person, account=account, used=used, limit=limit)
            elif state == "locked":
                logging.info(f"{person} ({account}): screen locked, not counted ({summary(person)}).")
                self.journal.add(now_local, "screen_locked", person=person, account=account, used=used, limit=limit)
            else:
                logging.info(f"{person} ({account}): session in the background (user switched), not counted.")
                self.journal.add(now_local, "session_background", person=person, account=account)
        self._states = dict(states)

        for account, (person, state) in states.items():
            if state != "counted" or (person, today) in self._near_limit:
                continue
            used, limit = numbers(person)
            if limit and 0.8 * limit <= used < limit:
                self._near_limit.add((person, today))
                logging.info(f"{person}: {used:.0f} of {limit} min used, {limit - used:.0f} min left today.")
                self.journal.add(now_local, "near_limit", person=person, account=account, used=used, limit=limit)

    # ----- full cycle ----------------------------------------------------------------------
    def run_cycle(self) -> CycleResult:
        now_local = self.clock()
        now_utc = now_local.astimezone(datetime.timezone.utc)
        today = now_local.date()
        mono = self.monotonic()

        config = self.repo.refresh_config()
        settings = get_settings(config)
        if settings["log_level"] != self._log_level:
            set_level(settings["log_level"])
            self._log_level = settings["log_level"]
        interval = settings["check_interval_minutes"]
        credit = elapsed_credit(mono, self._previous_monotonic, interval)
        self._previous_monotonic = mono
        if not self._started:
            self._started = True
            self.journal.add(now_local, "tracker_started", detail=f"version {defaults.__version__}")

        own = self.repo.load_own(today.isoformat())
        if not self._recovered and self.repo.remote is not None:
            self._recovered = self.repo.recover(own)

        others = self.repo.fetch_others(today.isoformat())
        has_remote = self.repo.remote is not None
        online = (not has_remote) or others is not None
        if others is None:
            others = self.repo.cached_others(today.isoformat())
        result = CycleResult(online=online, interval_minutes=interval)

        index = build_account_index(config)
        if not index:
            logging.debug("No managed users in the configuration.")
        all_sessions = self.platform.get_sessions()
        sessions = [s for s in all_sessions if s.active and not s.locked]
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            def describe(s):
                state = "locked" if s.locked else ("active" if s.active else "inactive")
                person = index.get(normalize_account(s.account))
                return f"{s.account} ({state}, {'person ' + person if person else 'not managed'})"
            logging.debug(f"Cycle: {'online' if online else 'OFFLINE'}, {credit:.2f} min to credit; sessions: "
                          f"{', '.join(describe(s) for s in all_sessions) or 'none'}")

        usage_before = usage_by_person([own, *others], index)
        managed = []
        for session in sessions:
            account = normalize_account(session.account)
            person = index.get(account)
            if person is None:
                continue  # not managed, not recorded
            limits = self._limits(config, person, today, online)
            if outside_login_window(limits, now_local):
                self._log_off(session, person, "login_hours", f"outside allowed login hours "
                              f"{limits['earliest_login']}-{limits['latest_login']}", result, now_local,
                              used=usage_before.get(person, 0.0), limit=limits["limit_minutes"],
                              detail=f"allowed {limits['earliest_login']}-{limits['latest_login']}")
                continue
            if account not in result.credited:
                own.credit(account, credit, now_utc)
                result.credited[account] = credit
            managed.append((session, person, limits))

        if result.credited:
            self.repo.save_own(own)

        result.usage = usage_by_person([own, *others], index)
        for session, person, limits in managed:
            used = result.usage.get(person, 0.0)
            logging.debug(f"{person} ({session.account}): {used:.1f} of {limits['limit_minutes']} min used")
            if limit_reached(limits, used):
                self._log_off(session, person, "daily_limit", f"daily limit of {limits['limit_minutes']} min "
                              f"reached ({used:.0f} min used today)", result, now_local,
                              used=used, limit=limits["limit_minutes"])

        self._report_changes(all_sessions, index, config, today, online, result, now_local)
        # Upload last, so this cycle's usage and events reach the network store in this cycle.
        self.repo.push_dirty()

        self._last_config, self._last_usage, self._last_date = config, dict(result.usage), today
        if online and has_remote and (self._writer_published is None
                                      or now_utc - self._writer_published >= WRITER_INFO_EVERY):
            self.repo.publish_writer(writer_info(self.identity, self.os_name, now_utc.isoformat(timespec="seconds")))
            self._writer_published = now_utc
        if self._pruned_on != today:
            self.repo.prune(today, settings["retention_days"], online)
            self._pruned_on = today
        return result

    # ----- quick check between cycles ------------------------------------------------------
    def quick_check(self) -> CycleResult:
        """Log off a managed user who just logged in while over the limit or outside the allowed
        hours. Uses the limits and usage of the last full cycle; no network access. Sessions that
        were already being counted are left to the full cycle."""
        now_local = self.clock()
        result = CycleResult(online=self._was_online is not False)
        if self._last_config is None:
            return result
        today = now_local.date()
        usage = self._last_usage if self._last_date == today else {}  # a new day starts at 0
        index = build_account_index(self._last_config)
        for session in self.platform.get_sessions():
            if not session.active or session.locked:
                continue
            account = normalize_account(session.account)
            person = index.get(account)
            if person is None or self._states.get(account, (None, None))[1] == "counted":
                continue
            limits = self._limits(self._last_config, person, today, result.online)
            used = usage.get(person, 0.0)
            if outside_login_window(limits, now_local):
                code, reason = "login_hours", (f"outside allowed login hours {limits['earliest_login']}-"
                                               f"{limits['latest_login']} (checked at login)")
            elif limit_reached(limits, used):
                code, reason = "daily_limit", (f"daily limit of {limits['limit_minutes']} min reached "
                                               f"({used:.0f} min used today, checked at login)")
            else:
                continue
            if self._log_off(session, person, code, reason, result, now_local, used=used,
                             limit=limits["limit_minutes"], detail="checked at login"):
                self._states[account] = (person, "logged off")
        if result.logged_off:
            self.repo.push_dirty()
        return result
