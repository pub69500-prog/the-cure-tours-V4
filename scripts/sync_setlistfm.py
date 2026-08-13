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
UA = "STATICURE/4.8 (+https://github.com/pub69500-prog/the-cure-tours-V4)"


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
                return json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as exc:

            # A search without results can legitimately return 404.
            if exc.code == 404:
                log(
                    f"[setlist.fm] no result: {url}"
                )
                return {
                    "setlist": [],
                    "total": 0,
                    "page": 1,
                    "itemsPerPage": 20,
                }

            # Rate limiting.
            if exc.code == 429:
                retry_after = exc.headers.get(
                    "Retry-After"
                )

                try:
                    wait = max(
                        2,
                        int(retry_after)
                    )
                except (TypeError, ValueError):
                    wait = min(
                        60,
                        5 * attempt
                    )

                log(
                    "[setlist.fm] HTTP 429 — "
                    f"waiting {wait}s "
                    f"(attempt {attempt}/{retries})"
                )

                time.sleep(wait)
                continue

            # Temporary server-side errors.
            if (
                500 <= exc.code <= 599
                and attempt < retries
            ):
                wait = min(
                    30,
                    3 * attempt
                )

                log(
                    f"[setlist.fm] HTTP {exc.code} "
                    f"— retry in {wait}s"
                )

                time.sleep(wait)
                continue

            body = ""

            try:
                body = (
                    exc.read()
                    .decode(
                        "utf-8",
                        "replace"
                    )[:500]
                )
            except Exception:
                pass

            raise RuntimeError(
                f"setlist.fm HTTP {exc.code} "
                f"for {url}"
                + (
                    f" — {body}"
                    if body
                    else ""
                )
            ) from exc

        except urllib.error.URLError as exc:

            if attempt >= retries:
                raise RuntimeError(
                    "setlist.fm network error "
                    f"for {url}: {exc}"
                ) from exc

            wait = min(
                30,
                3 * attempt
            )

            log(
                "[setlist.fm] network error "
                f"— retry in {wait}s: {exc}"
            )

            time.sleep(wait)

    return {
        "setlist": [],
        "total": 0,
        "page": 1,
        "itemsPerPage": 20,
    }


def year_items(year, key):
    out = []
    page = 1

    log(
        f"[setlist.fm] scanning year {year}"
    )

    while True:
        data = get(
            "/search/setlists",
            {
                "artistMbid": MBID,
                "year": year,
                "p": page,
            },
            key,
        )

        items = data.get("setlist") or []

        out.extend(items)

        total = int(
            data.get("total") or 0
        )

        per_page = int(
            data.get("itemsPerPage") or 20
        )

        if not items:
            break

        if page * per_page >= total:
            break

        page += 1
        time.sleep(0.7)

    log(
        f"[setlist.fm] {year}: "
        f"{len(out)} setlist(s)"
    )

    return out


def songs(item):
    out = []

    for set_block in (
        (item.get("sets") or {})
        .get("set") or []
    ):
        encore = set_block.get(
            "encore"
        )

        section = (
            f"Encore {encore}"
            if encore
            else "Mainset"
        )

        position = 0

        for song in (
            set_block.get("song") or []
        ):

            # Tape / intro entries are not
            # counted as performed songs.
            if song.get("tape"):
                continue

            name = (
                song.get("name") or ""
            ).strip()

            if not name:
                continue

            position += 1

            out.append(
                {
                    "section": section,
                    "position": position,
                    "song": name,
                }
            )

    return out


