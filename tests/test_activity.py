"""Shared activity log, per-computer usage and the quick login check."""

import datetime
import json

from configurator.activity import load_day
from core.activity import describe, events_csv, merge_events, parse_events, serialize_events, usage_table, usage_csv
from core.usage import DailyRecord
from tests.test_tracker import DAY, FlakyStore, make, sam, CONFIG  # noqa: F401  (fixtures and helpers)
from core.config import serialize_config
from tracker.sync import CONFIG_KEY, events_key

import pytest

NOW = datetime.datetime(2026, 10, 26, 12, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture
def nas(tmp_path):
    store = FlakyStore(tmp_path / "nas")
    store.put(CONFIG_KEY, serialize_config(CONFIG))
    return store


# ----- pure logic -----------------------------------------------------------------------------
def test_parse_events_keeps_valid_lines_only():
    data = (b'{"time": "2026-10-26T10:00:00+00:00", "event": "session_counted", "person": "sam", "used": 5}\n'
            b'not json\n'
            b'{"time": "yesterday", "event": "x"}\n'
            b'{"time": "2026-10-26T09:00:00+00:00", "event": "logged_off", "used": "lots", "evil": {"a": 1}}\n')
    events = parse_events(data, "w1")
    assert [e["event"] for e in events] == ["session_counted", "logged_off"]
    assert "used" not in events[1] and "evil" not in events[1] and events[1]["writer_id"] == "w1"
    assert parse_events(serialize_events(events)) == [{k: v for k, v in e.items()} for e in events]


def test_merge_and_describe():
    a = [{"time": "2026-10-26T10:00:00+00:00", "event": "session_counted", "person": "sam", "account": "sam.k",
          "used": 5, "limit": 90}]
    b = [{"time": "2026-10-26T11:00:00+02:00", "event": "logged_off", "person": "sam", "reason": "daily_limit",
          "used": 91.4, "limit": 90}]
    merged = merge_events([a, b])
    assert [e["event"] for e in merged] == ["logged_off", "session_counted"]  # 09:00 UTC before 10:00 UTC
    assert describe(merged[0]) == "sam: logged off: daily limit reached (91 of 90 min used)"
    assert describe(merged[1]) == "sam (sam.k): session counted (5 of 90 min used)"
    assert "daily_limit" in events_csv(merged)


def test_usage_table_per_computer():
    pc, laptop = DailyRecord("w1", "d"), DailyRecord("w2", "d")
    pc.credit("sam", 30, NOW)
    laptop.credit("sam.k", 15, NOW)
    laptop.credit("guest", 5, NOW)
    computers, rows = usage_table([pc, laptop], {"w1": "PC (linux)", "w2": "LAPTOP (windows)"},
                                  {"sam": "Sam", "sam.k": "Sam"})
    assert computers == ["LAPTOP (windows)", "PC (linux)"]
    assert rows == [("Sam", {"PC (linux)": 30, "LAPTOP (windows)": 15}, 45),
                    ("guest (not managed)", {"LAPTOP (windows)": 5}, 5)]
    assert usage_csv("2026-10-26", computers, rows).splitlines()[1] == "2026-10-26,Sam,15.0,30.0,45.0"


# ----- tracker writes and shares its journal ---------------------------------------------------
def journal(nas, writer):
    data = nas.get(events_key(writer, DAY.isoformat()), 1_000_000)
    return [e["event"] for e in parse_events(data)] if data else []


def test_events_are_shared_in_the_same_cycle(tmp_path, nas):
    pc, platform, clock = make(tmp_path, "pc", nas, sam())
    pc.run_cycle()
    assert journal(nas, "pc") == ["tracker_started", "session_counted"]
    for _ in range(6):
        clock.advance(5)
        pc.run_cycle()
    assert journal(nas, "pc") == ["tracker_started", "session_counted", "near_limit", "logged_off"]
    logged_off = parse_events(nas.get(events_key("pc", DAY.isoformat()), 1_000_000))[-1]
    assert logged_off["reason"] == "daily_limit" and logged_off["used"] == 30 and logged_off["limit"] == 30


def test_offline_events_are_uploaded_later(tmp_path, nas):
    pc, _, clock = make(tmp_path, "pc", nas, sam())
    pc.run_cycle()
    nas.online = False
    clock.advance(5)
    pc.run_cycle()
    nas.online = True
    clock.advance(5)
    pc.run_cycle()
    assert journal(nas, "pc")[-2:] == ["offline", "online"]


def test_activity_tab_loads_all_computers(tmp_path, nas):
    pc, _, pc_clock = make(tmp_path, "pc", nas, sam())
    laptop, _, laptop_clock = make(tmp_path, "laptop", nas, sam(account="sam.k"))
    pc.run_cycle()
    laptop_clock.advance(1)
    laptop.run_cycle()
    nas.put("writers/pc.json", json.dumps({"label": "PC (linux)"}).encode())
    records, events, labels = load_day(nas, DAY.isoformat())
    assert {r.writer_id for r in records} == {"pc", "laptop"}
    assert [e["event"] for e in events].count("session_counted") == 2
    assert labels["pc"] == "PC (linux)"


# ----- quick login check -----------------------------------------------------------------------
def test_quick_check_logs_off_a_new_login_over_the_limit(tmp_path, nas):
    pc, platform, clock = make(tmp_path, "pc", nas)
    laptop, _, laptop_clock = make(tmp_path, "laptop", nas, sam())
    for _ in range(6):                     # 30 min on the laptop: limit reached
        laptop.run_cycle()
        laptop_clock.advance(5)
    pc.run_cycle()                         # nobody on the PC; learns today's usage
    platform.sessions = [sam()]            # Sam logs in on the PC between cycles
    result = pc.quick_check()
    assert result.logged_off and "checked at login" in result.logged_off[0][1]
    assert journal(nas, "pc")[-1] == "logged_off"


def test_quick_check_leaves_counted_sessions_to_the_full_cycle(tmp_path, nas):
    pc, platform, clock = make(tmp_path, "pc", nas, sam())
    pc.run_cycle()                         # Sam is being counted, 5 of 30
    assert pc.quick_check().logged_off == []
    clock.now = clock.now.replace(hour=22)  # past latest login, but a counted session waits for the cycle
    assert pc.quick_check().logged_off == []


def test_quick_check_outside_hours(tmp_path, nas):
    pc, platform, clock = make(tmp_path, "pc", nas)
    pc.run_cycle()
    clock.now = clock.now.replace(hour=22)
    platform.sessions = [sam()]
    result = pc.quick_check()
    assert result.logged_off and "login hours" in result.logged_off[0][1]
