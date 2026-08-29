#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from html import unescape

from bs4 import BeautifulSoup, NavigableString, Tag
from common import load, save, log_change, now, normalize


BASE = "https://www.cure-concerts.de"
UA = (
    "STATICURE-archive-sync/4.8 "
    "(+https://github.com/pub69500-prog/the-cure-tours-V4)"
)

TITLE_RE = re.compile(
    r"^(?P<artist>.*?)\s+"
    r"(?P<date>\d{4}-(?:\d{2}|xx)-(?:\d{2}|xx))\s+"
    r"(?P<city>.+?)\s+-\s+"
    r"(?P<venue>.+?)\s+\((?P<country>[^)]+)\)"
)

CONCERT_URL_RE = re.compile(
    r"/concerts/\d{4}-(?:\d{2}|xx)-(?:\d{2}|xx)(?:_[^/?#]+)?\.php$",
    re.I,
)

UPDATE_DATE_RE = re.compile(
    r"^(?P<day>\d{1,2})\.\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+"
    r"(?P<year>\d{4})$",
    re.I,
)

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

LABELS = {
    "Songs played": "songsPlayed",
    "Set length": "setLengthMin",
    "Set time": "setTime",
    "Curfew": "curfew",
    "Tour": "tour",
    "Attendance": "attendance",
    "Capacity": "concertCapacity",
    "Address": "venueAddress",
}

CORE_ARTISTS = {
    "the cure": "The Cure",
    "easy cure": "Easy Cure",
    "malice": "Malice",
}

_ROBOTS = None
_ROBOTS_READY = False


def _log(*args):
    print(*args, flush=True)


def _env_true(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "oui", "y", "on"}


def _respect_robots():
    return _env_true("CUREGUIDE_RESPECT_ROBOTS", True)


def _full_scan_requested():
    return _env_true("CUREGUIDE_FULL_SCAN", False)


def _load_robots_once():
    global _ROBOTS, _ROBOTS_READY

    if _ROBOTS_READY:
        return _ROBOTS

    _ROBOTS_READY = True

    if not _respect_robots():
        _log("[cureguide] robots.txt check disabled by configuration")
        return None

    robots_url = BASE + "/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)

    try:
        req = urllib.request.Request(
            robots_url,
            headers={
                "User-Agent": UA,
                "Accept": "text/plain,*/*;q=0.1",
            },
        )

        with urllib.request.urlopen(req, timeout=8) as response:
            body = response.read().decode("utf-8", "replace")

        rp.parse(body.splitlines())
        _ROBOTS = rp
        _log("[cureguide] robots.txt loaded once")

    except Exception as exc:
        _ROBOTS = None
        _log(
            "[cureguide] WARNING: "
            f"robots.txt unavailable ({exc}); continuing"
        )

    return _ROBOTS


def allowed(url):
    if not _respect_robots():
        return True

    rp = _load_robots_once()

    if rp is None:
        return True

    return rp.can_fetch(UA, url)


def fetch(url, retries=4):
    if not allowed(url):
        raise RuntimeError(f"robots.txt interdit {url}")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en,fr;q=0.8",
        },
    )

    last_error = None

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.read().decode("utf-8", "replace")

        except Exception as exc:
            last_error = exc

            if attempt >= retries:
                break

            wait_time = 5 * attempt

            _log(
                "[cureguide] fetch failed "
                f"({attempt}/{retries}) "
                f"{url}: {exc} — "
                f"retry in {wait_time}s"
            )

            time.sleep(wait_time)

    raise RuntimeError(
        f"failed to fetch {url} after {retries} attempts: {last_error}"
    )

def _inline_confirmation_hint(anchor):
    bits = []
    node = anchor

    for _ in range(4):
        if node is None:
            break

        bits += list(node.get("class") or [])
        bits.append(node.get("style") or "")
        node = node.parent

    blob = " ".join(bits).lower()

    if any(
        x in blob
        for x in (
            "unconfirmed",
            "notconfirmed",
            "unknown",
            " grey",
            " gray",
        )
    ):
        return "Unconfirmed"

    if "confirmed" in blob and "unconfirmed" not in blob:
        return "Confirmed"

    if re.search(
        r"color\s*:\s*(?:grey|gray|#(?:777|888|999|aaa|bbb)\b)",
        blob,
    ):
        return "Unconfirmed"

    if re.search(
        r"color\s*:\s*(?:white|#fff(?:fff)?\b)",
        blob,
    ):
        return "Confirmed"

    return "Unknown"


