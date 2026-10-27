# Install and test on another Windows computer

Step by step, for an additional Windows 10/11 computer (for example a laptop) that joins an existing
Time Manager setup: the network store is already running and the limits are already configured
from another computer. The new computer needs **no Python**: you copy the program built on the
first computer.

Placeholders used below:
- The NAS: `https://nas.home.arpa:30036/timemanager` and its certificate file `nas-cert.crt` are
  examples: use your own URL and file name throughout.
- `sam`: the child's account on this computer, as an example.

Run commands in **PowerShell as administrator** (right-click Start → *Terminal (Admin)*).

## 1. Prepare the computer

1. **The child uses a standard account.** *Settings → Accounts → Other users* → the child's account
   → *Change account type* → **Standard User**. An administrator could stop the tracker.
2. **Note the child's account name** on this computer:
   ```powershell
   Get-LocalUser | Where-Object Enabled | Select-Object Name
   ```
   If it differs from the person's name in Time Manager (for example `sam.k` here and `sam`
   elsewhere), you add it as another account name in step 4.
3. **Remove older time controls** that would act on their own and confuse the logs:
   - a 1.x Time Manager task (Task Scheduler → disable it);
   - logon scripts: `gpedit.msc` → *User Configuration → Windows Settings → Scripts (Logon/Logoff)* →
     *Logon* → both the **Scripts** and the **PowerShell Scripts** tab should be empty;
   - Microsoft Family Safety screen time for the child's account, if you used it.
4. **Time zone:** standard users can change it, which would shift midnight and the allowed hours.
   `secpol.msc` → *Local Policies → User Rights Assignment* → *Change the time zone* → remove
   **Users**. (Windows Home has no `secpol.msc`; there this protection is not available.)

## 2. Bring the program over

On the first computer, `build.py` produced `dist\TimeManager-2.0.0-windows.zip`. Copy it to this
computer (USB stick or network share).

1. If the zip came by browser, e-mail or cloud storage: right-click it → *Properties* → tick
   **Unblock** → *OK*. Otherwise Windows marks every file as downloaded and SmartScreen asks on start.
2. Extract it. It contains one folder, `TimeManager`.
3. Copy that folder to `C:\Program Files\` (Explorer asks for administrator rights). Result:
   `C:\Program Files\TimeManager\tracker\tracker.exe` and `...\configurator\configurator.exe`.
4. Copy the certificate file (`nas-cert.crt`) to this computer too, for example to your Desktop.

## 3. Check that the NAS is reachable

```powershell
Resolve-DnsName nas.home.arpa
Test-NetConnection nas.home.arpa -Port 30036          # TcpTestSucceeded : True
```

If the name does not resolve, add it to the hosts file (use the NAS's real LAN IP):

```powershell
Add-Content "$env:WINDIR\System32\drivers\etc\hosts" "`r`n192.168.1.10   nas.home.arpa"
```

## 4. Configure

Start `C:\Program Files\TimeManager\configurator\configurator.exe` (it asks for administrator rights).

1. **Connection** tab: *Network store (WebDAV over HTTPS)*, URL
   `https://nas.home.arpa:30036/timemanager`, username `timemanager`, password, **Certificate file**
   → *Browse…* → `nas-cert.crt` (it is copied into the program folder; the field must not stay empty
   for a NAS with its own certificate). **Test connection** → all PASS → **Save connection**.
2. The limits load from the NAS: the status line shows the store and a revision number, and
   **People** lists the persons configured on the other computers. If the configurator offers to
   upload limits to an *empty* store, the URL is wrong: answer **No** and check it.
3. **People** → the child's person → **Other account names**: add this computer's account name if
   it differs (step 1.2) → **Save limits**. Without this, the tracker ignores the account here.
4. **Installation** (Connection tab) should say *Permissions OK*; otherwise press **Fix permissions**.
   It also shows the program for the scheduled task.

## 5. Create the scheduled task

Task Scheduler → *Create Task…* (not *Create Basic Task*):

| Setting | Value |
|---|---|
| General | Run as **SYSTEM** (*Change User or Group…* → `SYSTEM`), **Run with highest privileges** |
| Triggers | **At startup**, no repetition |
| Actions | Start a program: `C:\Program Files\TimeManager\tracker\tracker.exe` (no arguments) |
| Conditions | untick **Start the task only if the computer is on AC power**; untick *Wake the computer to run this task* |
| Settings | untick **Stop the task if it runs longer than**; *If the task fails, restart every* **1 minute**, up to **999** times; *If the task is already running*: **Do not start a new instance** |

Then right-click the task → **Run**.

On a laptop the AC power settings matter: with the defaults, the tracker would not start on battery.

## 6. Check that it runs

```powershell
Get-Process tracker | Select-Object Id, Path
Get-Content "C:\Program Files\TimeManager\logs\tracker.log" -Tail 20 -Wait     # Ctrl+C to stop
```

Expected:

```
... INFO - Time Manager tracker 2.0.0 starting, install folder C:\Program Files\TimeManager
... INFO - Local store: folder C:\Program Files\TimeManager\data; network store: WebDAV https://nas.home.arpa:30036/timemanager/
... INFO - Writer id for this installation: <new id>
```

The new writer id shows this computer is a separate installation; its minutes are added to the
other computers' minutes on the NAS.

## 7. Test

1. **Shared total:** log in as the child. The log shows
   `sam (sam.k): session counted on this computer, X of Y min used today.` X includes the minutes
   already used on the other computers today.
2. **Lock screen:** press Win+L. The log shows `screen locked, not counted` and the minutes stop.
3. **Limit:** when the total reaches the limit, the child is logged off within 5 minutes:
   `Logged off sam.k: daily limit of … min reached`. (To test without waiting, temporarily lower
   the child's limit in the configurator, or use a test account as described in the README.)
4. **Offline:** switch Wi-Fi off. The log shows `Network store unreachable, enforcing offline limits`;
   switch it on again: `Network store reachable again`, and the offline minutes are uploaded.
5. **Reboot:** restart the computer; the log shows a new `starting` line from boot time.

## How a laptop behaves away from home

- Away from home the NAS is unreachable, so the laptop runs **offline**: it counts locally and
  applies the **stricter** of the child's own limits and the global *Defaults*. Minutes used on
  other computers that day are included as far as the laptop saw them before it went offline.
- Back home, the laptop uploads its records and every computer includes them in the daily total.
- Sleep and a closed lid are not counted.

## Upgrading later

Build the new version on the first computer, then here: end the task (Task Scheduler → right-click
→ *End*), copy the new `tracker` and `configurator` folders over the ones in
`C:\Program Files\TimeManager`, and run the task again. Settings, data and logs are kept.

## Removing

Delete the scheduled task, then the folder `C:\Program Files\TimeManager`.

If something fails, send the step number and the last 30 lines of
`C:\Program Files\TimeManager\logs\tracker.log`.
