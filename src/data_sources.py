"""API clients for IsThereAnyDeal (history) and CheapShark (current prices).

These functions are intentionally free of any Streamlit dependency so they can
be tested on their own. Caching is added in app.py via st.cache_data wrappers.

All prices are PC digital-store prices (USD), used as a free proxy for the
depreciation *shape* of the equivalent Xbox titles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

import requests

# Make Python use the operating system's certificate store. This is what makes
# HTTPS work behind security/proxy software that re-signs TLS (common on
# managed Windows machines). Harmless on Streamlit Cloud / Linux.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # pragma: no cover - truststore is best-effort
    pass


ITAD_BASE = "https://api.isthereanydeal.com"
CHEAPSHARK_BASE = "https://www.cheapshark.com/api/1.0"
COUNTRY = "US"
TIMEOUT = 30


class DataSourceError(RuntimeError):
    """Raised when an upstream API fails in a way the UI should surface."""


@dataclass(frozen=True)
class PricePoint:
    """One observed price, expressed as days since the edition's release."""

    days_since_release: int
    price: float


@dataclass(frozen=True)
class CurrentPrice:
    """The cheapest current price for the live edition, plus context."""

    price: float
    store: str
    all_time_low: float | None
    source: str  # "CheapShark" or "IsThereAnyDeal"


# --------------------------------------------------------------------------- #
# IsThereAnyDeal — historical price records
# --------------------------------------------------------------------------- #

def _normalize(title: str) -> str:
    """Strip publisher prefixes / trademark symbols so titles compare cleanly.

    e.g. "EA SPORTS™ Madden NFL 26" -> "madden nfl 26".
    """
    t = title.lower()
    t = re.sub(r"ea sports|™|®|©|�", " ", t)  # � = mojibake replacement char
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Words that signal a special/expensive edition we don't want as the base game.
_EDITION_NOISE = ("deluxe", "edition", "bundle", "season", "pass", "points", "mvp", "superstar")


def itad_find_game_id(title: str, api_key: str) -> str | None:
    """Resolve a game title to its ITAD base-game id (UUID). None if not on PC."""
    resp = requests.get(
        f"{ITAD_BASE}/games/search/v1",
        params={"key": api_key, "title": title},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise DataSourceError(f"ITAD search failed for '{title}' (HTTP {resp.status_code}).")

    games = [r for r in resp.json() if r.get("type") == "game"]
    if not games:
        return None

    wanted = _normalize(title)

    # 1) Exact normalized match with no special-edition noise (the base game).
    for g in games:
        norm = _normalize(g.get("title", ""))
        if norm == wanted and not any(w in norm for w in _EDITION_NOISE):
            return g["id"]
    # 2) Title that starts with what we searched and is a plain edition.
    for g in games:
        norm = _normalize(g.get("title", ""))
        if norm.startswith(wanted) and not any(w in norm for w in _EDITION_NOISE):
            return g["id"]
    # 3) Fall back to the first game result.
    return games[0]["id"]


def itad_price_history(
    game_id: str,
    release_date: date,
    api_key: str,
) -> list[PricePoint]:
    """Daily lowest price for a game, as days-since-release points.

    The history endpoint defaults to the last 3 months, so we pass `since` set
    to the release date to retrieve the full lifetime of the edition.
    """
    since = datetime(release_date.year, release_date.month, release_date.day).isoformat() + "Z"
    resp = requests.get(
        f"{ITAD_BASE}/games/history/v2",
        params={"key": api_key, "id": game_id, "country": COUNTRY, "since": since},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise DataSourceError(f"ITAD history failed (HTTP {resp.status_code}).")

    # Collapse many shop records into one lowest price per calendar day.
    daily_low: dict[int, float] = {}
    for entry in resp.json():
        ts = entry.get("timestamp")
        amount = entry.get("deal", {}).get("price", {}).get("amount")
        if ts is None or amount is None:
            continue
        when = datetime.fromisoformat(ts).date()
        days = (when - release_date).days
        if days < 0:
            continue  # ignore pre-release / preorder noise
        if days not in daily_low or amount < daily_low[days]:
            daily_low[days] = float(amount)

    return [PricePoint(d, p) for d, p in sorted(daily_low.items())]


def itad_all_time_low(game_id: str, api_key: str) -> float | None:
    """All-time lowest price ITAD has ever recorded for the game."""
    resp = requests.post(
        f"{ITAD_BASE}/games/prices/v3",
        params={"key": api_key, "country": COUNTRY, "capacity": 1},
        json=[game_id],
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    if not data:
        return None
    low = data[0].get("historyLow", {}).get("all", {}).get("amount")
    return float(low) if low is not None else None


# --------------------------------------------------------------------------- #
# CheapShark — current deal price
# --------------------------------------------------------------------------- #

# CheapShark store IDs → friendly names (the common PC stores).
CHEAPSHARK_STORES = {
    "1": "Steam",
    "3": "GreenManGaming",
    "7": "GOG",
    "8": "Origin",
    "11": "Humble Store",
    "13": "Uplay",
    "15": "Fanatical",
    "23": "GameBillet",
    "25": "Epic Games",
}


def cheapshark_current_price(title: str) -> CurrentPrice | None:
    """Cheapest current deal for an exact title match across PC retailers."""
    resp = requests.get(
        f"{CHEAPSHARK_BASE}/deals",
        params={"title": title, "pageSize": 60},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        return None

    wanted = title.strip().lower()
    best: tuple[float, str] | None = None
    for deal in resp.json():
        # Exact-title match only, so we skip "Superstar Edition", DLC, etc.
        if deal.get("title", "").strip().lower() != wanted:
            continue
        try:
            price = float(deal["salePrice"])
        except (KeyError, TypeError, ValueError):
            continue
        store = CHEAPSHARK_STORES.get(str(deal.get("storeID")), "PC store")
        if best is None or price < best[0]:
            best = (price, store)

    if best is None:
        return None
    return CurrentPrice(price=best[0], store=best[1], all_time_low=None, source="CheapShark")