def find_concert(
    concerts,
    date,
    city_name,
    venue_name,
):
    """
    Match a setlist.fm event against an EXISTING
    canonical Cure Guide concert.

    IMPORTANT:
    setlist.fm never creates a canonical concert.

    Matching priority:

    1. date + city + venue
    2. date + city, but ONLY if unique

    Date-only matching is deliberately forbidden
    because The Cure sometimes played multiple
    concerts on the same date.
    """

    same_date = [
        c
        for c in concerts
        if c.get("date") == date
    ]

    if not same_date:
        return None

    city_norm = normalize(
        city_name
    )

    venue_norm = normalize(
        venue_name
    )

    # ----------------------------------------------------------
    # STRONG MATCH
    # date + city + venue
    # ----------------------------------------------------------

    exact = [
        c
        for c in same_date
        if normalize(
            c.get("city")
        ) == city_norm
        and normalize(
            c.get("venue")
        ) == venue_norm
    ]

    if len(exact) == 1:
        return exact[0]

    # More than one exact result means that Cure Guide
    # contains multiple shows at the same venue/date.
    # We must NOT guess which one setlist.fm refers to.
    if len(exact) > 1:
        log(
            "[setlist.fm] ambiguous exact match:",
            date,
            "|",
            city_name,
            "|",
            venue_name,
            f"| {len(exact)} Cure Guide events"
        )

        return None

    # ----------------------------------------------------------
    # SECONDARY MATCH
    # date + city only, if unique
    # ----------------------------------------------------------

    city_matches = [
        c
        for c in same_date
        if normalize(
            c.get("city")
        ) == city_norm
    ]

    if len(city_matches) == 1:
        return city_matches[0]

    if len(city_matches) > 1:
        log(
            "[setlist.fm] ambiguous city match:",
            date,
            "|",
            city_name,
            f"| {len(city_matches)} Cure Guide events"
        )

    return None


