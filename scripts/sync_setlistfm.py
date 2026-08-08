#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from common import load, save, normalize, log_change, now

API = "https://api.setlist.fm/rest/1.0"
MBID = "69ee3720-a7cb-4402-b48d-a02c366f2bcf"  # The Cure
UA = "STATICURE/4.4 (+https://github.com/pub69500-prog/the-cure-tours-V4)"


def log(*args):
    print(*args, flush=True)


def get(path, params, key, retries=4):
    url = API + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "x-api-key": key,
            "User-Agent": UA,
        },
    )

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as exc:
            # setlist.fm can return 404 when a valid search has no matches.
            if exc.code == 404:
                log(f"[setlist.fm] no result: {url}")
                return {"setlist": [], "total": 0, "page": 1, "itemsPerPage": 20}

            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After")
                try:
                    wait = max(2, int(retry_after))
                except (TypeError, ValueError):
                    wait = min(60, 5 * attempt)
                log(f"[setlist.fm] HTTP 429 — waiting {wait}s (attempt {attempt}/{retries})")
                time.sleep(wait)
                continue

            if 500 <= exc.code <= 599 and attempt < retries:
                wait = min(30, 3 * attempt)
                log(f"[setlist.fm] HTTP {exc.code} — retry in {wait}s")
                time.sleep(wait)
                continue

            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            raise RuntimeError(
                f"setlist.fm HTTP {exc.code} for {url}"
                + (f" — {body}" if body else "")
            ) from exc

        except urllib.error.URLError as exc:
            if attempt >= retries:
                raise RuntimeError(f"setlist.fm network error for {url}: {exc}") from exc
            wait = min(30, 3 * attempt)
            log(f"[setlist.fm] network error — retry in {wait}s: {exc}")
            time.sleep(wait)

    return {"setlist": [], "total": 0, "page": 1, "itemsPerPage": 20}


def year_items(year, key):
    out = []
    page = 1
    log(f"[setlist.fm] scanning year {year}")

    while True:
        data = get(
            "/search/setlists",
            {"artistMbid": MBID, "year": year, "p": page},
            key,
        )
        items = data.get("setlist") or []
        out.extend(items)

        total = int(data.get("total") or 0)
        per_page = int(data.get("itemsPerPage") or 20)

        if not items:
            break
        if page * per_page >= total:
            break

        page += 1
        time.sleep(0.7)

    log(f"[setlist.fm] {year}: {len(out)} setlist(s)")
    return out


def songs(item):
    out = []

    for set_block in ((item.get("sets") or {}).get("set") or []):
        encore = set_block.get("encore")
        section = f"Encore {encore}" if encore else "Mainset"
        position = 0

        for song in set_block.get("song") or []:
            # Tape/intros are not counted as songs played.
            if song.get("tape"):
                continue

            name = (song.get("name") or "").strip()
            if name:
                position += 1
                out.append(
                    {
                        "section": section,
                        "position": position,
                        "song": name,
                    }
                )

    return out


def find_concert(concerts, date, city_name, venue_name):
    same_date = [c for c in concerts if c.get("date") == date]
    if not same_date:
        return None

    # Strong match first: date + city + venue.
    city_norm = normalize(city_name)
    venue_norm = normalize(venue_name)

    exact = [
        c
        for c in same_date
        if normalize(c.get("city")) == city_norm
        and normalize(c.get("venue")) == venue_norm
    ]
    if len(exact) == 1:
        return exact[0]

    # Date + city is acceptable only if unique.
    city_matches = [
        c for c in same_date if normalize(c.get("city")) == city_norm
    ]
    if len(city_matches) == 1:
        return city_matches[0]

    # Date alone only if there is exactly one local event that day.
    if len(same_date) == 1:
        return same_date[0]

    return None


