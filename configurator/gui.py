"""Configurator window. Edits the shared config in memory and saves it through ConfigSession.

Blank fields inherit: a person's weekday/weekend values fall back to the defaults, a day override
falls back to the person's weekday/weekend values.
"""

import copy
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter

from configurator.activity import ActivityFrame
from configurator.connection import ConnectionFrame
from configurator.session import ConfigSession, RevisionConflict
from core.config import DAYS, DEFAULT_SETTINGS, LOG_LEVELS, ConfigError, parse_config, validate_config
from storage.base import StoreError

FIELDS = (("limit_minutes", "Max minutes"), ("earliest_login", "Earliest login"), ("latest_login", "Latest login"))


def _to_value(key: str, text: str):
    text = text.strip()
    if key == "limit_minutes" and text.isdigit():
        return int(text)
    return text


class LimitsRow:
    """The three entries of one row in a LimitsTable; get() returns only the filled in values."""

    def __init__(self, entries: dict):
        self.entries = entries

    def set(self, limits: dict | None) -> None:
        for key, entry in self.entries.items():
            entry.delete(0, "end")
            value = (limits or {}).get(key)
            if value is not None:
                entry.insert(0, str(value))

    def get(self) -> dict:
        return {k: _to_value(k, e.get()) for k, e in self.entries.items() if e.get().strip()}


class LimitsTable(customtkinter.CTkFrame):
    """Rows of limits in one grid, so labels and columns line up whatever the font size."""

    def __init__(self, master, rows: list[tuple[str, str]]):
        super().__init__(master, fg_color="transparent")
        for col, (_, header) in enumerate(FIELDS, start=1):
            customtkinter.CTkLabel(self, text=header, anchor="w").grid(row=0, column=col, padx=4, sticky="w")
        self.rows: dict[str, LimitsRow] = {}
        for r, (name, title) in enumerate(rows, start=1):
            customtkinter.CTkLabel(self, text=title, anchor="w").grid(row=r, column=0, padx=(0, 10), sticky="w")
            entries = {}
            for col, (key, _) in enumerate(FIELDS, start=1):
                entry = customtkinter.CTkEntry(self, width=110, corner_radius=4, border_width=1)
                entry.grid(row=r, column=col, padx=4, pady=2, sticky="w")
                entries[key] = entry
            self.rows[name] = LimitsRow(entries)


class PersonEditor(customtkinter.CTkScrollableFrame):
    def __init__(self, master):
        super().__init__(master)
        self.grid_columnconfigure(0, weight=1)
        self.title = customtkinter.CTkLabel(self, text="Select or add a person",
                                            font=customtkinter.CTkFont(size=18, weight="bold"))
        self.title.grid(row=0, column=0, sticky="w", pady=(0, 8))
        customtkinter.CTkLabel(self, text="Other account names (comma separated), if they differ between computers:",
                               anchor="w").grid(row=1, column=0, sticky="w")
        self.accounts = customtkinter.CTkEntry(self)
        self.accounts.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        customtkinter.CTkLabel(self, text="Blank fields use the defaults.", anchor="w").grid(row=3, column=0, sticky="w")
        base = LimitsTable(self, [("weekday", "Weekday"), ("weekend", "Weekend")])
        base.grid(row=4, column=0, sticky="w", pady=(0, 12))
        self.weekday, self.weekend = base.rows["weekday"], base.rows["weekend"]
        customtkinter.CTkLabel(self, text="Day overrides (blank fields use weekday/weekend values):",
                               anchor="w").grid(row=6, column=0, sticky="w")
        days = LimitsTable(self, [(day, day.capitalize()) for day in DAYS])
        days.grid(row=7, column=0, sticky="w")
        self.days = days.rows
        self.person = None
        self._set_enabled(False)

    def _set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        widgets = [self.accounts] + [e for row in (self.weekday, self.weekend, *self.days.values())
                                     for e in row.entries.values()]
        for widget in widgets:
            widget.configure(state=state)

    def show(self, person: str | None, entry: dict | None) -> None:
        self.person = person
        self._set_enabled(True)
        self.title.configure(text=person or "Select or add a person")
        entry = entry or {}
        self.accounts.delete(0, "end")
        self.accounts.insert(0, ", ".join(entry.get("accounts", [])))
        self.weekday.set(entry.get("weekday"))
        self.weekend.set(entry.get("weekend"))
        overrides = entry.get("day_overrides", {})
        for day, row in self.days.items():
            row.set(overrides.get(day))
        if person is None:
            self._set_enabled(False)

    def collect(self) -> dict:
        entry = {}
        accounts = [a.strip() for a in self.accounts.get().split(",") if a.strip()]
        if accounts:
            entry["accounts"] = accounts
        for name, row in (("weekday", self.weekday), ("weekend", self.weekend)):
            limits = row.get()
            if limits:
                entry[name] = limits
        overrides = {day: row.get() for day, row in self.days.items() if row.get()}
        if overrides:
            entry["day_overrides"] = overrides
        return entry


