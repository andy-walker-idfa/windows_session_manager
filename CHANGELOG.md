# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
