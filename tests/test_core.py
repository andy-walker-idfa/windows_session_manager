import datetime

import pytest

from core.config import (ConfigError, build_account_index, get_settings, normalize_config, parse_config,
                         serialize_config, validate_config)
from core.enforcement import limit_reached, outside_login_window
from core.limits import resolve_limits, resolve_offline_limits
from core.usage import (DailyRecord, NewerSchemaError, RecordError, elapsed_credit, parse_record,
                        serialize_record, usage_by_person)

MONDAY = datetime.date(2026, 10, 26)
SATURDAY = datetime.date(2026, 10, 31)

LEGACY_TOML = b'''
[defaults.weekday]
limit_minutes = 360
earliest_login = "06:00"
latest_login = "23:00"

[defaults.weekend]
limit_minutes = 360
earliest_login = "06:00"
latest_login = "23:00"

[users.sam_k]
"Configuration level" = "Custom weekday / weekend"

[users.sam_k.weekday]
limit_minutes = 30
earliest_login = "08:00"
latest_login = "20:00"

[users.sam_k.weekend]
limit_minutes = 120
earliest_login = "12:00"
latest_login = "21:00"

[users.sam_k.day_overrides.mon]
limit_minutes = 45
earliest_login = "16:01"
latest_login = "20:01"
'''


def config(**users):
    return {"schema": 1, "revision": 1,
            "defaults": {"weekday": {"limit_minutes": 120, "earliest_login": "08:00", "latest_login": "21:00"},
                         "weekend": {"limit_minutes": 180}},
            "users": users}


# ----- config ---------------------------------------------------------------------------------
def test_legacy_config_is_normalised_and_day_override_applies():
    cfg = parse_config(LEGACY_TOML)
    assert cfg["schema"] == 1 and cfg["revision"] == 0
    user = cfg["users"]["sam_k"]
    assert "Configuration level" not in user
    assert user["day_overrides"] == {"monday": {"limit_minutes": 45, "earliest_login": "16:01", "latest_login": "20:01"}}
    assert resolve_limits(cfg, "sam_k", MONDAY)["limit_minutes"] == 45


def test_legacy_per_day_overrides_table_with_blank_fields():
    raw = {"users": {"kid": {"Per-day overrides": {"Monday": {"limit_minutes": "60", "earliest_login": ""},
                                                   "Tuesday": {"limit_minutes": ""}}}}}
    cfg = normalize_config(raw)
    assert cfg["users"]["kid"] == {"day_overrides": {"monday": {"limit_minutes": 60}}}
    assert validate_config(cfg) == []


@pytest.mark.parametrize("change, message", [
    (lambda c: c["defaults"]["weekday"].update(limit_minutes=2000), "0-1440"),
    (lambda c: c["defaults"]["weekday"].update(latest_login="24:00"), "HH:MM"),
    (lambda c: c.update(schema=2), "newer"),
    (lambda c: c.update(settings={"check_interval_minutes": 0}), "1-60"),
    (lambda c: c["users"].update(a={"accounts": ["x"]}, b={"accounts": ["X"]}), "already belongs"),
    (lambda c: c["users"].update(a={"bogus": 1}), "unknown key"),
])
def test_validation_errors(change, message):
    cfg = config()
    change(cfg)
    errors = validate_config(cfg)
    assert any(message in e for e in errors), errors


def test_parse_rejects_bad_toml_and_serialize_round_trips():
    with pytest.raises(ConfigError):
        parse_config(b"this is = = not toml")
    cfg = config(sam={"accounts": ["Sam.K"]})
    assert parse_config(serialize_config(cfg)) == cfg


def test_account_index_is_case_insensitive_with_aliases():
    index = build_account_index(config(Sam={"accounts": ["sam.k", "SamK"]}))
    assert index == {"sam": "Sam", "sam.k": "Sam", "samk": "Sam"}


def test_settings_fall_back_to_built_in_defaults():
    assert get_settings({"settings": {"retention_days": 7}}) == {
        "check_interval_minutes": 5, "retention_days": 7, "log_level": "INFO"}


