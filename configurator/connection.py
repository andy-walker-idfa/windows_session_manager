"""Connection tab: where this installation finds the network store (instance.toml)."""

import dataclasses
import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter

from shared.instance import (InstanceError, RemoteSettings, install_certificate, instance_path, load_instance,
                             save_remote_settings, validate_remote)
from shared.security import find_issues, fix_all, protect_secret_file, tracker_command
from storage.base import StoreError
from storage.diagnostics import check_folder, check_webdav

TYPE_LABELS = {"webdav": "Network store (WebDAV over HTTPS)", "folder": "Folder (local or mounted)",
               "none": "This computer only"}
LABEL_TYPES = {v: k for k, v in TYPE_LABELS.items()}


class ConnectionFrame(customtkinter.CTkFrame):
    def __init__(self, master, root: Path, remote: RemoteSettings, on_saved):
        super().__init__(master, fg_color="transparent")
        self.root = root
        self.saved = remote
        self.on_saved = on_saved
        self.passed_for: RemoteSettings | None = None  # settings that last passed the test
        self.results: queue.Queue = queue.Queue()
        self.grid_columnconfigure(1, weight=1)

        row = 0
        customtkinter.CTkLabel(self, text="Where this computer stores and shares usage data. Saved in "
                                          "instance.toml; the tracker picks up changes within one check interval.",
                               anchor="w", wraplength=740, justify="left").grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 10))
        row += 1
        customtkinter.CTkLabel(self, text="Store type").grid(row=row, column=0, sticky="w", padx=(0, 12))
        self.type_menu = customtkinter.CTkOptionMenu(self, values=list(TYPE_LABELS.values()), width=300,
                                                     command=lambda _: self._update_visibility())
        self.type_menu.grid(row=row, column=1, sticky="w", pady=4)

        self.fields = {}
        self.rows = {}
        specs = (
            ("url", "URL", "https://nas.home.arpa:30036/timemanager", None),
            ("username", "Username", "", None),
            ("password", "Password", "", None),
            ("ca_file", "Certificate file", "empty = publicly trusted certificate", self._browse_certificate),
            ("path", "Folder", "", self._browse_folder),
            ("timeout_seconds", "Timeout (seconds)", "", None),
        )
        for key, label, placeholder, browse in specs:
            row += 1
            text = customtkinter.CTkLabel(self, text=label)
            text.grid(row=row, column=0, sticky="w", padx=(0, 12))
            entry = customtkinter.CTkEntry(self, placeholder_text=placeholder, show="*" if key == "password" else "")
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            widgets = [text, entry]
            if browse:
                button = customtkinter.CTkButton(self, text="Browse...", width=90, command=browse)
                button.grid(row=row, column=2, padx=(8, 0))
                widgets.append(button)
            self.fields[key] = entry
            self.rows[key] = widgets

        row += 1
        buttons = customtkinter.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=row, column=0, columnspan=3, sticky="w", pady=10)
        self.test_button = customtkinter.CTkButton(buttons, text="Test connection", width=150, command=self.test)
        self.test_button.grid(row=0, column=0, padx=(0, 8))
        customtkinter.CTkButton(buttons, text="Save connection", width=150, command=self.save).grid(row=0, column=1)

        row += 1
        self.output = customtkinter.CTkTextbox(self, height=160, wrap="word")
        self.output.grid(row=row, column=0, columnspan=3, sticky="nsew")
        self.grid_rowconfigure(row, weight=1)

        # ----- installation: what the scheduled task / service runs, and folder permissions -----
        row += 1
        customtkinter.CTkLabel(self, text="Installation", font=customtkinter.CTkFont(size=16, weight="bold"),
                               anchor="w").grid(row=row, column=0, columnspan=3, sticky="w", pady=(14, 2))
        row += 1
        customtkinter.CTkLabel(self, text="Scheduled task / service runs").grid(row=row, column=0, sticky="w", padx=(0, 12))
        self.command = customtkinter.CTkEntry(self)
        self.command.insert(0, tracker_command(root))
        self.command.configure(state="readonly")
        self.command.grid(row=row, column=1, sticky="ew", pady=4)
        customtkinter.CTkButton(self, text="Copy", width=90, command=self._copy_command).grid(row=row, column=2, padx=(8, 0))
        row += 1
        self.security = customtkinter.CTkLabel(self, text="", anchor="w", justify="left", wraplength=620)
        self.security.grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
        self.fix_button = customtkinter.CTkButton(self, text="Fix permissions", width=90, command=self._fix_permissions)
        self.fix_button.grid(row=row, column=2, padx=(8, 0))
        self.show(remote)
        self._check_permissions()

    # ----- form <-> settings ---------------------------------------------------------------
    def show(self, remote: RemoteSettings) -> None:
        self.saved = remote
        self.type_menu.set(TYPE_LABELS.get(remote.type, TYPE_LABELS["none"]))
        values = {"url": remote.url, "username": remote.username, "ca_file": remote.ca_file,
                  "path": remote.path, "timeout_seconds": f"{remote.timeout_seconds:g}", "password": ""}
        for key, entry in self.fields.items():
            entry.delete(0, "end")
            if values[key]:
                entry.insert(0, values[key])
        self.fields["password"].configure(
            placeholder_text="(unchanged; type to replace)" if remote.password else "")
        self._update_visibility()

    def _update_visibility(self) -> None:
        kind = LABEL_TYPES[self.type_menu.get()]
        visible = {"webdav": {"url", "username", "password", "ca_file", "timeout_seconds"},
                   "folder": {"path"}, "none": set()}[kind]
        for key, widgets in self.rows.items():
            for widget in widgets:
                if key in visible:
                    widget.grid()
                else:
                    widget.grid_remove()

    def collect(self) -> RemoteSettings:
        kind = LABEL_TYPES[self.type_menu.get()]
        text = {k: e.get().strip() for k, e in self.fields.items()}
        try:
            timeout = float(text["timeout_seconds"] or 5)
        except ValueError:
            timeout = -1  # reported by validate_remote
        password = self.fields["password"].get() or self.saved.password  # blank keeps the saved password
        return RemoteSettings(type=kind, url=text["url"], username=text["username"], password=password,
                              ca_file=text["ca_file"].strip('"'), path=text["path"].strip('"'),
                              timeout_seconds=timeout)

    def _browse_certificate(self):
        name = filedialog.askopenfilename(title="Certificate that verifies the server",
                                          filetypes=[("Certificates", "*.crt *.pem *.cer"), ("All files", "*.*")])
        if name:
            self.fields["ca_file"].delete(0, "end")
            self.fields["ca_file"].insert(0, name)

    def _browse_folder(self):
        name = filedialog.askdirectory(title="Shared folder")
        if name:
            self.fields["path"].delete(0, "end")
            self.fields["path"].insert(0, name)

    # ----- installation ----------------------------------------------------------------------
    def _copy_command(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(tracker_command(self.root))

    def _check_permissions(self) -> None:
        try:
            issues = find_issues(self.root)
        except Exception as e:
            self.security.configure(text=f"Permissions could not be checked: {e}")
            self.fix_button.grid_remove()
            return
        if issues:
            self.security.configure(text="Warning:\n" + "\n".join(f"• {i.message}" for i in issues),
                                    text_color=("#a30000", "#ff7070"))
            self.fix_button.grid()
        else:
            self.security.configure(text="Permissions OK: standard users cannot change the program "
                                         "or read the network password.", text_color=("#1b6e20", "#7bd17f"))
            self.fix_button.grid_remove()

    def _fix_permissions(self) -> None:
        if not messagebox.askyesno(
                "Fix permissions",
                f"Restrict {self.root} so that only SYSTEM and Administrators (root) can change it, and "
                "only they can read instance.toml?\n\nStandard users can still run the configurator, "
                "but it will refuse to work without administrator rights."):
            return
        try:
            remaining = fix_all(self.root)
        except Exception as e:
            messagebox.showerror("Fix permissions", f"Could not change permissions:\n{e}")
            remaining = None
        self._check_permissions()
        if remaining:
            messagebox.showwarning("Fix permissions", "Some problems remain:\n" +
                                   "\n".join(i.message for i in remaining))

    # ----- test ----------------------------------------------------------------------------
    def _write(self, line: str) -> None:
        self.output.insert("end", line + "\n")
        self.output.see("end")

    def test(self) -> None:
        remote = self.collect()
        self.output.delete("1.0", "end")
        errors = validate_remote(remote)
        if errors:
            self._write("Please correct: " + "; ".join(errors))
            return
        if remote.type == "none":
            self._write("This computer only: nothing to test.")
            self.passed_for = remote
            return
        if remote.ca_file and not Path(remote.ca_file).is_file():
            self._write(f"Certificate file not found: {remote.ca_file}")
            return
        self.test_button.configure(state="disabled", text="Testing...")
        self._write(f"Testing {remote.url or remote.path} ...")

        def worker():
            checks = (check_webdav(remote.url, remote.username, remote.password, remote.ca_file,
                                   remote.timeout_seconds)
                      if remote.type == "webdav" else check_folder(remote.path))
            ok_all = True
            for name, ok, detail in checks:
                ok_all &= ok
                self.results.put(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
            self.results.put((ok_all, remote))

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll)

    def _poll(self) -> None:
        while not self.results.empty():
            item = self.results.get()
            if isinstance(item, tuple):
                ok_all, remote = item
                self.passed_for = remote if ok_all else None
                self._write("\nAll checks passed." if ok_all else "\nSome checks failed; see the lines marked FAIL.")
                self.test_button.configure(state="normal", text="Test connection")
                return
            self._write(item)
        self.after(100, self._poll)

    # ----- save ----------------------------------------------------------------------------
    def save(self) -> None:
        remote = self.collect()
        errors = validate_remote(remote)
        if errors:
            messagebox.showerror("Please correct", "\n".join(errors))
            return
        if remote != self.passed_for and not messagebox.askyesno(
                "Not tested", "The connection test has not passed for these settings.\n\n"
                              "Save anyway? Until the store is reachable, the tracker enforces offline limits."):
            return
        try:
            if remote.type == "webdav" and remote.ca_file:
                remote = dataclasses.replace(remote, ca_file=install_certificate(self.root, Path(remote.ca_file)))
            save_remote_settings(self.root, remote)
            instance = load_instance(self.root)
        except (InstanceError, StoreError, OSError) as e:
            messagebox.showerror("Save failed", f"{e}\n\nThe configurator needs administrator (root) rights.")
            return
        try:
            protect_secret_file(instance_path(self.root))  # the file holds the password
        except Exception as e:
            messagebox.showwarning("Saved", f"Connection saved, but instance.toml could not be protected:\n{e}")
        self._check_permissions()
        self.show(instance.remote)
        self._write("\nConnection saved.")
        self.on_saved(instance)
