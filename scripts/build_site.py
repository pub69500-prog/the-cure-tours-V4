#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from common import ROOT, DATA, load

DIST = ROOT / "dist"
SITE = ROOT / "site"


def as_bool(value) -> bool:
    """Normalize values coming from Excel/JSON/string sources."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "oui", "y"}


def clean_song_rows(rows):
    """
    Convert canonical setlist rows to the compact structure expected by
    the original V3/V4.5 JavaScript interface.
    """
    result = []
    for row in rows:
        song = row.get("song")
        if not song:
            continue

        # Keep the historical interface focused on actual performed songs.
        # Intros/tapes explicitly marked as non-song are not included in rankings.
        if row.get("countsAsSong", True) is False:
            continue

        result.append(
            {
                "section": row.get("section") or "Mainset",
                "position": row.get("position"),
                "song": song,
                # Extra V4.5 metadata: harmless for the old frontend and useful later.
                "status": row.get("status") or "Unknown",
                "sourceUrl": row.get("sourceUrl"),
            }
        )

    def section_rank(name: str):
        if name == "Mainset":
            return (0, 0)
        if name and name.startswith("Encore"):
            try:
                return (1, int(name.split()[-1]))
            except (ValueError, IndexError):
                return (1, 999)
        return (2, 0)

    result.sort(
        key=lambda x: (
            section_rank(x.get("section")),
            x.get("position") if isinstance(x.get("position"), int) else 9999,
        )
    )
    return result


def build_frontend_concerts(concerts, setlists):
    """
    Preserve the exact data contract used by the original 7-tab frontend.

    The canonical V4 database uses stable string IDs such as:
      cureguide:2026-07-26:nimes:arenes-de-nimes

    The original JavaScript expects numeric IDs and calls parseInt() when a row
    is clicked. We therefore assign deterministic numeric frontend IDs while
    retaining the canonical ID in `canonicalId`.
    """
    by_concert = defaultdict(list)
    by_date = defaultdict(list)

    for row in setlists:
        cid = row.get("concertId")
        if cid:
            by_concert[str(cid)].append(row)
        if row.get("date"):
            by_date[row["date"]].append(row)

    # Stable order gives stable numeric IDs across builds unless an older-dated
    # concert is inserted. canonicalId remains the durable identifier.
    ordered = sorted(
        concerts,
        key=lambda c: (
            c.get("date") or "9999-99-99",
            c.get("city") or "",
            c.get("venue") or "",
            str(c.get("id") or ""),
        ),
    )

    frontend = []

    for frontend_id, c in enumerate(ordered, start=1):
        canonical_id = str(c.get("id") or "")
        rows = by_concert.get(canonical_id, [])

        # Fallback for legacy/imported rows that have no concertId.
        if not rows and c.get("date"):
            same_date = by_date.get(c["date"], [])
            if len({str(x.get("concertId") or "") for x in same_date}) <= 1:
                rows = same_date

        setlist = clean_song_rows(rows)

        songs_played = c.get("songsPlayed")
        if songs_played is None and setlist:
            songs_played = len(setlist)

        capacity = c.get("concertCapacity")
        if capacity is None:
            capacity = c.get("capacity")
        if capacity is None:
            capacity = c.get("generalVenueCapacity")

        item = {
            # Fields required by the original frontend:
            "id": frontend_id,
            "date": c.get("date"),
            "year": c.get("year"),
            "city": c.get("city"),
            "venue": c.get("venue"),
            "country": c.get("country"),
            "tour": c.get("tour"),
            "songsPlayed": songs_played,
            "attendance": c.get("attendance"),
            "capacity": capacity,
            "soldOut": as_bool(c.get("soldOut")),
            "dow": c.get("dayOfWeek") or c.get("dow"),
            "address": c.get("venueAddress") or c.get("address"),
            "setlist": setlist,

            # V4/V4.5 metadata retained for future UI additions:
            "canonicalId": canonical_id,
            "artist": c.get("artist") or "The Cure",
            "eventType": c.get("eventType") or "Concert",
            "event": c.get("event"),
            "setLengthMin": c.get("setLengthMin"),
            "setTime": c.get("setTime"),
            "curfew": c.get("curfew"),
            "sourceUrl": c.get("sourceUrl"),
            "setlistFmUrl": c.get("setlistFmUrl"),
            "concertConfirmation": c.get("concertConfirmation") or "Unknown",
            "setlistConfirmation": (
                c.get("setlistConfirmation")
                or c.get("setlistStatus")
                or "Unknown"
            ),
            "confirmationSource": c.get("confirmationSource"),
            "scrapedAt": c.get("scrapedAt"),
        }

        frontend.append(item)

    return frontend


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main():
    concerts = load("concerts.json", [])
    setlists = load("setlists.json", [])
    changes = load("changelog.json", [])
    state = load("state.json", {})

    if not SITE.exists():
        raise SystemExit("[build] ERROR: site/ is missing")

    if DIST.exists():
        shutil.rmtree(DIST)

    # Preserve the V4.5 frontend exactly as committed in site/.
    shutil.copytree(SITE, DIST)

    data_dir = DIST / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Build the compatibility data file consumed by assets/app.js.
    frontend_concerts = build_frontend_concerts(concerts, setlists)
    write_json(data_dir / "concerts.json", frontend_concerts)

    # Also publish canonical V4 data for debugging/future features.
    write_json(data_dir / "canonical-concerts.json", concerts)
    write_json(data_dir / "setlists.json", setlists)
    write_json(data_dir / "changelog.json", changes)
    write_json(data_dir / "state.json", state)

    years = Counter(c.get("year") for c in concerts if c.get("year"))
    countries = Counter(c.get("country") for c in concerts if c.get("country"))
    venues = Counter(c.get("venue") for c in concerts if c.get("venue"))
    songs = Counter(
        x.get("song")
        for x in setlists
        if x.get("countsAsSong", True)
        and x.get("song")
        and not str(x.get("song")).startswith("[")
    )

    stats = {
        "concerts": len(concerts),
        "frontendConcerts": len(frontend_concerts),
        "setlistEntries": len(setlists),
        "years": dict(sorted(years.items())),
        "countries": countries.most_common(30),
        "venues": venues.most_common(30),
        "songs": songs.most_common(100),
        "confirmation": {
            "concertsConfirmed": sum(
                1 for c in concerts
                if c.get("concertConfirmation") == "Confirmed"
            ),
            "concertsUnconfirmed": sum(
                1 for c in concerts
                if c.get("concertConfirmation") == "Unconfirmed"
            ),
            "setlistsConfirmed": sum(
                1 for c in concerts
                if c.get("setlistConfirmation") == "Confirmed"
            ),
            "setlistsUnconfirmed": sum(
                1 for c in concerts
                if c.get("setlistConfirmation") == "Unconfirmed"
            ),
        },
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "lastSync": (
            state.get("lastSync")
            or state.get("cureGuideLastSync")
            or state.get("setlistFmLastSync")
        ),
    }
    write_json(data_dir / "stats.json", stats)

    # Sanity checks specifically for the restored original frontend.
    if len(frontend_concerts) != len(concerts):
        raise SystemExit(
            f"[build] ERROR: frontend count {len(frontend_concerts)} "
            f"!= canonical count {len(concerts)}"
        )

    missing_setlist_property = [
        c["id"] for c in frontend_concerts if not isinstance(c.get("setlist"), list)
    ]
    if missing_setlist_property:
        raise SystemExit("[build] ERROR: malformed frontend setlist data")

    print(
        "[build] V4.5 dist ready:",
        len(frontend_concerts),
        "concerts |",
        sum(len(c["setlist"]) for c in frontend_concerts),
        "performed-song entries",
    )


if __name__ == "__main__":
    main()
