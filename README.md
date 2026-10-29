# Time Manager

Parental control for computer time: daily limits and allowed login hours per person, enforced
on **Windows, Linux and macOS**, with one shared daily total across all computers and OSs.

Current version: **2.1.0**. See [CHANGELOG.md](CHANGELOG.md).

## How it works

Each computer, and each OS on a multi-boot computer, runs its own **tracker** as a SYSTEM/root
service. Every few minutes the tracker:

1. Lists the active, unlocked desktop sessions. Locked screens and switched-away sessions do not count.
2. Maps each account to a **person** from the configuration. Accounts that don't belong to a person
   are ignored and not recorded.
3. Logs the person off if the time is outside their allowed login hours. Between these checks,
   new logins are checked every 20 seconds, so someone who logs in while already over the limit
   or outside the hours is logged off at once.
4. Adds the elapsed time to this installation's usage record for today. It writes locally first,
   then copies the record to the network store.
5. Adds up the person's minutes from **all** installations and logs them off when the daily limit
   is reached.

```
   Windows PC         Linux (same PC)       macOS laptop
   tracker ──┐         tracker ──┐           tracker ──┐
     local store         local store           local store
             └───────────────────┴─────────────────────┴──►  network store (WebDAV over HTTPS)
                                                              config/limits.toml
                                                              records/<installation>/<date>.json
                                                              events/<installation>/<date>.jsonl
                                                              writers/<installation>.json
```

**Offline.** If the network store can't be reached, the tracker keeps working from local data plus
the last records it saw from other installations today. It then applies the **stricter** of the
person's own limits and the global defaults. Records are uploaded once the store is reachable again.

**Configuration.** The **configurator** (a GUI) edits `config/limits.toml` on the network store.
Every tracker downloads it each cycle and only uses it after checking that it is valid, so a
broken file never replaces a working one. Each installation also keeps a local copy for offline
use. A revision number stops two people from overwriting each other's changes.

**Shared activity log.** Next to its local log file, every tracker keeps a journal of what happened
to managed people on that computer: session counted, screen locked, user switched, close to the
limit, logged off and why, offline and back. It is uploaded together with the usage records, so the
configurator's **Activity** tab can show, for any day, the minutes per person **per computer** and
one combined timeline of all computers, and export both as CSV.

### Limits

Per time period there are three values: **Max minutes** (0-1440 per day), **Earliest login** and
**Latest login** (HH:MM). For each value separately, the most specific setting wins:

1. Person's day override (for example Monday)
2. Person's weekday / weekend values
3. Global defaults for weekday / weekend

### Configuration file (`limits.toml`, written by the configurator)

```toml
schema = 1
revision = 4

[settings]                      # optional
check_interval_minutes = 5
retention_days = 30
log_level = "INFO"

[defaults.weekday]
limit_minutes = 120
earliest_login = "08:00"
latest_login = "21:00"

[defaults.weekend]
limit_minutes = 180

[users.sam]
accounts = ["sam.k"]           # other account names of the same person, on other computers
[users.sam.weekday]
limit_minutes = 90
[users.sam.day_overrides.monday]
latest_login = "19:00"
```

Account names are compared without regard to case.

## Setup guide (administrator)

### 1. Network store

Any WebDAV server reachable over HTTPS works. For TrueNAS Scale:

1. Create a dataset, for example `tank/timemanager`. Don't share it over SMB or NFS: only the
   trackers should write to it.
2. Install the **WebDAV** app. Share the dataset under a name such as `timemanager`, with
   authentication set to *basic*, and HTTPS enabled.
3. Create a dedicated user for the trackers (for example `timemanager`) with access to this share only.
4. Note the URL, for example `https://truenas.lan:30035/timemanager`. If the certificate is
   self-signed, export its CA certificate as a PEM file and copy it to each computer. Certificates
   are always verified.
5. Recommended: schedule periodic ZFS snapshots of the dataset.

A cloud WebDAV provider works the same way, but only over `https://`.

### 2. Operating system preparation

