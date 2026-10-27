"""Enforcement rules. Login times are "HH:MM" strings, so plain string comparison is correct."""

import datetime


def outside_login_window(limits: dict, now_local: datetime.datetime) -> bool:
    current = now_local.strftime("%H:%M")
    return current < limits["earliest_login"] or current > limits["latest_login"]


def limit_reached(limits: dict, minutes_used: float) -> bool:
    return minutes_used >= limits["limit_minutes"]
