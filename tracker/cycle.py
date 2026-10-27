"""One tracker cycle: read sessions, credit usage, sync, enforce."""

import datetime
import logging
import time
from dataclasses import dataclass, field

from core.config import build_account_index, get_settings, normalize_account
from core.enforcement import limit_reached, outside_login_window
from core.limits import resolve_limits, resolve_offline_limits
from core.usage import elapsed_credit, usage_by_person
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
        self._previous_monotonic: float | None = None
        self._recovered = False
        self._writer_published: datetime.datetime | None = None
        self._pruned_on: datetime.date | None = None
        self._log_level: str | None = None
        # For the INFO log: what each managed account was doing last cycle, and who was warned.
        self._states: dict[str, tuple[str, str]] = {}      # account -> (person, state)
        self._near_limit: set[tuple[str, datetime.date]] = set()
        self._was_online: bool | None = None

    def _report_changes(self, sessions, index, config, today, online, result) -> None:
        """Write INFO lines when something changes for a managed person, so the normal log tells
        each child's day without DEBUG: counting starts, screen locked, session ends, near the limit."""
        if self._was_online is False and online:
            logging.info("Network store reachable again; normal limits apply.")
        self._was_online = online

        def summary(person: str) -> str:
            try:
                limits = (resolve_limits if online else resolve_offline_limits)(config, person, today)
                return f"{result.usage.get(person, 0.0):.0f} of {limits['limit_minutes']} min used today"
            except Exception:
                return f"{result.usage.get(person, 0.0):.0f} min used today"

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
            if state == "ended":
                if previous != "logged off":
                    logging.info(f"{person} ({account}): session ended on this computer, {summary(person)}.")
            elif state == "counted":
                logging.info(f"{person} ({account}): session counted on this computer, {summary(person)}.")
            elif state == "locked":
                logging.info(f"{person} ({account}): screen locked, not counted ({summary(person)}).")
            else:
                logging.info(f"{person} ({account}): session in the background (user switched), not counted.")
        self._states = {a: s for a, s in states.items()}

        for account, (person, state) in states.items():
            if state != "counted" or (person, today) in self._near_limit:
                continue
            try:
                limit = (resolve_limits if online else resolve_offline_limits)(config, person, today)["limit_minutes"]
            except Exception:
                continue
            used = result.usage.get(person, 0.0)
            if limit > 0 and 0.8 * limit <= used < limit:
                self._near_limit.add((person, today))
                logging.info(f"{person}: {used:.0f} of {limit} min used, {limit - used:.0f} min left today.")

    def _log_off(self, session, reason: str, result: CycleResult) -> None:
        if self.dry_run:
            logging.info(f"[dry run] Would log off {session.account}: {reason}.")
        else:
            try:
                self.platform.log_off(session)
                logging.info(f"Logged off {session.account}: {reason}.")
            except Exception as e:
                logging.error(f"Logging off {session.account} failed, will retry next cycle: {e}")
                return
        result.logged_off.append((session.account, reason))

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

        managed = []
        for session in sessions:
            account = normalize_account(session.account)
            person = index.get(account)
            if person is None:
                continue  # not managed, not recorded
            if online:
                limits = resolve_limits(config, person, today)
            else:
                limits = resolve_offline_limits(config, person, today)
            if outside_login_window(limits, now_local):
                self._log_off(session, f"outside allowed login hours {limits['earliest_login']}-"
                                       f"{limits['latest_login']}", result)
                continue
            if account not in result.credited:
                own.credit(account, credit, now_utc)
                result.credited[account] = credit
            managed.append((session, person, limits))

        if result.credited:
            self.repo.save_own(own)
        self.repo.push_dirty()

        result.usage = usage_by_person([own, *others], index)
        for session, person, limits in managed:
            used = result.usage.get(person, 0.0)
            logging.debug(f"{person} ({session.account}): {used:.1f} of {limits['limit_minutes']} min used")
            if limit_reached(limits, used):
                self._log_off(session, f"daily limit of {limits['limit_minutes']} min reached "
                                       f"({used:.0f} min used today)", result)

        self._report_changes(all_sessions, index, config, today, online, result)

        if online and has_remote and (self._writer_published is None
                                      or now_utc - self._writer_published >= WRITER_INFO_EVERY):
            self.repo.publish_writer(writer_info(self.identity, self.os_name, now_utc.isoformat(timespec="seconds")))
            self._writer_published = now_utc
        if self._pruned_on != today:
            self.repo.prune(today, settings["retention_days"], online)
            self._pruned_on = today
        return result
