"""Tracker cycle and sync rules, with a fake OS and folder stores standing in for the NAS."""

import datetime
import json

import pytest

from configurator.session import ConfigSession, RevisionConflict
from core.config import serialize_config
from platforms.base import Session
from shared.instance import InstanceSettings, RemoteSettings, WriterIdentity, load_writer_identity
from storage.base import StoreError
from storage.folder import FolderStore
from tracker.cycle import Tracker
from tracker.sync import CONFIG_CACHE_KEY, CONFIG_KEY, Repository, record_key

DAY = datetime.date(2026, 10, 26)  # a Monday
CONFIG = {
    "schema": 1, "revision": 1,
    "defaults": {"weekday": {"limit_minutes": 60, "earliest_login": "08:00", "latest_login": "21:00"}},
    "users": {"Sam": {"accounts": ["sam.k"], "weekday": {"limit_minutes": 30}}},
}


class FakePlatform:
    def __init__(self, *sessions):
        self.sessions = list(sessions)
        self.logged_off = []

    def get_sessions(self):
        return [s for s in self.sessions if s not in self.logged_off]

    def log_off(self, session):
        self.logged_off.append(session)


class FlakyStore(FolderStore):
    """A network store that can be switched off."""
    online = True

    def _check(self):
        if not self.online:
            raise StoreError("network down")

    def get(self, key, max_bytes):
        self._check()
        return super().get(key, max_bytes)

    def put(self, key, data):
        self._check()
        super().put(key, data)

    def list(self, prefix):
        self._check()
        return super().list(prefix)

    def delete(self, key):
        self._check()
        super().delete(key)


class Clock:
    def __init__(self, hour=12, minute=0):
        self.now = datetime.datetime(2026, 10, 26, hour, minute).astimezone()
        self.mono = 1000.0

    def advance(self, minutes):
        self.now += datetime.timedelta(minutes=minutes)
        self.mono += minutes * 60


def make(tmp_path, name, remote, *sessions, clock=None):
    clock = clock or Clock()
    local = FolderStore(tmp_path / name)
    repo = Repository(local, remote, name)
    platform = FakePlatform(*sessions)
    tracker = Tracker(platform, repo, WriterIdentity(name, name), "test",
                      clock=lambda: clock.now, monotonic=lambda: clock.mono)
    return tracker, platform, clock


@pytest.fixture
def nas(tmp_path):
    store = FlakyStore(tmp_path / "nas")
    store.put(CONFIG_KEY, serialize_config(CONFIG))
    return store


def sam(session_id=1, account="Sam", locked=False, active=True):
    return Session(account, session_id, active, locked)


def test_usage_adds_up_across_writers(tmp_path, nas):
    pc, _, pc_clock = make(tmp_path, "pc", nas, sam())
    laptop, laptop_os, laptop_clock = make(tmp_path, "laptop", nas, sam(account="sam.k"))
    for _ in range(3):  # 15 min on the PC
        pc.run_cycle()
        pc_clock.advance(5)
    result = laptop.run_cycle()  # first laptop cycle: 5 min
    assert result.online
    assert result.usage == {"Sam": 20}
    for _ in range(2):
        laptop_clock.advance(5)
        result = laptop.run_cycle()
    assert result.usage == {"Sam": 30}
    assert laptop_os.logged_off and "daily limit" in result.logged_off[0][1]


def test_locked_inactive_and_unmanaged_sessions_are_not_counted(tmp_path, nas):
    tracker, _, _ = make(tmp_path, "pc", nas, sam(locked=True), sam(2, active=False),
                         Session("dad", 3, True, False))
    result = tracker.run_cycle()
    assert result.credited == {} and result.usage == {}
    assert tracker.repo.local.get(record_key("pc", DAY.isoformat()), 10_000) is None


def test_outside_login_hours_logs_off_without_credit(tmp_path, nas):
    tracker, platform, _ = make(tmp_path, "pc", nas, sam(), clock=Clock(hour=7, minute=30))
    result = tracker.run_cycle()
    assert result.credited == {} and platform.logged_off
    assert "login hours" in result.logged_off[0][1]


def test_offline_uses_cache_and_stricter_defaults_then_pushes(tmp_path, nas):
    config = json.loads(json.dumps(CONFIG))
    config["users"]["Sam"]["weekday"] = {"limit_minutes": 200, "latest_login": "23:00"}
    nas.put(CONFIG_KEY, serialize_config(config))
    pc, _, pc_clock = make(tmp_path, "pc", nas, sam())
    pc.run_cycle()                       # online: config cached
    nas.online = False
    pc_clock.advance(5)
    result = pc.run_cycle()
    assert not result.online
    assert result.usage == {"Sam": 10}
    # offline at 22:30: defaults say 21:00 is the latest login, and the stricter value wins
    pc_clock.now = pc_clock.now.replace(hour=22, minute=30)
    pc_clock.advance(5)
    result = pc.run_cycle()
    assert result.logged_off and "login hours" in result.logged_off[0][1]
    nas.online = True
    pc_clock.now = pc_clock.now.replace(hour=12)
    pc_clock.advance(5)
    pc.run_cycle()
    # The 10 offline minutes reach the network once it is back (the session was logged off at 22:30).
    pushed = json.loads(nas.get(record_key("pc", DAY.isoformat()), 10_000))
    assert pushed["accounts"]["sam"]["minutes"] == 10


