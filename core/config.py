"""Shared configuration (limits.toml): normalisation, validation and lookups.

Schema 1 layout:

    schema = 1
    revision = 7

    [settings]                      # optional, built-in defaults apply when missing
    check_interval_minutes = 5
    retention_days = 30
    log_level = "INFO"

    [defaults.weekday]              # and [defaults.weekend]
    limit_minutes = 120
    earliest_login = "08:00"
    latest_login = "21:00"

    [users.sam]                    # a person
    accounts = ["sam.k"]           # optional extra account names
    [users.sam.weekday]            # optional, same keys as defaults
    [users.sam.day_overrides.monday]
"""

import re
import tomllib

import tomli_w

CONFIG_SCHEMA = 1
LIMIT_KEYS = ("limit_minutes", "earliest_login", "latest_login")
DAY_TYPES = ("weekday", "weekend")
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MAX_CONFIG_BYTES = 256 * 1024

DEFAULT_SETTINGS = {
    "check_interval_minutes": 5,
    "retention_days": 30,
    "log_level": "INFO",
}
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")

_TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_DAY_ALIASES = {d[:3]: d for d in DAYS} | {d: d for d in DAYS}
# Keys written by the 1.x configurator that carry no meaning for the tracker.
_LEGACY_IGNORED_KEYS = {"Configuration level"}


class ConfigError(ValueError):
    """Raised when a configuration cannot be parsed or fails validation."""


def normalize_account(name: str) -> str:
    return name.strip().casefold()


def _normalize_limits(raw) -> dict:
    """Drop empty values and turn numeric strings into ints (1.x GUI leftovers)."""
    if not isinstance(raw, dict):
        return raw
    limits = {}
    for key, value in raw.items():
        if value == "" or value is None:
            continue
        if key == "limit_minutes" and isinstance(value, str) and value.strip().isdigit():
            value = int(value)
        limits[key] = value
    return limits


def _normalize_day_overrides(raw) -> dict:
    if not isinstance(raw, dict):
        return raw
    overrides = {}
    for day, limits in raw.items():
        day_name = _DAY_ALIASES.get(str(day).strip().lower(), day)
        limits = _normalize_limits(limits)
        if limits:
            overrides[day_name] = limits
    return overrides


def normalize_config(raw: dict) -> dict:
    """Bring a 1.x or schema 1 config into canonical schema 1 form.

    1.x quirks handled here: no schema/revision fields, day overrides keyed by "mon".."sun",
    a "Per-day overrides" table with "Monday".."Sunday", a "Configuration level" marker and empty
    strings for fields left blank.
    """
    config = {
        "schema": raw.get("schema", CONFIG_SCHEMA),
        "revision": raw.get("revision", 0),
    }
    if "settings" in raw:
        config["settings"] = dict(raw["settings"]) if isinstance(raw["settings"], dict) else raw["settings"]

    defaults = raw.get("defaults", {})
    if isinstance(defaults, dict):
        config["defaults"] = {k: _normalize_limits(v) for k, v in defaults.items() if _normalize_limits(v) != {}}
    else:
        config["defaults"] = defaults

    users = {}
    raw_users = raw.get("users", {})
    if not isinstance(raw_users, dict):
        config["users"] = raw_users
        return config
    for person, entry in raw_users.items():
        if not isinstance(entry, dict):
            users[person] = entry
            continue
        user = {}
        for key, value in entry.items():
            if key in _LEGACY_IGNORED_KEYS:
                continue
            if key in DAY_TYPES:
                limits = _normalize_limits(value)
                if limits:
                    user[key] = limits
            elif key in ("day_overrides", "Per-day overrides"):
                merged = user.get("day_overrides", {})
                merged.update(_normalize_day_overrides(value))
                if merged:
                    user["day_overrides"] = merged
            else:
                user[key] = value
        users[person] = user
    config["users"] = users
    return config


def _validate_limits(limits, where: str, errors: list) -> None:
    if not isinstance(limits, dict):
        errors.append(f"{where}: expected a table")
        return
    for key, value in limits.items():
        if key not in LIMIT_KEYS:
            errors.append(f"{where}: unknown key '{key}'")
        elif key == "limit_minutes":
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 1440:
                errors.append(f"{where}.limit_minutes: must be a whole number 0-1440")
        elif not isinstance(value, str) or not _TIME_RE.match(value):
            errors.append(f"{where}.{key}: must be HH:MM (00:00-23:59)")