- **Multi-boot machines:** make Windows keep the hardware clock in UTC, as Linux and macOS do. In an
  administrator prompt, run
  `reg add HKLM\SYSTEM\CurrentControlSet\Control\TimeZoneInformation /v RealTimeIsUniversal /t REG_QWORD /d 1 /f`,
  then reboot.
- **Windows time zone:** by default, standard users can change the time zone. That shifts midnight
  and the allowed login hours. Remove the right in `secpol.msc` → Local Policies → User Rights
  Assignment → *Change the time zone* → remove **Users**.
- **Children use standard (non-admin) accounts** on every OS.
- **Install the tracker on every OS** on every computer the children can use.
- **Firmware:** set a firmware (BIOS/UEFI) setup password, disable booting from USB, and protect the
  OpenCore boot picker with a password. Otherwise an OS without the tracker can be booted.

### 3. Get the program

Step-by-step guides, including testing: [another Windows computer](docs/install-windows.md), [Linux](docs/install-linux.md), [macOS](docs/install-macos.md).

There is no installer. Each OS has its own build, a `TimeManager` folder containing `tracker` (the
service) and `configurator` (the GUI). Get it in either of two ways:

- **Release zip:** `TimeManager-<version>-<windows|linux|macos>.zip`.
- **Build it yourself** from the source, so you know exactly what runs as SYSTEM/root. PyInstaller
  can't build for another OS, so build on each OS with Python 3.11 or newer:
  ```sh
  python -m venv venv
  venv/bin/pip install -r requirements-dev.txt          # Windows: venv\Scripts\pip ...
  venv/bin/python build.py                               # Windows: venv\Scripts\python build.py
  ```
  The result is `dist/<os>/TimeManager/`, plus the same folder as a zip in `dist/`.

On Windows, a downloaded unsigned program triggers SmartScreen ("Windows protected your PC").
Choose *More info → Run anyway*, or build it yourself.

### 4. Copy it into a protected folder

The tracker runs as SYSTEM/root. A user who can change its folder could replace the program and
gain full control of the computer, so the folder must be writable by administrators only.

| OS | Copy the `TimeManager` folder to | How |
|---|---|---|
| Windows | `C:\Program Files\TimeManager` | Explorer (it asks for administrator rights). `Program Files` is already protected against changes by standard users |
| Linux | `/opt/timemanager` | `sudo mkdir -p /opt/timemanager && sudo cp -R TimeManager/. /opt/timemanager/ && sudo chown -R root:root /opt/timemanager` |
| macOS | `/usr/local/timemanager` | `sudo mkdir -p /usr/local/timemanager && sudo cp -R TimeManager/. /usr/local/timemanager/ && sudo chown -R root:wheel /usr/local/timemanager` |

The configurator checks these permissions and can fix them (step 5).

**Upgrading:** stop the task/service, copy the new folder over the old one, and start it again.
`instance.toml`, `data/` and `logs/` are kept.

### 5. Configure

Start the configurator **with administrator rights**: on Windows it asks through UAC; on Linux and
macOS, run `sudo <install folder>/configurator/configurator`. On Linux Wayland desktops, first allow
root to open windows with `xhost +si:localuser:root`.

- **Connection:** where this computer finds the network store.
  - Choose *Network store (WebDAV over HTTPS)*, then enter the URL (with the share name, e.g.
    `https://nas.home.arpa:30036/timemanager`) and the username and password.
  - Choose the certificate file if the NAS certificate isn't publicly trusted. It's copied into
    the install folder.
  - **Test connection** runs the same checks as `tools/check_store.py`. **Save connection**
    writes `instance.toml` (readable by SYSTEM/Administrators or root only), and the tracker
    reconnects within one check interval with no restart.
  - When you edit later, leave the password blank to keep the saved one.
  - If the store has no limits yet, the configurator offers to upload this computer's limits.
  - **Installation** shows the exact program your task/service must run (with a *Copy* button). It
    warns if standard users can change the program folder or read `instance.toml`; **Fix
    permissions** corrects that.
- **People:** add a person by name, or pick a local account. Use *Other account names* when the
  same child has a different account name on another computer. Blank fields inherit.
