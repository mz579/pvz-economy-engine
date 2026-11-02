"""P0-B3 data-quality layer: blocking checks and warning records."""

from .rules import DQError, DQResult, RULES, validate

__all__ = ["validate", "DQResult", "DQError", "RULES"]