def main():
    key = os.getenv(
        "SETLISTFM_API_KEY",
        ""
    ).strip()

    if not key:
        log(
            "[setlist.fm] "
            "SETLISTFM_API_KEY missing; "
            "synchronization skipped"
        )
        return

    log(
        "[setlist.fm] sync V4.8 started"
    )

    concerts = load(
        "concerts.json",
        []
    )

    setlists = load(
        "setlists.json",
        []
    )

    changes = load(
        "changelog.json",
        []
    )

    current_year = (
        dt.datetime.now().year
    )

    matched_count = 0
    unmatched_count = 0
    enriched_count = 0
    ambiguous_count = 0

    # Current year + previous year.
    for year in (
        current_year - 1,
        current_year,
    ):
        items = year_items(
            year,
            key
        )

        for index, item in enumerate(
            items,
            1
        ):
            event_date = (
                dt.datetime.strptime(
                    item["eventDate"],
                    "%d-%m-%Y",
                )
                .date()
                .isoformat()
            )

            venue = (
                item.get("venue") or {}
            )

            city = (
                venue.get("city") or {}
            )

            country = (
                city.get("country") or {}
            )

            city_name = city.get(
                "name"
            )

            venue_name = venue.get(
                "name"
            )

            country_name = country.get(
                "name"
            )

            concert = find_concert(
                concerts,
                event_date,
                city_name,
                venue_name,
            )

            # ==================================================
            # CRITICAL V4.8 RULE
            #
            # Cure Concerts Guide owns the canonical archive.
            #
            # A setlist.fm-only event is NOT automatically
            # inserted into concerts.json.
            # ==================================================

            if concert is None:

                same_date = [
                    c
                    for c in concerts
                    if c.get("date")
                    == event_date
                ]

                if same_date:
                    ambiguous_count += 1
                else:
                    unmatched_count += 1

                log(
                    "[setlist.fm] unmatched — "
                    "NOT added to canonical archive:",
                    event_date,
                    "|",
                    city_name or "?",
                    "|",
                    venue_name or "?",
                    "|",
                    item.get("url") or "",
                )

                continue

            matched_count += 1

            # ==================================================
            # SOURCE METADATA
            # ==================================================

            sources = concert.setdefault(
                "sources",
                {}
            )

            # Never replace the primary source.
            if not sources.get("primary"):
                sources["primary"] = (
                    "cure-concerts.de"
                )

            sources["secondary"] = (
                "setlist.fm"
            )

            concert["setlistFmUrl"] = (
                item.get("url")
            )

            concert["setlistFmId"] = (
                item.get("id")
            )

            concert["setlistFmVersionId"] = (
                item.get("versionId")
            )

            concert["setlistFmLastUpdated"] = (
                item.get("lastUpdated")
            )

            # ==================================================
            # HISTORICAL DATA
            #
            # Cure Guide is authoritative.
            #
            # setlist.fm may fill a blank but NEVER overwrite
            # an existing Cure Guide value.
            # ==================================================

            for key_name, value in [
                (
                    "city",
                    city_name,
                ),
                (
                    "venue",
                    venue_name,
                ),
                (
                    "country",
                    country_name,
                ),
                (
                    "tour",
                    (
                        item.get("tour")
                        or {}
                    ).get("name"),
                ),
            ]:
                if (
                    not concert.get(
                        key_name
                    )
                    and value
                ):
                    concert[
                        key_name
                    ] = value

            # ==================================================
            # SETLIST
            # ==================================================

            new_songs = songs(
                item
            )

            if new_songs:

                # IMPORTANT:
                #
                # Once a canonical concert has been identified,
                # setlist rows are linked ONLY by concertId.
                #
                # We deliberately do NOT use date + city here,
                # because double shows can occur at the same
                # venue/city/date.
                existing = [
                    row
                    for row in setlists
                    if str(
                        row.get(
                            "concertId"
                        ) or ""
                    )
                    == str(
                        concert["id"]
                    )
                ]

                cure_status = str(
                    concert.get(
                        "setlistConfirmation"
                    )
                    or concert.get(
                        "cureGuideSetlistStatus"
                    )
                    or concert.get(
                        "setlistStatus"
                    )
                    or ""
                ).lower()

                # setlist.fm may enrich a missing,
                # unknown or unconfirmed setlist.
                #
                # A Cure Guide confirmed setlist is protected.
                replace_allowed = (
                    not existing
                    or cure_status
                    in {
                        "",
                        "unknown",
                        "unconfirmed",
                        "community",
                    }
                )

                if replace_allowed:

                    setlists = [
                        row
                        for row in setlists
                        if str(
                            row.get(
                                "concertId"
                            ) or ""
                        )
                        != str(
                            concert["id"]
                        )
                    ]

                    setlists += [
                        {
                            "concertId":
                                concert["id"],

                            "date":
                                event_date,

                            **entry,

                            "countsAsSong":
                                True,

                            "status":
                                "Community",

                            "sourceUrl":
                                item.get(
                                    "url"
                                ),
                        }
                        for entry
                        in new_songs
                    ]

                    concert[
                        "songsPlayed"
                    ] = len(
                        new_songs
                    )

                    concert[
                        "setlistFmStatus"
                    ] = "Community"

                    if not concert.get(
                        "setlistConfirmation"
                    ):
                        concert[
                            "setlistConfirmation"
                        ] = "Unknown"

                    if not concert.get(
                        "setlistStatus"
                    ):
                        concert[
                            "setlistStatus"
                        ] = (
                            concert.get(
                                "setlistConfirmation"
                            )
                            or "Unknown"
                        )

                    enriched_count += 1

                    log_change(
                        changes,
                        concert["id"],
                        event_date,
                        "setlist",
                        len(existing),
                        len(new_songs),
                        item.get("url")
                        or "setlist.fm",
                        "NEW_SETLIST",
                    )

            if (
                index % 10 == 0
                or index == len(items)
            ):
                log(
                    f"[setlist.fm] "
                    f"{year}: "
                    f"{index}/{len(items)} "
                    "processed"
                )

            time.sleep(0.25)

        time.sleep(0.7)

    # ==========================================================
    # SAVE
    # ==========================================================

    save(
        "concerts.json",
        sorted(
            concerts,
            key=lambda x:
                x.get("date")
                or "9999-99-99",
        ),
    )

    save(
        "setlists.json",
        setlists,
    )

    save(
        "changelog.json",
        changes[-5000:],
    )

    state = load(
        "state.json",
        {}
    )

    state[
        "setlistFmLastSync"
    ] = now()

    state[
        "setlistFmMatched"
    ] = matched_count

    state[
        "setlistFmUnmatched"
    ] = unmatched_count

    state[
        "setlistFmAmbiguous"
    ] = ambiguous_count

    state[
        "setlistFmEnriched"
    ] = enriched_count

    save(
        "state.json",
        state,
    )

    log(
        "[setlist.fm] sync completed"
    )

    log(
        "[setlist.fm] summary:",
        matched_count,
        "matched |",
        enriched_count,
        "setlists enriched |",
        unmatched_count,
        "setlist.fm-only ignored |",
        ambiguous_count,
        "ambiguous ignored",
    )


if __name__ == "__main__":
    main()
