# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2026-10-29

### Added

- **Shared activity log.** Every installation keeps a journal of what happened to managed people on
  that computer: session counted, screen locked, user switched, close to the limit, logged off and why,
  offline and back online. Journals are stored next to the usage records
  (`events/<installation>/<date>.jsonl`), uploaded in the same cycle, kept locally while offline and
  removed after the retention period. Local log files are unchanged.
- **Activity tab in the configurator.** For any day: minutes per person per computer, with the total
  and the limit, and one combined timeline of all computers. **Export CSV…** saves both.
- **Quick login check.** Between the regular cycles, new logins are checked every 20 seconds. A managed
  person who logs in while over the daily limit, or outside the allowed hours, is logged off at once
  instead of within the next cycle, which makes separate logon scripts unnecessary.

### Fixed

- Names in the configurator's people list were nearly invisible in light mode unless selected.

## [2.0.0] - 2026-10-26

Rewritten for several computers and operating systems sharing one daily total.

### Added

- **Linux and macOS support.** systemd-logind (`loginctl`) and IORegistry/`launchctl` adapters next
  to the Windows one. Only active, unlocked, local desktop sessions count.
- **Shared usage across computers.** Each installation writes its own daily record. Records are
  copied to a WebDAV store over HTTPS, and a person's usage is the sum over all installations.
- **Offline mode.** If the store can't be reached, the tracker uses local and cached data together
  with the stricter of the person's limits and the global defaults, then uploads its records when
  the store is back.
- **Shared configuration** on the store, validated before use, with a local cache, a seed config
  at install time, and a revision check against concurrent edits.
- **People with several account names** (`accounts = [...]`); account names are compared without
  regard to case.
- **Configurator rework.** It runs on any OS, loads and shows the current settings, edits people,
  defaults and tracker settings, and refuses to save over someone else's newer changes.
- **Connection tab in the configurator.** You set the network store (URL, username, password,
  certificate file) in the GUI and test it with the same checks as `tools/check_store.py`. The
  running tracker picks up saved settings by itself.
- **No installer.** `build.py` produces a release zip per OS. You copy the folder into a protected
  location, and the configurator does the rest: it shows the command your scheduled task or service
  must run, warns when standard users could change the program or read the network password, and
  fixes that with one button. It can also import a 1.x `limits.toml`. The README describes the
  Windows scheduled task, and templates are provided for the systemd service and the macOS
  LaunchDaemon.
- `tools/check_store.py`, a command-line check of a WebDAV store before installation.
- **Readable log at the normal level.** Without DEBUG, the log records each managed person's day on
  this computer: when their session starts being counted (with minutes used and the limit), when
  the screen is locked or the user switched away, when 80% of the limit is used, every logoff with its
  reason, when the session ends, and when the network store goes offline and comes back.
- `--once` and `--dry-run` tracker options for testing; rotating log files; a pytest suite.

### Changed

- Elapsed time is measured with the process's monotonic clock and capped at the check interval,
  so changes to the wall clock and time spent asleep no longer affect usage.
- The daily limit is reached at exactly `limit_minutes` (it used to be after it was exceeded).
- Files are written atomically and parsed strictly. A damaged record is set aside and restored
  from the network copy instead of wiping history.
- `timeline.json` is replaced by per-installation daily records. The 1.x timeline is not imported;
  the 1.x `limits.toml` is imported as the seed config.

### Fixed

- Day overrides saved by the 1.x configurator (`mon` ... `sun`, and the "Per-day overrides" table)
  were never applied by the tracker. They are converted and applied now.

## [1.0.0] - 2026-09-08

First tagged release. The tool has been in real use for a while, so this entry
records the state it has reached rather than a single change.

### Added

- **Timeline retention.** `timeline_period` in `defaults.py` (30 days by default) sets how long
  per-user usage records are kept in `timeline.json`. Previously the file grew without limit.
  Expiry is applied when the file is rewritten, so old entries are actually removed from disk.
- **Startup script deployment option.** The tracker can be configured as a Windows startup script
  in addition to a scheduled task, with `create_scheduledtask.ps1` updated accordingly.
- **Application version constant** (`defaults.__version__`).

### Fixed

- **Tracker crashed on every limit check.** `tracker/main.py` compared the `(minutes, timestamp)`
  tuple returned by `read_user_today_usage()` directly against the configured minute limit,
  raising `TypeError`. It now unpacks the tuple, and handles a user having no record for today
  instead of failing on `None`.
- **A single malformed timeline key disabled usage tracking entirely.** An unparseable date key
  raised an uncaught `ValueError` out of the timeline load, and because writes load before they
  save, the tracker could no longer record anything until the file was edited by hand.
  Unrecognised keys are now logged and preserved.
- **Guarded against silent history loss.** A non-positive or non-integer `timeline_period` would
  have caused the next write to permanently truncate the timeline. Invalid values are now rejected
  and the file is left untouched.
- **Tracker silently ignored a configured user whose limits failed to save.** `get_user_config()`
  returns `None` for an unmanaged user but an empty dict for a user listed in `limits.toml` with no
  limits of their own, and the tracker gated on truthiness, so both were treated as "not managed".
  A deployed config containing a bare `[users.<name>]` header meant the tracker enumerated sessions
  and enforced nothing, with no error in the log. The gate now compares against `None`, an empty
  entry falls back to the global defaults through `get_effective_limits()`, and a warning is logged.
- **Scheduled task could be killed after 72 hours.** `create_scheduledtask.ps1` built its settings
  without `-ExecutionTimeLimit`, so the registered task inherited Windows' three day default. The
  tracker is a long running loop with an at-startup trigger only, so once the Task Scheduler stopped
  it nothing restarted it until the next reboot. The script now registers it with no time limit.
- **Added configuration diagnostics.** The tracker now logs the resolved `limits.toml` path, the
  list of managed users, and the effective limits applied per user, and warns when no users are
  configured at all — the previous silent no-op was indistinguishable from normal operation.
- **Reads no longer discard data.** Timeline expiry was applied on load, which meant any caller
  reading history silently received truncated data. Loading and pruning are now separate, and
  pruning happens only in `write_timeline_data()`.
- **Locked sessions counted as active usage.** Sessions sitting on the lock screen were being
  credited with time; detection now cross-checks `LogonUI.exe` through WMI.
- **Usage limits miscalculated when the tracker ran off-schedule.** Timeline keys carry a full
  ISO datetime, and elapsed time is derived from either the configured interval or the last time
  the user was actually seen, whichever is shorter.
- **Empty day overrides were not saved** by the configurator.
- **Project root detection under PyInstaller** now resolves the configuration folder one level up
  from the bundled executable.

### Known limitations

- The configurator does not pre-fill existing settings when reopened.
- No warning is shown to the user before being logged off.
- Each computer tracks usage independently; there is no centralized multi-machine tracking.
