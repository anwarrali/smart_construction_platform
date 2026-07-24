"""Canonical calendar-date rules for construction schedules."""

from datetime import date


def inclusive_duration_days(start_date: date, end_date: date) -> int:
    """Return calendar days with both the start and end dates included."""
    if end_date < start_date:
        raise ValueError("End date must be on or after start date")
    return (end_date - start_date).days + 1