def validate_config(config: dict) -> list[str]:
    """Return a list of human readable problems; an empty list means the config is valid.

    Expects a normalised config (see normalize_config).
    """
    errors = []
    schema = config.get("schema")
    if not isinstance(schema, int) or isinstance(schema, bool):
        errors.append("schema: must be a whole number")
    elif schema > CONFIG_SCHEMA:
        errors.append(f"schema: version {schema} is newer than supported version {CONFIG_SCHEMA}")
    revision = config.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        errors.append("revision: must be a whole number >= 0")

    settings = config.get("settings", {})
    if not isinstance(settings, dict):
        errors.append("settings: expected a table")
    else:
        for key, value in settings.items():
            if key not in DEFAULT_SETTINGS:
                errors.append(f"settings: unknown key '{key}'")
            elif key == "check_interval_minutes" and not (isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 60):
                errors.append("settings.check_interval_minutes: must be 1-60")
            elif key == "retention_days" and not (isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 3650):
                errors.append("settings.retention_days: must be 1-3650")
            elif key == "log_level" and value not in LOG_LEVELS:
                errors.append(f"settings.log_level: must be one of {', '.join(LOG_LEVELS)}")

    defaults = config.get("defaults", {})
    if not isinstance(defaults, dict):
        errors.append("defaults: expected a table")
    else:
        for key, value in defaults.items():
            if key not in DAY_TYPES:
                errors.append(f"defaults: unknown key '{key}'")
            else:
                _validate_limits(value, f"defaults.{key}", errors)

    users = config.get("users", {})
    if not isinstance(users, dict):
        errors.append("users: expected a table")
        return errors
    seen_accounts = {}
    for person, entry in users.items():
        where = f"users.{person}"
        if not isinstance(entry, dict):
            errors.append(f"{where}: expected a table")
            continue
        for key, value in entry.items():
            if key in DAY_TYPES:
                _validate_limits(value, f"{where}.{key}", errors)
            elif key == "day_overrides":
                if not isinstance(value, dict):
                    errors.append(f"{where}.day_overrides: expected a table")
                    continue
                for day, limits in value.items():
                    if day not in DAYS:
                        errors.append(f"{where}.day_overrides: unknown day '{day}'")
                    else:
                        _validate_limits(limits, f"{where}.day_overrides.{day}", errors)
            elif key == "accounts":
                if not isinstance(value, list) or not all(isinstance(a, str) and a.strip() for a in value):
                    errors.append(f"{where}.accounts: must be a list of account names")
            else:
                errors.append(f"{where}: unknown key '{key}'")
        # One account may belong to only one person, otherwise usage would be counted twice.
        for account in account_names(person, entry):
            if account in seen_accounts and seen_accounts[account] != person:
                errors.append(f"{where}: account '{account}' already belongs to '{seen_accounts[account]}'")
            seen_accounts[account] = person
    return errors


def parse_config(data: bytes) -> dict:
    """Parse, normalise and validate limits.toml content. Raises ConfigError."""
    if len(data) > MAX_CONFIG_BYTES:
        raise ConfigError(f"config is larger than {MAX_CONFIG_BYTES} bytes")
    try:
        raw = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"config is not valid TOML: {e}") from e
    config = normalize_config(raw)
    errors = validate_config(config)
    if errors:
        raise ConfigError("; ".join(errors))
    return config


def serialize_config(config: dict) -> bytes:
    errors = validate_config(config)
    if errors:
        raise ConfigError("; ".join(errors))
    return tomli_w.dumps(config).encode("utf-8")


def get_settings(config: dict) -> dict:
    settings = dict(DEFAULT_SETTINGS)
    settings.update(config.get("settings", {}) or {})
    return settings


def account_names(person: str, entry: dict) -> set[str]:
    names = {normalize_account(person)}
    for alias in entry.get("accounts", []) or []:
        names.add(normalize_account(alias))
    return names


def build_account_index(config: dict) -> dict[str, str]:
    """Map every normalised account name to the person it belongs to."""
    index = {}
    for person, entry in config.get("users", {}).items():
        for account in account_names(person, entry or {}):
            index[account] = person
    return index
