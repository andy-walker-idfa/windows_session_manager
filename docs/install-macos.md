# Install and test on macOS

Step by step, for macOS 13 (Ventura) or newer, including a Hackintosh; written for macOS 15 (Sequoia). Commands are run in
Terminal as your normal admin user; `sudo` is used where root is needed.

There is no ready-made macOS download: you build the program from the source on GitHub (step 3),
which takes a few minutes. This guide assumes the network store (a WebDAV share, see
*Setup guide → 1. Network store* in the [README](../README.md)) already exists.

Placeholders used below:
- `v2.2.2`: the release to install. Use the newest one listed on the
  [Releases page](https://github.com/andy-walker-idfa/windows_session_manager/releases).
- The NAS: `https://nas.home.arpa:30036/timemanager` and its certificate file `nas-cert.crt` are
  examples: use your own URL and file name throughout.

## 1. Python

You need Python **3.11 or newer with Tk** (the configurator's window toolkit). Use one you already
have if it qualifies; install one only if not.

**Find the Pythons on this Mac:**

```sh
which -a python3 python3.13 python3.12 python3.11 2>/dev/null
ls -d /Library/Frameworks/Python.framework/Versions/*/bin/python3 2>/dev/null     # python.org installs
ls -d /usr/local/bin/python3* /opt/homebrew/bin/python3* 2>/dev/null              # Homebrew installs
```

**Check a candidate** (replace the path with one from the lists above):

```sh
PY=/usr/local/bin/python3.13          # the candidate
"$PY" --version                         # must be 3.11 or newer
"$PY" -c "import tkinter; tkinter.Tcl(); print('Tk OK', tkinter.TkVersion)"
```

| Result | What to do |
|---|---|
| Version 3.11+ and `Tk OK` | Use it: keep this `PY=` line, it is used in step 3 |
| Version 3.11+ but `No module named '_tkinter'` (Homebrew Python) | Add Tk to it: `brew install python-tk@3.13` (use the same version number as your Python), then check again |
| Older than 3.11, or `/usr/bin/python3` | Not usable (`/usr/bin/python3` is Apple's Python 3.9). Try another candidate, or install Python 3.13 from **python.org** (*Downloads → macOS → universal2 installer*; it includes Tk). It then lives at `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` |

A Python managed by pyenv or conda works too, as long as the check above prints `Tk OK`.

## 2. Make the NAS name resolve

The examples use the NAS name `nas.home.arpa`; use the name in your certificate and URL. A name may
resolve on Windows but not on macOS, especially one ending in `.local`: macOS resolves those with
Bonjour (mDNS) first, not with your DNS server. Check:

```sh
dscacheutil -q host -a name nas.home.arpa
```

If it prints no `ip_address`, add the NAS address (use its real LAN IP) and flush the cache:

```sh
echo "192.168.1.10   nas.home.arpa" | sudo tee -a /etc/hosts
sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder
dscacheutil -q host -a name nas.home.arpa
```

## 3. Get the source and build

The source goes into `~/timemanager-src` in your home folder. Get it in one of these ways.

**A. With git (recommended, makes upgrading easy).** `git` comes with Apple's Command Line Tools;
if macOS offers to install them on the first `git` command, accept and run the command again.

```sh
git clone --branch v2.2.2 https://github.com/andy-walker-idfa/windows_session_manager.git ~/timemanager-src
```

**B. Without git**, as the source archive of a release (the *Source code (tar.gz)* link on the
[Releases page](https://github.com/andy-walker-idfa/windows_session_manager/releases)):

```sh
mkdir -p ~/timemanager-src
curl -L https://github.com/andy-walker-idfa/windows_session_manager/archive/refs/tags/v2.2.2.tar.gz \
  | tar -xz --strip-components=1 -C ~/timemanager-src
```

**C. From a copy you already have**, for example on a partition shared with another OS. Copy it to
your home folder first: a Python virtual environment cannot live on exFAT (no symbolic links).

```sh
SRC="/Volumes/SHARED/Scripts/Python/windows session time manager"    # adjust; see ls /Volumes
mkdir -p ~/timemanager-src
cd "$SRC"
cp -R build.py tracker.spec configurator.spec requirements.txt requirements-dev.txt pytest.ini README.md \
      run_tracker.py run_configurator.py core platforms storage tracker configurator shared service tests tools docs \
      ~/timemanager-src/
```

Whichever way you chose, copy the NAS certificate file to your home folder (the configurator asks
for it in step 6), then build:

```sh
PY=/usr/local/bin/python3.13       # the Python you chose in step 1
"$PY" --version || echo "PY is wrong: set it to the Python from step 1"
cp /path/to/nas-cert.crt ~/        # the certificate file, wherever you keep it

cd ~/timemanager-src
"$PY" -m venv venv
venv/bin/python -c "import tkinter; tkinter.Tcl(); print('Tk OK', tkinter.TkVersion)"   # must print "Tk OK"
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q               # optional: all tests should pass
venv/bin/python build.py
```

The result is `~/timemanager-src/dist/macos/TimeManager/` and `dist/TimeManager-<version>-macos.zip`.

## 4. Check the store from macOS (optional, before installing)

```sh
cd ~/timemanager-src
read -rs "TM_PASSWORD?WebDAV password: "; export TM_PASSWORD; echo
venv/bin/python tools/check_store.py https://nas.home.arpa:30036/timemanager --user timemanager --ca-file ~/nas-cert.crt
unset TM_PASSWORD
```

(`read -rs "NAME?prompt"` is the zsh form; macOS Terminal uses zsh.) All checks should pass.

**macOS 15 (Sequoia) and newer: Local Network permission.** Programs started from Terminal need
permission to reach devices on your LAN. macOS asks once ("Terminal would like to find and connect
to devices on your local network"): choose **Allow**. If the checks fail with `No route to host`,
enable **Terminal** in *System Settings → Privacy & Security → Local Network* and run them again.
This also applies to the configurator (step 6). The tracker service itself is a system LaunchDaemon
and does not need it.

## 5. Copy the program into /usr/local

```sh
sudo mkdir -p /usr/local/timemanager
sudo cp -R ~/timemanager-src/dist/macos/TimeManager/. /usr/local/timemanager/
sudo chown -R root:wheel /usr/local/timemanager
sudo chmod -R go-w /usr/local/timemanager
sudo xattr -dr com.apple.quarantine /usr/local/timemanager 2>/dev/null; true
```

The `/.` copies the folder's contents, so the same command also upgrades an existing installation.
The `xattr` line only matters if you install from a downloaded zip instead of your own build.

## 6. Configure

The configurator must run as root (it writes `instance.toml`, readable by root only):

```sh
sudo /usr/local/timemanager/configurator/configurator
```

In the window:

1. **Connection** tab: *Network store (WebDAV over HTTPS)*, URL
   `https://nas.home.arpa:30036/timemanager`, username `timemanager`, password, certificate file
   `/Users/<you>/nas-cert.crt` (*Browse…*; the dialog runs as root and starts in root's
   home, so go to */Users/<you>* — or type the full path; `~` would mean root's home here. The file is
   copied to `/usr/local/timemanager/nas-ca.crt`). **This field must not stay empty**: the NAS
   certificate is self-signed, so without it every connection fails with `CERTIFICATE_VERIFY_FAILED`.
   **Test connection** → all PASS → **Save connection**.
2. The limits load from the NAS (the ones saved from Windows/Linux). If it offers to upload limits to
   an empty store, something is wrong: answer **No** and check the URL.
3. **Installation** should say *Permissions OK*; otherwise press **Fix permissions**.

## 7. Start the tracker as a LaunchDaemon

```sh
sudo cp /usr/local/timemanager/local.timemanager.tracker.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/local.timemanager.tracker.plist
sudo chmod 644 /Library/LaunchDaemons/local.timemanager.tracker.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/local.timemanager.tracker.plist
sudo launchctl print system/local.timemanager.tracker | grep -E "state|pid"     # state = running
sudo tail -f /usr/local/timemanager/logs/tracker.log
```

macOS may show *Background Items Added*. Make sure it is allowed in *System Settings → General →
Login Items & Extensions* (the entry may be shown as "tracker").

Expected log, as on the other systems:

```
... INFO - Time Manager tracker <version> starting, install folder /usr/local/timemanager
... INFO - Local store: folder /usr/local/timemanager/data; network store: WebDAV https://nas.home.arpa:30036/timemanager/
... DEBUG - Cycle: online, 5.00 min to credit; sessions: <you> (active, not managed)
```

The tracker reads sessions from the IORegistry. If sessions are missing or wrongly shown as locked,
include the output of this command in your report (once normally, once with the screen locked and then unlocked
with another user's session open):

```sh
ioreg -n Root -d1 -a | plutil -p - | grep -E "kCGSSessionUserNameKey|kCGSSessionOnConsoleKey|CGSSessionScreenIsLocked|kCGSessionLoginDoneKey"
```

## 8. Enforcement test

1. Create a standard test user named **`tmtest`** (same name as on the other systems, so the
   minutes add up): *System Settings → Users & Groups → Add User…*, account type **Standard**.
   Log in with it once to finish setting it up.
2. Configurator (step 6) → **People**: `tmtest` is already there if you created it on Windows or
   Linux; otherwise *Add local account…* → `tmtest`. Set today's **Max minutes** a little above what
   it has already used today, **Save limits**.
3. Switch to `tmtest` (fast user switching: menu bar → Control Center → user name, or log out and in).
4. Expected in the log: `tmtest (active, person tmtest)` and `tmtest (tmtest): … of … min used`,
   including the minutes from the other systems, then `Logged off tmtest: daily limit … reached`.
5. Lock screen: with a higher limit, log in as `tmtest` and lock the screen (Ctrl+Cmd+Q). The cycle
   line shows `tmtest (locked, person tmtest)` and the minutes do not grow. If it shows `active`
   instead, include the `ioreg` output from step 7 taken while locked.

## 9. Offline and reboot

- Stop the WebDAV app on TrueNAS: the log says `Network store unreachable, enforcing offline limits`;
  start it again and the warning stops.
- Reboot into macOS; after logging in,
  `sudo launchctl print system/local.timemanager.tracker | grep state` shows `running`.

## Upgrading later

First get the new source (use the new release tag), the same way as in step 3:

```sh
cd ~/timemanager-src
TAG=v2.2.3                                                   # the new release tag
git fetch --tags && git checkout "$TAG"                     # A. with git
# B. without git: download the new archive over the old files
# curl -L https://github.com/andy-walker-idfa/windows_session_manager/archive/refs/tags/$TAG.tar.gz | tar -xz --strip-components=1 -C ~/timemanager-src
# C. from your own copy: repeat the cp -R command of step 3
```

Then build and replace the installed program:

```sh
cd ~/timemanager-src
venv/bin/pip install -r requirements-dev.txt && venv/bin/python build.py
sudo launchctl bootout system /Library/LaunchDaemons/local.timemanager.tracker.plist
sudo cp -R dist/macos/TimeManager/. /usr/local/timemanager/ && sudo chown -R root:wheel /usr/local/timemanager
sudo launchctl bootstrap system /Library/LaunchDaemons/local.timemanager.tracker.plist
```

## Removing

```sh
sudo launchctl bootout system /Library/LaunchDaemons/local.timemanager.tracker.plist
sudo rm /Library/LaunchDaemons/local.timemanager.tracker.plist
sudo rm -rf /usr/local/timemanager
```

If something fails, open an [issue on GitHub](https://github.com/andy-walker-idfa/windows_session_manager/issues)
with the step number, the command output and `sudo tail -30 /usr/local/timemanager/logs/tracker.log`
(remove anything private, such as your NAS address, first).
