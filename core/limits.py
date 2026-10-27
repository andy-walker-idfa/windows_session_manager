"""Resolve the limits that apply to a person on a given day."""

import datetime

from core.config import DAYS, LIMIT_KEYS

NO_LIMITS = {"limit_minutes": 1440, "earliest_login": "00:00", "latest_login": "23:59"}


def day_type(day: datetime.date) -> str:
    return "weekend" if day.weekday() >= 5 else "weekday"


def default_limits(config: dict, day: datetime.date) -> dict:
    return dict(config.get("defaults", {}).get(day_type(day), {}))


def resolve_limits(config: dict, person: str, day: datetime.date) -> dict:
    """Most specific wins, per key: user day override > user day type > global defaults.

    Keys not set anywhere fall back to NO_LIMITS, so the result always holds all three keys.
    """
    limits = dict(NO_LIMITS)
    limits.update(default_limits(config, day))
    user = config.get("users", {}).get(person) or {}
    for layer in (user.get(day_type(day), {}), user.get("day_overrides", {}).get(DAYS[day.weekday()], {})):
        limits.update({k: v for k, v in layer.items() if k in LIMIT_KEYS})
    return limits


def stricter(a: dict, b: dict) -> dict:
    """Combine two complete limit sets so that the stricter value wins for every key."""
    return {
        "limit_minutes": min(a["limit_minutes"], b["limit_minutes"]),
        "earliest_login": max(a["earliest_login"], b["earliest_login"]),
        "latest_login": min(a["latest_login"], b["latest_login"]),
    }


def resolve_offline_limits(config: dict, person: str, day: datetime.date) -> dict:
    """Limits while the network store is unreachable: the user's own limits combined with the
    global defaults, stricter value wins."""
    fallback = dict(NO_LIMITS)
    fallback.update(default_limits(config, day))
    return stricter(resolve_limits(config, person, day), fallback)