def _normalize_update_date(text: str) -> str | None:
    text = re.sub(r"\s+", " ", unescape(text or "")).strip()
    m = UPDATE_DATE_RE.match(text)

    if not m:
        return None

    month = MONTHS[m.group("month").lower()]

    try:
        value = dt.date(
            int(m.group("year")),
            month,
            int(m.group("day")),
        )
    except ValueError:
        return None

    return value.isoformat()


def parse_update_entries(html: str):
    """
    Parse updates.php once and return:
      [
        {
          "key": "2026-08-07|https://.../2026-08-07.php",
          "updateDate": "2026-08-07",
          "url": "...",
          "hint": "Confirmed/Unconfirmed/Unknown"
        },
        ...
      ]

    The key includes the update date. Therefore, if the same historical concert
    is corrected again on a later date, it becomes a NEW update event and will
    be fetched again even though its URL already existed.
    """
    soup = BeautifulSoup(html, "html.parser")

    current_update_date = None
    entries = []
    seen_keys = set()

    for node in soup.descendants:
        if isinstance(node, NavigableString):
            date_value = _normalize_update_date(str(node))
            if date_value:
                current_update_date = date_value
            continue

        if not isinstance(node, Tag):
            continue

        if node.name != "a" or not node.get("href"):
            continue

        if not current_update_date:
            # Navigation links occur before the actual chronological update list.
            continue

        url = urllib.parse.urljoin(
            BASE + "/main/updates.php",
            node["href"],
        )

        if not CONCERT_URL_RE.search(
            urllib.parse.urlsplit(url).path
        ):
            continue

        key = f"{current_update_date}|{url}"

        if key in seen_keys:
            continue

        seen_keys.add(key)

        entries.append(
            {
                "key": key,
                "updateDate": current_update_date,
                "url": url,
                "hint": _inline_confirmation_hint(node),
            }
        )

    return entries