def test_invalid_shared_config_is_rejected_and_cache_kept(tmp_path, nas):
    pc, _, _ = make(tmp_path, "pc", nas, sam())
    pc.run_cycle()
    nas.put(CONFIG_KEY, b'[defaults.weekday]\nlimit_minutes = "lots"\n')
    config = pc.repo.refresh_config()
    assert config["users"]["Sam"]["weekday"]["limit_minutes"] == 30


def test_seed_config_is_uploaded_to_an_empty_store(tmp_path):
    nas = FlakyStore(tmp_path / "nas")
    seed = tmp_path / "seed.toml"
    seed.write_bytes(serialize_config(CONFIG))
    pc, _, _ = make(tmp_path, "pc", nas, sam())
    pc.repo.import_seed_config(seed)
    pc.run_cycle()
    assert nas.get(CONFIG_KEY, 100_000) == pc.repo.local.get(CONFIG_CACHE_KEY, 100_000)


def test_corrupt_own_record_is_restored_from_network(tmp_path, nas):
    pc, _, clock = make(tmp_path, "pc", nas, sam())
    for _ in range(3):
        pc.run_cycle()
        clock.advance(5)
    key = record_key("pc", DAY.isoformat())
    pc.repo.local.put(key, b"{garbage")
    result = pc.run_cycle()
    assert result.usage == {"Sam": 20}
    assert any(".corrupt-" in p.name for p in (tmp_path / "pc" / "records" / "pc").iterdir())


def test_startup_recovery_takes_the_larger_value(tmp_path, nas):
    pc, _, clock = make(tmp_path, "pc", nas, sam())
    for _ in range(4):
        pc.run_cycle()
        clock.advance(5)
    (tmp_path / "pc" / "records" / "pc" / f"{DAY.isoformat()}.json").unlink()  # lost locally
    restarted, _, _ = make(tmp_path, "pc", nas, sam(), clock=clock)
    assert restarted.run_cycle().usage == {"Sam": 25}


def test_fingerprint_change_creates_new_writer_id(tmp_path):
    local = FolderStore(tmp_path)
    first = load_writer_identity(local, "windows", "machine-a")
    assert load_writer_identity(local, "windows", "machine-a").writer_id == first.writer_id
    assert load_writer_identity(local, "windows", "machine-b").writer_id != first.writer_id


def test_configurator_revision_check(tmp_path, nas):
    instance = InstanceSettings(tmp_path, tmp_path / "admin", tmp_path / "logs",
                                RemoteSettings(type="folder", path=str(nas.root)))
    one, two = ConfigSession(instance), ConfigSession(instance)
    config_one, config_two = one.load(), two.load()
    config_one["users"]["Mia"] = {}
    assert one.save(config_one) == 2
    config_two["users"]["Noa"] = {}
    with pytest.raises(RevisionConflict):
        two.save(config_two)
    assert "Mia" in two.load()["users"]


def test_info_log_tells_the_story_of_a_session(tmp_path, nas, caplog):
    import logging
    caplog.set_level(logging.INFO)
    session = sam()
    pc, platform, clock = make(tmp_path, "pc", nas, session)
    pc.run_cycle()                                   # 5 of 30
    clock.advance(5)
    platform.sessions = [sam(locked=True)]
    pc.run_cycle()                                   # locked: not counted
    clock.advance(5)
    platform.sessions = [session]
    for _ in range(4):                               # 10, 15, 20, 25 -> near the limit at 24+
        pc.run_cycle()
        clock.advance(5)
    pc.run_cycle()                                   # 30: logged off
    clock.advance(5)
    pc.run_cycle()                                   # gone
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO and "Sam" in r.getMessage()
                or "Logged off" in r.getMessage()]
    assert messages == [
        "Sam (sam): session counted on this computer, 5 of 30 min used today.",
        "Sam (sam): screen locked, not counted (5 of 30 min used today).",
        "Sam (sam): session counted on this computer, 10 of 30 min used today.",
        "Sam: 25 of 30 min used, 5 min left today.",
        "Logged off Sam: daily limit of 30 min reached (30 min used today).",
    ]


def test_info_log_reports_network_coming_back(tmp_path, nas, caplog):
    import logging
    caplog.set_level(logging.INFO)
    pc, _, clock = make(tmp_path, "pc", nas)
    pc.run_cycle()
    nas.online = False
    clock.advance(5)
    pc.run_cycle()
    nas.online = True
    clock.advance(5)
    pc.run_cycle()
    text = caplog.text
    assert "Network store unreachable" in text and "Network store reachable again" in text
