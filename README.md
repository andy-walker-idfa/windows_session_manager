# Windows Session Time Manager

A lightweight parental control tool for managing and enforcing computer usage time limits on Windows machines.

## What problem does it solve?

Managing children's screen time across multiple Windows computers is surprisingly difficult. Microsoft Family Safety is unreliable, and Windows security logs make it nearly impossible to accurately calculate actual session time — especially when accounting for sleep, hibernation, and inactive sessions.

This tool takes a different approach: instead of analyzing logs after the fact, it runs a lightweight tracker every few minutes that monitors active sessions in real time, accumulates usage, and enforces configured limits automatically.

## How it works

The system consists of two independent components that share a common configuration file:

### Configurator (GUI application)

The configurator is an interactive desktop application used by the parent/administrator to set up and manage time limits. It runs on demand — not as a background service.

**What it does:**

- Displays all local Windows user accounts and lets you select which ones to manage
- Opens a configuration window with two tabs:
  - **Defaults tab** — set baseline limits (weekday and weekend) that apply to all managed users
  - **User Settings tab** — configure per-user overrides with three levels of granularity:
    - *Inherit defaults only* — user follows the global defaults
    - *Custom weekday/weekend* — user has their own weekday and weekend limits, with optional per-day overrides
    - *Per-day overrides* — fully custom limits for each day of the week
- Validates all input before saving (time format, minute ranges)
- Saves configuration to a TOML file

**Three configurable parameters per time period:**

- **Earliest login** — the earliest time a user is allowed to be logged in (HH:MM format)
- **Latest login** — the latest time a user is allowed to be logged in (HH:MM format)
- **Max minutes** — maximum total active session time per day (0–1440)

### Tracker (background service)

The tracker is a non-interactive script that runs as a Windows Scheduled Task, executing every few minutes (configurable, default 5 minutes). It runs under the SYSTEM account for security and reliability.

**What it does on each execution:**

1. Enumerates all active Windows sessions using the Windows Terminal Services API
2. For each active session, checks if the logged-in user is managed
3. Retrieves the user's effective limits for today (resolving the defaults → user → day override chain)
4. Checks if the current time falls outside the allowed login window — if so, logs the user out
5. Adds the check interval minutes to the user's daily usage counter
6. Checks if the user has exceeded their daily maximum — if so, logs the user out

**Key design decisions:**

- Only active sessions (State 0) count toward usage time — disconnected sessions do not accumulate time
- The tracker runs silently with no console window (pythonw.exe)
- If a logoff attempt fails, the tracker continues tracking — it will try again on the next run
- All actions are logged to a file for troubleshooting

## Project structure

```
screen_time/
├── shared/                    # Code shared between both components
│   ├── __init__.py
│   ├── defaults.py            # Application constants and logging setup
│   ├── config_manager.py      # TOML config read/write, validation, transformation
│   ├── usage_manager.py       # JSON usage data read/write, daily tracking
│   └── users.py               # Windows local user account enumeration
├── configurator/              # GUI application
│   ├── __init__.py
│   ├── gui.py                 # All GUI classes (windows, frames, widgets)
│   └── main.py                # Configurator entry point logic
├── tracker/                   # Background tracker
│   ├── __init__.py
│   └── main.py                # Tracker logic (session check, enforcement)
├── config/                    # Runtime data (not in version control)
│   └── limits.toml            # User-configured limits
├── data/                      # Runtime data (not in version control)
│   └── timeline.json          # Daily usage counters per user
├── run_configurator.py        # Launcher for the configurator GUI
└── run_tracker.py             # Launcher for the tracker service
```

### Shared modules

- **defaults.py** — Central location for application-wide constants: filenames, check intervals, log levels, and the logging setup function
- **config_manager.py** — Handles all operations on the TOML configuration file: loading, saving, resolving effective limits (with the defaults → user day-type → user per-day fallback chain), input validation, and data transformation between GUI and TOML formats
- **usage_manager.py** — Manages the JSON timeline file that tracks daily usage per user: reading current usage, writing updates, and adding minutes to daily totals
- **users.py** — Retrieves the list of local Windows user accounts for the configurator GUI

### Configuration file format (limits.toml)

```toml
[defaults.weekday]
limit_minutes = 120
earliest_login = "08:00"
latest_login = "21:00"

[defaults.weekend]
limit_minutes = 180
earliest_login = "09:00"
latest_login = "22:00"

[users.my_child]
"Configuration level" = "Custom weekday / weekend"

[users.my_child.weekday]
limit_minutes = 90
earliest_login = "08:00"
latest_login = "20:00"

[users.my_child.weekend]
limit_minutes = 120
earliest_login = "10:00"
latest_login = "21:00"

[users.my_child.day_overrides.monday]
limit_minutes = 60
earliest_login = "15:00"
latest_login = "19:00"
```

### Limit resolution order

When the tracker needs to determine limits for a user on a specific day, it follows this chain (most specific wins):

1. **Per-user per-day override** (e.g., users.my_child.day_overrides.monday)
2. **Per-user day-type** (e.g., users.my_child.weekday)
3. **Global defaults day-type** (e.g., defaults.weekday)

Each parameter (limit_minutes, earliest_login, latest_login) falls back independently — a per-day override can set only limit_minutes while inheriting login times from a higher level.

## Requirements

- Windows 10/11
- Python 3.11 or newer
- Required packages: customtkinter, pywin32, tomli_w

## Installation and setup

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `venv\Scripts\activate`
4. Install dependencies: `pip install customtkinter pywin32 tomli_w`
5. Run the configurator: `python run_configurator.py`
6. Configure your limits and save

### Setting up the scheduled task

Create a Windows Scheduled Task to run the tracker automatically:

```powershell
$action = New-ScheduledTaskAction `
    -Execute "<path_to_venv>\Scripts\pythonw.exe" `
    -Argument "<path_to_project>\run_tracker.py"

$trigger = New-ScheduledTaskTrigger -AtStartup
# Configure repetition interval
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "00:00" `
    -RepetitionInterval (New-TimeSpan -Minutes 5)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

Register-ScheduledTask `
    -TaskName "ScreenTimeTracker" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal
```

**Important scheduled task settings:**

- Run as SYSTEM account (prevents managed users from stopping it)
- StartWhenAvailable = true (catches up after missed runs)
- AllowStartIfOnBatteries = true (runs on laptops)
- WakeToRun = false (does not wake sleeping computers — sleep time is not counted)

## Deployment with PyInstaller

To deploy on computers without Python installed, bundle the project into standalone executables:

```bash
pip install pyinstaller
pyinstaller --onedir --noconsole --distpath dist/ScreenTime --name tracker run_tracker.py
pyinstaller --onedir --noconsole --distpath dist/ScreenTime --name configurator run_configurator.py
```
Copy the entire dist/ScreenTime/ folder to the target computer — for example to C:\ScreenTime\

Then on the target computer:

Double-click configurator.exe to configure limits and save
Create the scheduled task pointing to tracker.exe:

powershell$action = New-ScheduledTaskAction -Execute "C:\ScreenTime\tracker.exe"

$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "00:00" `
    -RepetitionInterval (New-TimeSpan -Minutes 5)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

Register-ScheduledTask `
    -TaskName "ScreenTimeTracker" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal

## Limitations and future improvements

- The configurator does not pre-fill existing settings when reopened — configuration must be re-entered (or the TOML file can be edited manually)
- No warning is shown to the user before being logged off
- No multi-computer centralized tracking — each computer tracks usage independently
- No reporting or usage history visualization
