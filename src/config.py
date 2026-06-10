"""Franchise and edition definitions.

This is the single place to update each year when new editions release.
`release_date` anchors the model's "days since release" axis. The edition
flagged `is_current = True` is the one the app forecasts.

Release dates are the retail launch dates (US). Search terms are tuned to
match how IsThereAnyDeal / CheapShark name each title.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Edition:
    title: str            # Display name, e.g. "Madden NFL 24"
    release_date: date    # US retail launch
    search_term: str      # What we send to the price APIs
    is_current: bool = False


@dataclass(frozen=True)
class Franchise:
    key: str              # Short id used in the UI selector
    name: str             # Display name
    msrp: float           # Launch price of the standard edition
    editions: list[Edition] = field(default_factory=list)

    @property
    def current_edition(self) -> Edition:
        return next(e for e in self.editions if e.is_current)

    @property
    def past_editions(self) -> list[Edition]:
        return [e for e in self.editions if not e.is_current]


# Key price thresholds the forecast table reports dates for.
PRICE_THRESHOLDS = [49.99, 39.99, 29.99]


FRANCHISES: dict[str, Franchise] = {
    "madden": Franchise(
        key="madden",
        name="Madden NFL",
        msrp=69.99,
        editions=[
            Edition("Madden NFL 22", date(2021, 8, 20), "Madden NFL 22"),
            Edition("Madden NFL 23", date(2022, 8, 19), "Madden NFL 23"),
            Edition("Madden NFL 24", date(2023, 8, 18), "Madden NFL 24"),
            Edition("Madden NFL 25", date(2024, 8, 16), "Madden NFL 25"),
            Edition("Madden NFL 26", date(2025, 8, 14), "Madden NFL 26", is_current=True),
        ],
    ),
    "nba2k": Franchise(
        key="nba2k",
        name="NBA 2K",
        msrp=69.99,
        editions=[
            Edition("NBA 2K22", date(2021, 9, 10), "NBA 2K22"),
            Edition("NBA 2K23", date(2022, 9, 9), "NBA 2K23"),
            Edition("NBA 2K24", date(2023, 9, 8), "NBA 2K24"),
            Edition("NBA 2K25", date(2024, 9, 6), "NBA 2K25"),
            Edition("NBA 2K26", date(2025, 9, 5), "NBA 2K26", is_current=True),
        ],
    ),
}
