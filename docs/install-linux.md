# Install and test on Linux

Step by step, for a systemd distribution with a graphical desktop (GNOME, KDE, …). Commands are
run in a terminal as your normal (admin) user; `sudo` is used where root is needed.

Placeholders used below:
- `SRC`: the project folder on the shared exFAT partition, as Linux sees it. Find it with
  `lsblk -f` or in the file manager, e.g. `/media/$USER/SHARED/Scripts/Python/windows session time manager`.
- The NAS: `https://nas.home.arpa:30036/timemanager`, with the certificate file
  `nas-cert.crt`.

## 1. System packages

Python must be **3.11 or newer**. Check with `python3 --version`.

| Distribution | Command |
|---|---|
| Ubuntu / Debian / Mint | `sudo apt install python3 python3-venv python3-tk binutils x11-xserver-utils` |
| Fedora | `sudo dnf install python3 python3-tkinter binutils xrdb xhost` |
| Arch / Manjaro | `sudo pacman -S python tk binutils xorg-xrdb xorg-xhost` |

Ubuntu 22.04 ships Python 3.10: there, run `sudo apt install python3.11 python3.11-venv python3.11-tk`
and use `python3.11` instead of `python3` below.

## 2. Make the NAS name resolve

The examples use the NAS name `nas.home.arpa`; use the name in your certificate and URL. A name may
resolve on Windows but not on Linux, especially one ending in `.local`: many distributions look
those up only by mDNS, not in your DNS server. Check:

```sh
getent hosts nas.home.arpa
```

If it prints nothing, add the NAS address (use its real LAN IP):

```sh
echo "192.168.1.10   nas.home.arpa" | sudo tee -a /etc/hosts
getent hosts nas.home.arpa
```

## 3. Copy the source and build

Build in your home folder: a Python virtual environment cannot live on exFAT (no symbolic links),
and exFAT may be mounted so that programs cannot run from it.

```sh
SRC="/media/$USER/SHARED/Scripts/Python/windows session time manager"    # adjust
mkdir -p ~/timemanager-src
cd "$SRC"
cp -R build.py tracker.spec configurator.spec requirements.txt requirements-dev.txt pytest.ini README.md \
      run_tracker.py run_configurator.py core platforms storage tracker configurator shared service tests tools \
      ~/timemanager-src/
cp nas-cert.crt ~/            # the certificate file, wherever you keep it

cd ~/timemanager-src
python3 -m venv venv
venv/bin/python -c "import tkinter; tkinter.Tcl(); print('Tk OK', tkinter.TkVersion)"   # must print "Tk OK"; else install python3-tk (step 1)
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q               # optional: all tests should pass
venv/bin/python build.py
```

The result is `~/timemanager-src/dist/linux/TimeManager/` and `dist/TimeManager-<version>-linux.zip`.

## 4. Check the store from Linux (optional, before installing)

```sh
cd ~/timemanager-src
read -rs -p "WebDAV password: " TM_PASSWORD; export TM_PASSWORD; echo
venv/bin/python tools/check_store.py https://nas.home.arpa:30036/timemanager --user timemanager --ca-file ~/nas-cert.crt
unset TM_PASSWORD
```

All checks should pass (paste the password at the prompt; nothing is shown while typing).

## 5. Copy the program into /opt

```sh
sudo mkdir -p /opt/timemanager
sudo cp -R ~/timemanager-src/dist/linux/TimeManager/. /opt/timemanager/
sudo chown -R root:root /opt/timemanager
sudo chmod -R go-w /opt/timemanager
```

The `/.` copies the folder's contents, so the same command also upgrades an existing installation.

## 6. Configure

The configurator must run as root (it writes `instance.toml`, readable by root only). On a Wayland
desktop, first allow root to open a window:

```sh
xhost +si:localuser:root
sudo /opt/timemanager/configurator/configurator
```

In the window:

1. **Connection** tab: *Network store (WebDAV over HTTPS)*, URL
   `https://nas.home.arpa:30036/timemanager`, username `timemanager`, password, certificate file
   `~/nas-cert.crt` (*Browse…*; it is copied to `/opt/timemanager/nas-ca.crt`).
   **Test connection** → all PASS → **Save connection**.
2. The limits load from the NAS (the ones saved from Windows). The status line shows the store and
   revision. If it offers to upload limits to an empty store, something is wrong: the NAS should
   already have them. Answer **No** and check the URL.
3. **Installation** should say *Permissions OK*; otherwise press **Fix permissions**.
4. To test, add the test account on the **People** tab after creating it (step 8).

Close the window, then remove the root permission again: `xhost -si:localuser:root`.

The window follows the desktop's display scaling (read with `xrdb`). If it is still too small or
too large, set the factor yourself: `sudo TM_UI_SCALE=2 /opt/timemanager/configurator/configurator`.

## 7. Start the tracker as a service

```sh
sudo cp /opt/timemanager/timemanager-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now timemanager-tracker
systemctl status timemanager-tracker          # should say "active (running)"
sudo tail -f /opt/timemanager/logs/tracker.log
```

Expected log, as on Windows:

```
... INFO - Time Manager tracker <version> starting, install folder /opt/timemanager
... INFO - Local store: folder /opt/timemanager/data; network store: WebDAV https://nas.home.arpa:30036/timemanager/
... DEBUG - Cycle: online, 5.00 min to credit; sessions: <you> (active, not managed)
```

If no sessions are listed, show what logind reports and send it to me:

```sh
loginctl list-sessions
loginctl show-session $(loginctl list-sessions --no-legend | awk 'NR==1{print $1}') -p Name -p Active -p LockedHint -p Class -p Type -p Remote
```

## 8. Enforcement test

1. Create a standard test user (the name must match the Windows test person, so both OSs add up):
   ```sh
   sudo useradd -m -s /bin/bash tmtest && sudo passwd tmtest
   ```
2. Configurator (step 6 commands) → **People** → *Add local account…* → `tmtest`, today's row
   **Max minutes** a little above what `tmtest` already used on Windows today (or a fresh value
   tomorrow), **Save limits**.
3. Switch user to `tmtest` (top-right menu → *Switch User* on GNOME, or log out and in).
4. Expected in the log: `tmtest (active, person tmtest)` and `tmtest (tmtest): … of … min used`,
   including the minutes from Windows, then `Logged off tmtest: daily limit … reached`.
5. Lock screen: with a higher limit, log in as `tmtest` and lock the screen (Super+L). The cycle line
   shows `tmtest (locked, person tmtest)` and the minutes do not grow.

## 9. Offline and reboot

- Stop the WebDAV app on TrueNAS: the log says `Network store unreachable, enforcing offline limits`;
  start it again and the warning stops.
- Reboot into Linux and, without logging in, wait a minute; after logging in,
  `systemctl status timemanager-tracker` shows it running since boot.

## Upgrading later

```sh
cd ~/timemanager-src && cp -R "$SRC"/{core,platforms,storage,tracker,configurator,shared,tools,build.py,requirements.txt,requirements-dev.txt} .
venv/bin/pip install -r requirements-dev.txt && venv/bin/python build.py
sudo systemctl stop timemanager-tracker
sudo cp -R ~/timemanager-src/dist/linux/TimeManager/. /opt/timemanager/ && sudo chown -R root:root /opt/timemanager
sudo systemctl start timemanager-tracker
```

If something fails, send the step number, the command output and `sudo tail -30 /opt/timemanager/logs/tracker.log`.