- **Defaults:** the limits that apply to everyone. They are also the offline limits.
- **Settings:** the check interval, how many days of history to keep, and the log level.
- **Activity:** choose a day to see the minutes per person on each computer, with the total and
  the limit, and the combined timeline of all computers (in local time). **Export CSV…** saves
  both, for a spreadsheet or your own reports.
- **Import from file…** loads a `limits.toml`, for example from version 1.x; press **Save limits**
  to store it.

Trackers pick up saved limits within one check interval.

### 6. Start the tracker automatically

The tracker runs as one endless loop (one cycle every check interval), so exactly one instance must
run, from boot, as SYSTEM/root. You set this up yourself.

#### Windows: scheduled task

Create it in Task Scheduler (*Create Task…*, not *Create Basic Task*):

| Setting | Value | Why |
|---|---|---|
| Program | `C:\Program Files\TimeManager\tracker\tracker.exe` (no arguments) | finds `instance.toml` one folder up by itself |
| Run as | **SYSTEM**, *Run with highest privileges* | logging users off needs it; children can't stop it |
| Trigger | **At startup** | runs before anyone logs in |
| Stop the task if it runs longer than | **unchecked** (no time limit) | otherwise Windows kills it after 3 days |
| If the task fails, restart every | 1 minute, up to 999 times | recovers from a crash |
| If the task is already running | **Do not start a new instance** | two trackers would count time twice |
| Power | **do not** "Start only on AC power"; **do not** stop on battery | laptops |
| Wake the computer to run | unchecked | sleep time isn't usage anyway |

Don't use a repeating trigger (every 5 minutes): the tracker repeats by itself, and repetition as
in 1.x would start overlapping instances. After upgrading from 1.x, delete the old task.

#### Linux: systemd service

The template `timemanager-tracker.service` is in the build folder (and in `service/` in the source):

```sh
sudo cp /opt/timemanager/timemanager-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now timemanager-tracker
systemctl status timemanager-tracker
```

#### macOS: LaunchDaemon

The template `local.timemanager.tracker.plist` is in the build folder (and in `service/`):

```sh
sudo cp /usr/local/timemanager/local.timemanager.tracker.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/local.timemanager.tracker.plist
sudo chmod 644 /Library/LaunchDaemons/local.timemanager.tracker.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/local.timemanager.tracker.plist
sudo launchctl print system/local.timemanager.tracker
```

If you installed somewhere else, change the program path in the template (it must match what the
configurator's Installation section shows).

### 7. Check that it works

Read `<install folder>/logs/tracker.log` (as administrator/root). Set the log level to DEBUG in the
configurator to see every session and its minutes. To run one cycle by hand without logging anyone
off, stop the task/service first, then run, as administrator/root:

```sh
<install folder>/tracker/tracker --once --dry-run
```

To test enforcement, give a test account `limit_minutes = 1`.

## Project structure

```
core/          pure logic: config validation, limit resolution, usage records, enforcement rules
platforms/     OS adapters: windows.py (WTS + LogonUI), linux.py (loginctl), macos.py (ioreg + launchctl)
storage/       store backends: folder.py, webdav.py
tracker/       sync.py (local/network rules), cycle.py (one tracker cycle), main.py (service loop)
configurator/  session.py (load/save with revision check), gui.py (customtkinter window)
shared/        version and paths, instance.toml + installation identity, permission checks, logging
service/       systemd unit (Linux) and LaunchDaemon (macOS) templates
tools/         check_store.py: command-line check of a WebDAV store
tests/         pytest suite: run with  python -m pytest
```

Local data lives next to the program: `instance.toml`, `data/` (own records, cache, state) and
`logs/` (rotating, 5 × 1 MB).

## Limitations

- No warning before logoff yet. The OS adapters already have a place for it (`notify`).
- Logoff is forced, so unsaved work is lost.
- An unlocked but idle session counts as usage.
- Changes in the configurator always overwrite whole settings; there's no per-field merge with
  someone else's edits (a revision conflict asks you to reload).