class ConfiguratorApp(customtkinter.CTk):
    def __init__(self, instance, local_accounts: list[str], app_title: str, startup_warning: str = ""):
        super().__init__()
        self.session = ConfigSession(instance)
        self.local_accounts = local_accounts
        self.config_data: dict = {}
        self.limits_loaded = False
        self.title(app_title)
        self.geometry("820x760")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.status = customtkinter.CTkLabel(self, text="", anchor="w")
        self.status.grid(row=0, column=0, padx=16, pady=(12, 0), sticky="ew")

        self.tabs = tabs = customtkinter.CTkTabview(self, anchor="nw", command=self._tab_changed)
        tabs.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")
        for name in ("People", "Defaults", "Settings", "Activity", "Connection"):
            tabs.add(name)
        self._build_people(tabs.tab("People"))
        self._build_defaults(tabs.tab("Defaults"))
        self._build_settings(tabs.tab("Settings"))
        activity_tab = tabs.tab("Activity")
        activity_tab.grid_columnconfigure(0, weight=1)
        activity_tab.grid_rowconfigure(0, weight=1)
        self.activity = ActivityFrame(activity_tab, lambda: self.session.store,
                                      lambda: self.config_data if self.limits_loaded else None)
        self.activity.grid(row=0, column=0, sticky="nsew")
        self._activity_loaded = False
        connection_tab = tabs.tab("Connection")
        connection_tab.grid_columnconfigure(0, weight=1)
        connection_tab.grid_rowconfigure(0, weight=1)
        self.connection = ConnectionFrame(connection_tab, instance.root, instance.remote, self.on_connection_saved)
        self.connection.grid(row=0, column=0, sticky="nsew")

        # Reload / Save limits apply to the limit tabs; the Connection tab has its own buttons.
        self.limit_buttons = customtkinter.CTkFrame(self, fg_color="transparent")
        self.limit_buttons.grid(row=2, column=0, pady=(0, 12))
        customtkinter.CTkButton(self.limit_buttons, text="Reload", width=110,
                                command=self.reload).grid(row=0, column=0, padx=8)
        customtkinter.CTkButton(self.limit_buttons, text="Save limits", width=110,
                                command=self.save).grid(row=0, column=1, padx=8)
        customtkinter.CTkButton(self.limit_buttons, text="Import from file...", width=140,
                                command=self.import_file).grid(row=0, column=2, padx=8)
        if startup_warning:
            self.after(200, lambda: messagebox.showwarning("Connection settings", startup_warning))
        self.after(50, self.reload)

    def _tab_changed(self):
        # Reload / Save limits only belong to the tabs that edit limits.
        if self.tabs.get() in ("Connection", "Activity"):
            self.limit_buttons.grid_remove()
        else:
            self.limit_buttons.grid()
        if self.tabs.get() == "Activity" and not self._activity_loaded:
            self._activity_loaded = True  # load today's activity the first time the tab is opened
            self.activity.load()

    def on_connection_saved(self, instance):
        self.session = ConfigSession(instance)
        self._activity_loaded = False  # a new store has other activity
        self.reload(quiet=True)
        if self.limits_loaded and self.session.store_is_empty and messagebox.askyesno(
                "Empty network store",
                "The network store has no limits yet.\n\nUpload this computer's current limits to it?"):
            self.save()

    # ----- tabs ----------------------------------------------------------------------------
    def _build_people(self, tab):
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        left = customtkinter.CTkFrame(tab)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        left.grid_rowconfigure(0, weight=1)
        self.people_list = customtkinter.CTkScrollableFrame(left, width=180)
        self.people_list.grid(row=0, column=0, sticky="ns", padx=6, pady=6)
        self.new_person = customtkinter.CTkEntry(left, placeholder_text="New person name")
        self.new_person.grid(row=1, column=0, sticky="ew", padx=6, pady=2)
        customtkinter.CTkButton(left, text="Add person", command=self.add_person).grid(row=2, column=0, sticky="ew", padx=6, pady=2)
        self.account_choice = customtkinter.CTkOptionMenu(left, values=["Add local account..."],
                                                          command=self.add_local_account)
        self.account_choice.grid(row=3, column=0, sticky="ew", padx=6, pady=2)
        customtkinter.CTkButton(left, text="Remove selected", fg_color="#a33", hover_color="#822",
                                command=self.remove_person).grid(row=4, column=0, sticky="ew", padx=6, pady=(2, 6))
        self.editor = PersonEditor(tab)
        self.editor.grid(row=0, column=1, sticky="nsew")

    def _build_defaults(self, tab):
        customtkinter.CTkLabel(tab, text="These limits apply to every person unless overridden. "
                                         "They are also the offline limits.", anchor="w").grid(row=0, column=0, sticky="w", pady=(4, 12))
        table = LimitsTable(tab, [("weekday", "Weekday"), ("weekend", "Weekend")])
        table.grid(row=1, column=0, sticky="w")
        self.default_rows = table.rows

    def _build_settings(self, tab):
        labels = (("check_interval_minutes", "Check interval (minutes, 1-60)"),
                  ("retention_days", "Keep usage history (days)"))
        self.setting_entries = {}
        for i, (key, text) in enumerate(labels):
            customtkinter.CTkLabel(tab, text=text, anchor="w").grid(row=i, column=0, sticky="w", pady=4, padx=(0, 12))
            entry = customtkinter.CTkEntry(tab, width=100)
            entry.grid(row=i, column=1, sticky="w")
            self.setting_entries[key] = entry
        customtkinter.CTkLabel(tab, text="Log level", anchor="w").grid(row=2, column=0, sticky="w", pady=4)
        self.log_level = customtkinter.CTkOptionMenu(tab, values=list(LOG_LEVELS))
        self.log_level.grid(row=2, column=1, sticky="w")

    # ----- people list ---------------------------------------------------------------------
    def _refresh_people(self):
        for child in self.people_list.winfo_children():
            child.destroy()
        for i, person in enumerate(sorted(self.config_data.get("users", {}))):
            selected = person == self.editor.person
            customtkinter.CTkButton(self.people_list, text=person, anchor="w",
                                    fg_color=None if selected else "transparent",
                                    # unselected names: normal text colour (white text vanished in light mode)
                                    text_color=None if selected else ("gray10", "gray90"),
                                    hover_color=None if selected else ("gray75", "gray30"),
                                    command=lambda p=person: self.select_person(p)).grid(row=i, column=0, sticky="ew", pady=1)
        mapped = {a.casefold() for p, e in self.config_data.get("users", {}).items()
                  for a in [p, *e.get("accounts", [])]}
        choices = [a for a in self.local_accounts if a.casefold() not in mapped]
        self.account_choice.configure(values=["Add local account..."] + choices)
        self.account_choice.set("Add local account...")

    def _commit_editor(self):
        if self.editor.person is not None and self.editor.person in self.config_data.get("users", {}):
            self.config_data["users"][self.editor.person] = self.editor.collect()

    def select_person(self, person: str | None):
        self._commit_editor()
        self.editor.show(person, self.config_data.get("users", {}).get(person) if person else None)
        self._refresh_people()

    def _add(self, name: str):
        name = name.strip()
        if not name:
            return
        users = self.config_data.setdefault("users", {})
        if name.casefold() in {p.casefold() for p in users}:
            messagebox.showwarning("Already exists", f"'{name}' is already in the list.")
            return
        self._commit_editor()
        users[name] = {}
        self.select_person(name)

    def add_person(self):
        self._add(self.new_person.get())
        self.new_person.delete(0, "end")

    def add_local_account(self, choice: str):
        if choice != "Add local account...":
            self._add(choice)

    def remove_person(self):
        person = self.editor.person
        if person and messagebox.askyesno("Remove person", f"Stop managing '{person}'?"):
            self.config_data["users"].pop(person, None)
            self.editor.person = None
            self.select_person(None)

    # ----- load / save ---------------------------------------------------------------------
    def reload(self, quiet: bool = False):
        self.limits_loaded = False
        try:
            self.config_data = self.session.load()
        except StoreError as e:
            self.status.configure(text=f"Not connected: {self.session.describe()}  (see the Connection tab)")
            self.tabs.set("Connection")
            self._tab_changed()
            if not quiet:
                messagebox.showerror("Network store unreachable",
                                     f"Cannot load the limits:\n{e}\n\nCheck the settings on the Connection tab.")
            return
        except ConfigError as e:
            self.status.configure(text=f"Invalid configuration in {self.session.describe()}")
            messagebox.showerror("Invalid configuration", f"The stored configuration is invalid:\n{e}")
            return
        self.limits_loaded = True
        revision = self.session.loaded_revision
        self.status.configure(text=f"Store: {self.session.describe()}   |   revision: "
                                   f"{revision if revision is not None else 'none yet'}")
        self._show_loaded()

    def _show_loaded(self):
        """Fill every limits tab from self.config_data."""
        for name, row in self.default_rows.items():
            row.set(self.config_data.get("defaults", {}).get(name))
        settings = {**DEFAULT_SETTINGS, **self.config_data.get("settings", {})}
        for key, entry in self.setting_entries.items():
            entry.delete(0, "end")
            entry.insert(0, str(settings[key]))
        self.log_level.set(settings["log_level"])
        self.editor.person = None
        self.select_person(None)

    def import_file(self):
        """Load limits from a limits.toml (also from version 1.x) into the window; Save stores them."""
        if not self.limits_loaded:
            messagebox.showwarning("Not loaded", "Fix the connection and reload first, so the import can be saved.")
            return
        name = filedialog.askopenfilename(title="Import limits", filetypes=[("Limits", "*.toml"), ("All files", "*.*")])
        if not name:
            return
        try:
            imported = parse_config(Path(name).read_bytes())
        except (OSError, ConfigError) as e:
            messagebox.showerror("Import failed", f"{name} cannot be used:\n{e}")
            return
        imported["revision"] = self.config_data.get("revision", 0)
        self.config_data = imported
        self._show_loaded()
        messagebox.showinfo("Imported", f"Limits loaded from {Path(name).name}. Check them, then press Save limits.")

    def _collect(self) -> dict:
        self._commit_editor()
        config = copy.deepcopy(self.config_data)
        config["defaults"] = {n: r.get() for n, r in self.default_rows.items() if r.get()}
        settings = {}
        for key, entry in self.setting_entries.items():
            text = entry.get().strip()
            value = int(text) if text.isdigit() else text
            if value != DEFAULT_SETTINGS[key]:
                settings[key] = value
        if self.log_level.get() != DEFAULT_SETTINGS["log_level"]:
            settings["log_level"] = self.log_level.get()
        if settings:
            config["settings"] = settings
        else:
            config.pop("settings", None)
        return config

    def save(self):
        if not self.limits_loaded:
            messagebox.showwarning("Not loaded", "The limits could not be loaded, so they cannot be saved. "
                                                 "Fix the connection first, then press Reload.")
            return
        config = self._collect()
        errors = validate_config(config)
        if errors:
            messagebox.showerror("Please correct", "\n".join(errors[:15]))
            return
        try:
            revision = self.session.save(config)
        except RevisionConflict as e:
            messagebox.showwarning("Changed elsewhere", str(e))
            return
        except (StoreError, ConfigError) as e:
            messagebox.showerror("Save failed", str(e))
            return
        self.config_data = config
        self.config_data["revision"] = revision
        self.status.configure(text=f"Store: {self.session.describe()}   |   revision: {revision} (saved)")
        messagebox.showinfo("Saved", f"Configuration saved as revision {revision}. Trackers pick it up "
                                     "within one check interval.")
