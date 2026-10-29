"""Activity tab: usage per computer and the combined activity log of all computers, per day."""

import datetime
import json
import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter

from core.activity import (MAX_EVENTS_BYTES, describe, events_csv, local_time, merge_events, parse_events,
                           usage_csv, usage_table)
from core.config import build_account_index
from core.limits import resolve_limits
from core.usage import MAX_RECORD_BYTES, RecordError, parse_record
from storage.base import Store, StoreError
from tracker.sync import events_key, record_key


def load_day(store: Store, date: str):
    """Usage records, event journals and computer names of one day, from every installation."""
    writers = set()
    for prefix in ("records", "events"):
        writers.update(store.list(prefix))
    labels = {}
    for name in store.list("writers"):
        writer = name.removesuffix(".json")
        try:
            info = json.loads(store.get(f"writers/{name}", 64 * 1024) or b"{}")
            if isinstance(info.get("label"), str):
                labels[writer] = info["label"]
        except (StoreError, ValueError):
            pass
    records, journals = [], []
    for writer in sorted(writers):
        try:
            data = store.get(record_key(writer, date), MAX_RECORD_BYTES)
            if data:
                records.append(parse_record(data, writer, date))
        except (StoreError, ValueError, RecordError):
            pass  # an unreadable file of one computer must not hide the others
        try:
            data = store.get(events_key(writer, date), MAX_EVENTS_BYTES)
            if data:
                journal = parse_events(data, writer)
                for event in journal:
                    event.setdefault("computer", labels.get(writer, writer[:8]))
                journals.append(journal)
        except (StoreError, ValueError):
            pass
    return records, merge_events(journals), labels


class ActivityFrame(customtkinter.CTkFrame):
    def __init__(self, master, get_store, get_config):
        super().__init__(master, fg_color="transparent")
        self.get_store = get_store
        self.get_config = get_config
        self.results: queue.Queue = queue.Queue()
        self.loaded = None  # (date, computers, rows, events)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        mono = customtkinter.CTkFont(family="Courier", size=13)

        bar = customtkinter.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="w", pady=(4, 6))
        customtkinter.CTkLabel(bar, text="Day").grid(row=0, column=0, padx=(0, 6))
        self.date = customtkinter.CTkEntry(bar, width=110)
        self.date.grid(row=0, column=1)
        self.date.bind("<Return>", lambda _: self.load())
        for col, (text, days) in enumerate((("◀", -1), ("Today", 0), ("▶", 1)), start=2):
            customtkinter.CTkButton(bar, text=text, width=60 if days == 0 else 34,
                                    command=lambda d=days: self.shift(d)).grid(row=0, column=col, padx=3)
        customtkinter.CTkButton(bar, text="Refresh", width=80, command=self.load).grid(row=0, column=5, padx=(10, 3))
        customtkinter.CTkButton(bar, text="Export CSV...", width=110, command=self.export).grid(row=0, column=6, padx=3)

        self.status = customtkinter.CTkLabel(self, text="", anchor="w")
        self.status.grid(row=1, column=0, sticky="w")
        customtkinter.CTkLabel(self, text="Minutes per computer", anchor="w",
                               font=customtkinter.CTkFont(weight="bold")).grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.usage = customtkinter.CTkTextbox(self, height=130, font=mono, wrap="none")
        self.usage.grid(row=3, column=0, sticky="ew")
        timeline_label = customtkinter.CTkLabel(self, text="Activity on all computers (local time)", anchor="w",
                                                font=customtkinter.CTkFont(weight="bold"))
        timeline_label.grid(row=4, column=0, sticky="nw", pady=(10, 0))
        self.timeline = customtkinter.CTkTextbox(self, font=mono, wrap="none")
        self.timeline.grid(row=5, column=0, sticky="nsew")
        self.grid_rowconfigure(5, weight=1)
        self.date.insert(0, datetime.date.today().isoformat())

    # ----- loading -------------------------------------------------------------------------
    def shift(self, days: int) -> None:
        try:
            day = datetime.date.fromisoformat(self.date.get().strip())
        except ValueError:
            day = datetime.date.today()
        day = datetime.date.today() if days == 0 else day + datetime.timedelta(days=days)
        self.date.delete(0, "end")
        self.date.insert(0, day.isoformat())
        self.load()

    def load(self) -> None:
        try:
            date = datetime.date.fromisoformat(self.date.get().strip()).isoformat()
        except ValueError:
            self.status.configure(text="Enter the day as YYYY-MM-DD.")
            return
        store = self.get_store()
        self.status.configure(text=f"Loading {date} ...")

        def worker():
            try:
                self.results.put((date, load_day(store, date), None))
            except Exception as e:
                self.results.put((date, None, e))

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll)

    def _poll(self) -> None:
        if self.results.empty():
            self.after(100, self._poll)
            return
        date, loaded, error = self.results.get()
        if error is not None:
            self.status.configure(text=f"Could not load {date}: {error}")
            return
        self._show(date, *loaded)

    def _show(self, date: str, records, events, labels) -> None:
        config = self.get_config() or {}
        index = build_account_index(config)
        computers, rows = usage_table(records, labels, index)
        self.loaded = (date, computers, rows, events)

        day = datetime.date.fromisoformat(date)
        person_w = max([len("Person")] + [len(r[0]) for r in rows]) + 2
        widths = [max(len(c), 6) + 2 for c in computers]
        lines = ["Person".ljust(person_w) + "".join(c.ljust(w) for c, w in zip(computers, widths)) + "Total   Limit"]
        for person, cells, total in rows:
            try:
                limit = str(resolve_limits(config, person, day)["limit_minutes"]) if person in config.get("users", {}) else ""
            except Exception:
                limit = ""
            lines.append(person.ljust(person_w)
                         + "".join((f"{cells[c]:.0f}" if c in cells else "-").ljust(w) for c, w in zip(computers, widths))
                         + f"{total:.0f}".ljust(8) + limit)
        if not rows:
            lines.append("(no usage recorded on this day)")
        self._set_text(self.usage, "\n".join(lines))

        computer_w = max([8] + [len(e.get("computer", "")) for e in events]) + 2
        timeline = [f"{local_time(e):%H:%M:%S}  {e.get('computer', '').ljust(computer_w)}{describe(e)}" for e in events]
        self._set_text(self.timeline, "\n".join(timeline) or "(no events recorded on this day)")
        self.status.configure(text=f"{date}: {len(computers)} computer(s), {len(events)} event(s).")

    @staticmethod
    def _set_text(box, text: str) -> None:
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")

    # ----- export --------------------------------------------------------------------------
    def export(self) -> None:
        if not self.loaded:
            messagebox.showinfo("Export", "Load a day first.")
            return
        date, computers, rows, events = self.loaded
        name = filedialog.asksaveasfilename(title="Export activity", defaultextension=".csv",
                                            initialfile=f"time-manager-{date}-activity.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not name:
            return
        activity = Path(name)
        usage = activity.with_name(activity.stem.removesuffix("-activity") + "-usage.csv")
        try:
            # utf-8-sig so that Excel recognises the encoding
            activity.write_text(events_csv(events), encoding="utf-8-sig", newline="")
            usage.write_text(usage_csv(date, computers, rows), encoding="utf-8-sig", newline="")
        except OSError as e:
            messagebox.showerror("Export", f"Could not write the files:\n{e}")
            return
        messagebox.showinfo("Export", f"Saved:\n{activity}\n{usage}")