# ----- limits ---------------------------------------------------------------------------------
def test_resolution_chain_per_key():
    cfg = config(kid={"weekday": {"limit_minutes": 90},
                      "day_overrides": {"monday": {"latest_login": "19:00"}}})
    assert resolve_limits(cfg, "kid", MONDAY) == {"limit_minutes": 90, "earliest_login": "08:00", "latest_login": "19:00"}
    assert resolve_limits(cfg, "kid", SATURDAY) == {"limit_minutes": 180, "earliest_login": "00:00", "latest_login": "23:59"}


def test_offline_limits_take_the_stricter_value():
    cfg = config(kid={"weekday": {"limit_minutes": 300, "earliest_login": "07:00", "latest_login": "20:00"}})
    assert resolve_offline_limits(cfg, "kid", MONDAY) == {
        "limit_minutes": 120, "earliest_login": "08:00", "latest_login": "20:00"}


def test_enforcement_rules():
    limits = {"limit_minutes": 60, "earliest_login": "08:00", "latest_login": "21:00"}
    at = lambda h, m: datetime.datetime(2026, 10, 26, h, m)
    assert outside_login_window(limits, at(7, 59))
    assert not outside_login_window(limits, at(21, 0))
    assert outside_login_window(limits, at(21, 1))
    assert limit_reached(limits, 60) and not limit_reached(limits, 59.9)


# ----- usage ----------------------------------------------------------------------------------
NOW = datetime.datetime(2026, 10, 26, 12, 0, tzinfo=datetime.timezone.utc)


def test_record_round_trip_and_credit():
    record = DailyRecord("w1", "2026-10-26")
    record.credit("sam", 5, NOW)
    record.credit("sam", 2.5, NOW)
    record.credit("sam", -3, NOW)  # never subtracts
    parsed = parse_record(serialize_record(record), "w1", "2026-10-26")
    assert parsed.accounts["sam"].minutes == 7.5
    assert parsed.accounts["sam"].last_seen == "2026-10-26T12:00:00+00:00"


@pytest.mark.parametrize("data, error", [
    (b"{not json", RecordError),
    (b'{"schema": 9, "writer_id": "w1", "date": "2026-10-26", "accounts": {}}', NewerSchemaError),
    (b'{"schema": 1, "writer_id": "w2", "date": "2026-10-26", "accounts": {}}', RecordError),
    (b'{"schema": 1, "writer_id": "w1", "date": "2026-10-26", "accounts": {"a": {"minutes": -1}}}', RecordError),
    (b'{"schema": 1, "writer_id": "w1", "date": "2026-10-26", "accounts": {"a": {"minutes": "5"}}}', RecordError),
])
def test_bad_records_are_rejected(data, error):
    with pytest.raises(error):
        parse_record(data, "w1", "2026-10-26")


def test_merge_max_and_usage_sum():
    a = DailyRecord("w1", "d", {})
    a.credit("sam", 10, NOW)
    b = DailyRecord("w1", "d", {})
    b.credit("sam", 25, NOW)
    b.credit("mia", 5, NOW)
    assert a.merge_max(b) and a.accounts["sam"].minutes == 25
    other = DailyRecord("w2", "d")
    other.credit("sam.k", 7, NOW)
    other.credit("stranger", 99, NOW)
    totals = usage_by_person([a, other], {"sam": "Sam", "sam.k": "Sam", "mia": "Mia"})
    assert totals == {"Sam": 32, "Mia": 5}


@pytest.mark.parametrize("now, previous, expected", [
    (1000.0, None, 5.0),          # first cycle credits one interval
    (1000.0, 880.0, 2.0),         # ran early: real elapsed time
    (10000.0, 1000.0, 5.0),       # long gap (sleep): capped
    (1000.0, 2000.0, 0.0),        # impossible negative: nothing
])
def test_elapsed_credit(now, previous, expected):
    assert elapsed_credit(now, previous, 5) == expected