def main():
    key = os.getenv("SETLISTFM_API_KEY", "").strip()
    if not key:
        log("[setlist.fm] SETLISTFM_API_KEY missing; synchronization skipped")
        return

    log("[setlist.fm] sync started")

    concerts = load("concerts.json", [])
    setlists = load("setlists.json", [])
    changes = load("changelog.json", [])

    current_year = dt.datetime.now().year

    # Keep the V4 behavior: current year + previous year.
    # A year with no result is now treated normally instead of aborting the workflow.
    for year in (current_year - 1, current_year):
        items = year_items(year, key)

        for index, item in enumerate(items, 1):
            event_date = dt.datetime.strptime(
                item["eventDate"], "%d-%m-%Y"
            ).date().isoformat()

            venue = item.get("venue") or {}
            city = venue.get("city") or {}
            country = city.get("country") or {}

            city_name = city.get("name")
            venue_name = venue.get("name")
            country_name = country.get("name")

            concert = find_concert(
                concerts,
                event_date,
                city_name,
                venue_name,
            )

            if concert is None:
                # Do not silently merge ambiguous events.
                concert = {
                    "id": f"setlistfm:{item.get('id') or event_date}",
                    "date": event_date,
                    "year": year,
                    "artist": "The Cure",
                    "eventType": "Concert",
                    "city": city_name,
                    "venue": venue_name,
                    "country": country_name,
                    "sources": {"secondary": "setlist.fm"},
                }
                concerts.append(concert)
                log_change(
                    changes,
                    concert["id"],
                    event_date,
                    "event",
                    None,
                    "created",
                    item.get("url") or "setlist.fm",
                    "NEW_EVENT",
                )

            concert.setdefault("sources", {})["secondary"] = "setlist.fm"
            concert["setlistFmUrl"] = item.get("url")
            concert["setlistFmId"] = item.get("id")

            # Cure Concerts Guide remains primary for location/history.
            # setlist.fm only fills blanks.
            for key_name, value in [
                ("city", city_name),
                ("venue", venue_name),
                ("country", country_name),
                ("tour", (item.get("tour") or {}).get("name")),
            ]:
                if not concert.get(key_name) and value:
                    concert[key_name] = value

            new_songs = songs(item)

            if new_songs:
                existing = [
                    row
                    for row in setlists
                    if row.get("concertId") == concert["id"]
                    or (
                        row.get("date") == event_date
                        and normalize(row.get("city")) == normalize(city_name)
                    )
                ]

                # setlist.fm may enrich a missing/unknown/unconfirmed recent setlist.
                # It MUST NOT convert Cure Guide confirmation status to "confirmed".
                cure_status = str(
                    concert.get("setlistConfirmation")
                    or concert.get("cureGuideSetlistStatus")
                    or concert.get("setlistStatus")
                    or ""
                ).lower()

                replace_allowed = (
                    not existing
                    or cure_status in {"", "unknown", "unconfirmed", "community"}
                )

                if replace_allowed:
                    setlists = [
                        row
                        for row in setlists
                        if not (
                            row.get("concertId") == concert["id"]
                            or (
                                row.get("date") == event_date
                                and normalize(row.get("city")) == normalize(city_name)
                            )
                        )
                    ]

                    setlists += [
                        {
                            "concertId": concert["id"],
                            "date": event_date,
                            **entry,
                            "countsAsSong": True,
                            "status": "Community",
                            "sourceUrl": item.get("url"),
                        }
                        for entry in new_songs
                    ]

                    concert["songsPlayed"] = len(new_songs)
                    concert["setlistFmStatus"] = "Community"

                    # Preserve Cure Concerts Guide confirmation independently.
                    # setlist.fm can provide a community setlist, but it never
                    # upgrades Cure Guide confirmation to Confirmed.
                    if not concert.get("setlistConfirmation"):
                        concert["setlistConfirmation"] = "Unknown"
                    if not concert.get("setlistStatus"):
                        concert["setlistStatus"] = concert.get("setlistConfirmation") or "Unknown"

                    log_change(
                        changes,
                        concert["id"],
                        event_date,
                        "setlist",
                        len(existing),
                        len(new_songs),
                        item.get("url") or "setlist.fm",
                        "NEW_SETLIST",
                    )

            if index % 10 == 0 or index == len(items):
                log(f"[setlist.fm] {year}: {index}/{len(items)} processed")

            time.sleep(0.25)

        time.sleep(0.7)

    save("concerts.json", sorted(concerts, key=lambda x: x["date"]))
    save("setlists.json", setlists)
    save("changelog.json", changes[-5000:])

    state = load("state.json", {})
    state["setlistFmLastSync"] = now()
    save("state.json", state)

    log("[setlist.fm] sync completed")


if __name__ == "__main__":
    main()
