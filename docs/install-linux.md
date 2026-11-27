# Install and test on Linux

Step by step, for a systemd distribution with a graphical desktop (GNOME, KDE, …). Commands are
run in a terminal as your normal (admin) user; `sudo` is used where root is needed.

There is no ready-made Linux download: you build the program from the source on GitHub
(step 3), which takes a few minutes. This guide assumes the network store (a WebDAV share, see
*Setup guide → 1. Network store* in the [README](../README.md)) already exists.

Placeholders used below:
- The NAS: `https://nas.home.arpa:30036/timemanager`, with the certificate file
  `nas-cert.crt`. These are examples: use your own URL and file name throughout.
- `v2.2.2`: the release to install. Use the newest one listed on the
  [Releases page](https://github.com/andy-walker-idfa/windows_session_manager/releases).

## 1. System packages

Python must be **3.11 or newer**. Check with `python3 --version`.

| Distribution | Command |
|---|---|
| Ubuntu / Debian / Mint | `sudo apt install git python3 python3-venv python3-tk binutils x11-xserver-utils` |
| Fedora | `sudo dnf install git python3 python3-tkinter binutils xrdb xhost` |
| Arch / Manjaro | `sudo pacman -S git python tk binutils xorg-xrdb xorg-xhost` |

`git` is only needed to download the source with `git clone` (step 3, option A).

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

## 3. Get the source and build

The source goes into `~/timemanager-src` in your home folder. Get it in one of these ways.

**A. With git (recommended, makes upgrading easy):**

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

**C. From a copy you already have**, for example on a partition shared with Windows on a
multi-boot computer. Copy it to your home folder first: a Python virtual environment cannot live on
exFAT or NTFS (no symbolic links), and such partitions are often mounted so that programs cannot
run from them.

```sh
SRC="/media/$USER/SHARED/Scripts/Python/windows session time manager"    # adjust; see lsblk -f
mkdir -p ~/timemanager-src
cd "$SRC"
cp -R build.py tracker.spec configurator.spec requirements.txt requirements-dev.txt pytest.ini README.md \
      run_tracker.py run_configurator.py core platforms storage tracker configurator shared service assets tests tools \
      ~/timemanager-src/
```

Whichever way you chose, copy the NAS certificate file to your home folder (the configurator asks
for it in step 6), then build:

```sh
cp /path/to/nas-cert.crt ~/            # the certificate file, wherever you keep it

cd ~/timemanager-src
python3 -m venv venv
venv/bin/python -c "import tkinter; tkinter.Tcl(); print('Tk OK', tkinter.TkVersion)"   # must print "Tk OK"; else install python3-tk (step 1)
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q               # optional: all tests should pass
venv/bin/python build.py
```

The result is `~/timemanager-src/dist/linux/TimeManager/` and `dist/TimeManager-<version>-linux.zip`.

**Ready-made build instead (optional).** From 2.2.2, the release also carries
`TimeManager-<version>-linux.zip` under *Assets*. It was built on Debian 13 and runs only on
distributions with glibc 2.41 or newer (check with `ldd --version`); on older ones, build it as
above. To use it, unzip it and copy the `TimeManager` folder in step 5 instead of
`~/timemanager-src/dist/linux/TimeManager`. Python is bundled: of step 1, you only need the
`xhost`/`xrdb` package (`x11-xserver-utils`, `xrdb xhost` or `xorg-xrdb xorg-xhost`). Step 4 needs the
source, so skip it.

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

**Menu launcher (optional, versions after 2.2.1).** To start the configurator from the GNOME or KDE application menu, for
the desktop user who manages the limits (not with sudo):

```sh
install -m 644 /opt/timemanager/time-manager.desktop ~/.local/share/applications/
```

*Time Manager* then appears in the menu with its icon. It opens a terminal for the sudo password,
allows root to open the window (`xhost`) and removes that permission again when the window closes.

## 7. Start the tracker as a service

```sh
sudo install -m 644 /opt/timemanager/timemanager-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now timemanager-tracker
systemctl status timemanager-tracker          # should say "active (running)"
sudo tail -f /opt/timemanager/logs/tracker.log
```

`install -m 644` copies the file with the permissions systemd expects. If you used `cp` and the
source came from an exFAT or NTFS partition, the file is marked executable, and systemd warns at
every boot: *Configuration file /etc/systemd/system/timemanager-tracker.service is marked
executable. Please remove executable permission bits.* The service still works; to remove the
warning, run:

```sh
sudo chmod 644 /etc/systemd/system/timemanager-tracker.service
sudo systemctl daemon-reload
```

Expected log, as on Windows:

```
... INFO - Time Manager tracker <version> starting, install folder /opt/timemanager
... INFO - Local store: folder /opt/timemanager/data; network store: WebDAV https://nas.home.arpa:30036/timemanager/
... DEBUG - Cycle: online, 5.00 min to credit; sessions: <you> (active, not managed)
```

If no sessions are listed, show what logind reports and include it when you report the problem:

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
sudo systemctl stop timemanager-tracker
sudo cp -R ~/timemanager-src/dist/linux/TimeManager/. /opt/timemanager/ && sudo chown -R root:root /opt/timemanager
sudo systemctl start timemanager-tracker
```

Settings (`instance.toml`), data and logs in `/opt/timemanager` are kept.

## Removing

```sh
sudo systemctl disable --now timemanager-tracker
sudo rm /etc/systemd/system/timemanager-tracker.service
sudo systemctl daemon-reload
sudo rm -rf /opt/timemanager
```

If something fails, open an [issue on GitHub](https://github.com/andy-walker-idfa/windows_session_manager/issues)
with the step number, the command output and `sudo tail -30 /opt/timemanager/logs/tracker.log`
(remove anything private, such as your NAS address, first).