def parse_year_page(page_url: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    result = {}

    for a in soup.find_all("a", href=True):
        url = urllib.parse.urljoin(page_url, a["href"])

        if not CONCERT_URL_RE.search(
            urllib.parse.urlsplit(url).path
        ):
            continue

        hint = _inline_confirmation_hint(a)
        previous = result.get(url, "Unknown")

        result[url] = (
            hint
            if hint != "Unknown"
            else previous
        )

    return result


def incremental_candidates(state):
    """
    Daily mode.

    Network cost:
      - 1 x updates.php
      - current year / previous year / next year index pages
      - only NEW update entries
      - all detail pages of active years

    Historical URLs already listed in updates.php are not downloaded again
    every day unless they receive a new dated update entry.
    """
    year = dt.datetime.now().year
    update_url = f"{BASE}/main/updates.php"

    _log(f"[cureguide] scanning {update_url}")
    updates_html = fetch(update_url)
    update_entries = parse_update_entries(updates_html)

    old_seen = set(
        state.get("cureGuideSeenUpdateEntries") or []
    )

    bootstrapping = (
        state.get("cureGuideIncrementalVersion") != "4.8"
        or not old_seen
    )

    all_update_keys = [x["key"] for x in update_entries]

    if bootstrapping:
        # V4.7 has just performed the trusted full synchronization.
        # Seed current update history instead of re-fetching 500+ old pages.
        new_update_entries = []
        _log(
            "[cureguide] incremental bootstrap: "
            f"memorizing {len(all_update_keys)} existing update entries"
        )
    else:
        new_update_entries = [
            x
            for x in update_entries
            if x["key"] not in old_seen
        ]

    candidates = {}

    for entry in new_update_entries:
        candidates[entry["url"]] = entry["hint"]

    # Active years are intentionally rescanned daily.
    # This catches late setlists, venue changes and announced future shows
    # even before an item is added to updates.php.
    for active_year in (
        year - 1,
        year,
        year + 1,
    ):
        page = f"{BASE}/main/{active_year}.php"
        _log(f"[cureguide] scanning active year {page}")

        try:
            html = fetch(page)
            year_urls = parse_year_page(page, html)

            for url, hint in year_urls.items():
                previous = candidates.get(url, "Unknown")
                candidates[url] = (
                    hint
                    if hint != "Unknown"
                    else previous
                )

        except Exception as exc:
            # Next-year pages may legitimately not exist yet.
            _log(
                "[cureguide] active-year page unavailable "
                f"{page}: {exc}"
            )

        time.sleep(0.5)

    newest_update = (
        max(
            (x["updateDate"] for x in update_entries),
            default=None,
        )
    )

    state_patch = {
        # Keep enough history to recognize old update entries.
        # 4000 is comfortably above the current update page volume.
        "cureGuideSeenUpdateEntries":
            all_update_keys[:4000],

        "cureGuideLatestUpdateDate":
            newest_update,

        "cureGuideIncrementalVersion":
            "4.8",

        "cureGuideUpdatesListed":
            len(update_entries),

        "cureGuideNewUpdateEntries":
            len(new_update_entries),
    }

    return sorted(candidates.items()), state_patch


def full_candidates():
    """
    Manual audit mode.

    Keeps the known V4.7 behavior:
      - all URLs referenced by updates.php
      - previous/current/next active year pages

    This is intentionally NOT the normal daily mode.
    """
    year = dt.datetime.now().year
    candidates = {}

    update_url = f"{BASE}/main/updates.php"
    _log(f"[cureguide] FULL scan {update_url}")

    try:
        updates_html = fetch(update_url)
        entries = parse_update_entries(updates_html)

        for entry in entries:
            previous = candidates.get(
                entry["url"],
                "Unknown",
            )

            candidates[entry["url"]] = (
                entry["hint"]
                if entry["hint"] != "Unknown"
                else previous
            )

    except Exception as exc:
        _log(
            "[cureguide] ERROR scanning updates page: "
            f"{exc}"
        )

    for active_year in (
        year - 1,
        year,
        year + 1,
    ):
        page = f"{BASE}/main/{active_year}.php"
        _log(f"[cureguide] FULL scan {page}")

        try:
            html = fetch(page)

            for url, hint in parse_year_page(
                page,
                html,
            ).items():
                previous = candidates.get(
                    url,
                    "Unknown",
                )

                candidates[url] = (
                    hint
                    if hint != "Unknown"
                    else previous
                )

        except Exception as exc:
            _log(
                f"[cureguide] ERROR scanning {page}: {exc}"
            )

        time.sleep(0.5)

    return sorted(candidates.items())


def _all_marker_text(soup):
    parts = []

    for img in soup.find_all("img"):
        for attr in (
            "alt",
            "title",
        ):
            value = img.get(attr)
            if value:
                parts.append(str(value))

    for tag in soup.find_all(True):
        title = tag.get("title")
        if title:
            parts.append(str(title))

    return " ".join(parts).lower()


def _confirmation_status(
    soup,
    text,
    songs_played,
):
    markers = _all_marker_text(soup)
    combined = markers + " " + text.lower()

    has_named_setlist = bool(
        songs_played
        or re.search(
            r"(?im)^\s*"
            r"(?:mainset|encore\s*\d*|set\s*\d*)"
            r"\s*:",
            text,
        )
    )

    if (
        "setlist unknown" in combined
        or "setlist unconfirmed" in combined
    ):
        setlist_confirmation = (
            "Unconfirmed"
            if has_named_setlist
            else "Unknown"
        )

    elif "setlist confirmed" in combined:
        setlist_confirmation = "Confirmed"

    else:
        setlist_confirmation = "Unknown"

    if (
        "concert unconfirmed" in combined
        or "concert unknown" in combined
    ):
        concert_confirmation = "Unconfirmed"

    elif "concert confirmed" in combined:
        concert_confirmation = "Confirmed"

    else:
        concert_confirmation = "Unknown"

    return (
        concert_confirmation,
        setlist_confirmation,
    )


def _normalize_artist(value):
    return (
        str(value or "The Cure")
        .strip()
        .rstrip(":")
        .strip()
        .lower()
    )


def _classify_artist(
    artist,
    page_title="",
):
    raw_artist = (
        str(artist or "The Cure")
        .strip()
        .rstrip(":")
        .strip()
    )

    artist_norm = _normalize_artist(raw_artist)

    if (
        artist_norm == "the cure"
        or artist_norm.startswith("the cure ")
    ):
        return (
            "The Cure",
            True,
            "Concert",
        )

    if (
        artist_norm == "easy cure"
        or artist_norm.startswith("easy cure ")
    ):
        return (
            "Easy Cure",
            True,
            "Concert",
        )

    if (
        artist_norm == "malice"
        or artist_norm.startswith("malice ")
    ):
        return (
            "Malice",
            True,
            "Concert",
        )

    title_norm = (
        str(page_title or "")
        .strip()
        .lower()
    )

    if "the cure live concert" in title_norm:
        return (
            "The Cure",
            True,
            "Concert",
        )

    if "easy cure live concert" in title_norm:
        return (
            "Easy Cure",
            True,
            "Concert",
        )

    if "malice live concert" in title_norm:
        return (
            "Malice",
            True,
            "Concert",
        )

    return (
        raw_artist or "Unknown",
        False,
        "Guest appearance",
    )


def parse(
    url,
    html,
    concert_hint="Unknown",
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    title = (
        soup.title.get_text(
            " ",
            strip=True,
        )
        if soup.title
        else ""
    )

    text = "\n".join(
        x.strip()
        for x in soup.get_text(
            "\n"
        ).splitlines()
        if x.strip()
    )

    m = (
        TITLE_RE.search(title)
        or TITLE_RE.search(text)
    )

    date_match = re.search(
        r"(\d{4}-(?:\d{2}|xx)-"
        r"(?:\d{2}|xx))",
        url,
    )

    if not date_match:
        raise ValueError(
            "date introuvable "
            f"dans l'URL: {url}"
        )

    date = date_match.group(1)

    out = {
        "id": None,
        "date": date,
        "year": int(date[:4]),
        "sourceUrl": url,
        "scrapedAt": now(),
        "pageTitle": title,
        "sources": {
            "primary":
                "cure-concerts.de"
        },
        "confirmationSource":
            "cure-concerts.de",
    }

    if m:
        out.update(
            {
                "artist":
                    m["artist"]
                    .strip()
                    .rstrip(":")
                    .strip()
                    or "The Cure",

                "city":
                    m["city"]
                    .strip(),

                "venue":
                    m["venue"]
                    .strip(),

                "country":
                    m["country"]
                    .strip(),
            }
        )

    (
        artist,
        is_core,
        event_type,
    ) = _classify_artist(
        out.get("artist"),
        title,
    )

    out["artist"] = artist
    out["isTheCureConcert"] = is_core
    out["guestAppearance"] = not is_core
    out["eventType"] = event_type

    lines = text.splitlines()

    for i, line in enumerate(lines):
        for label, key in LABELS.items():
            if (
                line.rstrip(":").lower()
                != label.lower()
            ):
                continue

            if i + 1 >= len(lines):
                continue

            value = lines[i + 1]

            if key in {
                "songsPlayed",
                "attendance",
                "concertCapacity",
                "setLengthMin",
            }:
                number = re.search(
                    r"\d[\d,']*",
                    value,
                )

                if not number:
                    continue

                value = int(
                    number
                    .group(0)
                    .replace(",", "")
                    .replace("'", "")
                )

            out[key] = value

    (
        page_concert_status,
        setlist_status,
    ) = _confirmation_status(
        soup,
        text,
        out.get("songsPlayed"),
    )

    out["concertConfirmation"] = (
        page_concert_status
        if page_concert_status != "Unknown"
        else concert_hint
    )

    out["setlistConfirmation"] = (
        setlist_status
    )

    out["setlistStatus"] = (
        setlist_status
    )

    return out


def main():
    mode = (
        "FULL"
        if _full_scan_requested()
        else "INCREMENTAL"
    )

    _log(
        f"[cureguide] sync V4.8 started — mode {mode}"
    )

    _load_robots_once()

    concerts = load(
        "concerts.json",
        [],
    )

    changes = load(
        "changelog.json",
        [],
    )

    state = load(
        "state.json",
        {},
    )

    byid = {
        c["id"]: c
        for c in concerts
    }

    byurl = {
        c.get("sourceUrl"): c
        for c in concerts
        if c.get("sourceUrl")
    }

    state_patch = {}

    if _full_scan_requested():
        items = full_candidates()
    else:
        items, state_patch = incremental_candidates(
            state
        )

    _log(
        "[cureguide] "
        f"{len(items)} detail page(s) selected"
    )

    if state_patch.get("cureGuideNewUpdateEntries") is not None:
        _log(
            "[cureguide] "
            f"{state_patch['cureGuideNewUpdateEntries']} "
            "new dated update entrie(s)"
        )

    for index, (
        url,
        concert_hint,
    ) in enumerate(
        items,
        1,
    ):
        _log(
            f"[cureguide] "
            f"{index}/{len(items)} "
            f"{url}"
        )

        try:
            patch = parse(
                url,
                fetch(url),
                concert_hint,
            )

        except Exception as exc:
            _log(
                "[cureguide] skip "
                f"{url}: {exc}"
            )
            continue

        old = byurl.get(url)

        if old is None:
            same = [
                c
                for c in byid.values()
                if (
                    c.get("date")
                    == patch["date"]

                    and normalize(
                        c.get("city")
                    )
                    == normalize(
                        patch.get("city")
                    )

                    and normalize(
                        c.get("venue")
                    )
                    == normalize(
                        patch.get("venue")
                    )
                )
            ]

            old = (
                same[0]
                if len(same) == 1
                else None
            )

        if old is None:
            base = (
                f"cureguide:"
                f"{patch['date']}:"
                f"{normalize(patch.get('city')).replace(' ', '-')}:"
                f"{normalize(patch.get('venue')).replace(' ', '-')}"
            ).rstrip(":")

            cid = base
            duplicate = 2

            while cid in byid:
                cid = (
                    f"{base}:"
                    f"{duplicate}"
                )
                duplicate += 1

            patch["id"] = cid
            byid[cid] = patch
            byurl[url] = patch

            log_change(
                changes,
                cid,
                patch["date"],
                "event",
                None,
                "created",
                url,
                "NEW_EVENT",
            )

        else:
            for key, value in patch.items():
                if (
                    key in {
                        "id",
                        "sources",
                    }
                    or value in {
                        None,
                        "",
                    }
                ):
                    continue

                if key == "scrapedAt":
                    old[key] = value
                    continue

                if (
                    key in {
                        "concertConfirmation",
                        "setlistConfirmation",
                        "setlistStatus",
                    }
                    and value == "Unknown"
                    and old.get(key)
                    in {
                        "Confirmed",
                        "Unconfirmed",
                    }
                ):
                    continue

                if old.get(key) == value:
                    continue

                if key in {
                    "concertConfirmation",
                    "setlistConfirmation",
                    "setlistStatus",
                    "eventType",
                    "isTheCureConcert",
                    "guestAppearance",
                    "artist",
                }:
                    change_type = (
                        "STATUS_CHANGE"
                    )

                elif (
                    old.get("year")
                    and old["year"]
                    < dt.datetime.now().year
                ):
                    change_type = (
                        "HISTORICAL_CORRECTION"
                    )

                else:
                    change_type = (
                        "UPDATED_EVENT"
                    )

                log_change(
                    changes,
                    old["id"],
                    old["date"],
                    key,
                    old.get(key),
                    value,
                    url,
                    change_type,
                )

                old[key] = value

            old.setdefault(
                "sources",
                {},
            )["primary"] = (
                "cure-concerts.de"
            )

            old[
                "confirmationSource"
            ] = (
                "cure-concerts.de"
            )

        time.sleep(0.8)

    save(
        "concerts.json",
        sorted(
            byid.values(),
            key=lambda concert:
                concert["date"],
        ),
    )

    save(
        "changelog.json",
        changes[-5000:],
    )

    state["cureGuideLastSync"] = now()
    state["cureGuideCandidates"] = len(items)
    state["cureGuideVersion"] = "4.8"
    state["cureGuideMode"] = mode

    for key, value in state_patch.items():
        state[key] = value

    save(
        "state.json",
        state,
    )

    _log(
        f"[cureguide] sync V4.8 completed — "
        f"{len(items)} detail page(s)"
    )


if __name__ == "__main__":
    main()
