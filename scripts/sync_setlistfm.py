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
UA = "STATICURE/4.9 (+https://github.com/pub69500-prog/the-cure-tours-V4)"


# ================================================================
# ALIAS DE VILLES
#
# Cure Concerts Guide reste la référence.
# Ces alias servent UNIQUEMENT à reconnaître qu'un nom setlist.fm
# correspond à la même ville.
# ================================================================

CITY_ALIASES = {
    # Suède
    "gothenburg": "goteborg",
    "goteborg": "goteborg",

    # Bulgarie
    "plovdiv": "plowdiw",
    "plowdiw": "plowdiw",

    # Grèce
    "athens": "athina",
    "athina": "athina",

    # Italie
    "florence": "firenze",
    "firenze": "firenze",

    # Roumanie
    "comuna bontida": "bontida",
    "bontida": "bontida",
}


# ================================================================
# ALIAS DE SALLES / SITES
#
# Également utilisés uniquement pour la comparaison.
# Ils n'écrasent JAMAIS les noms Cure Guide.
# ================================================================

VENUE_ALIASES = {
    # Bulgarie
    "rowing canal": "grebna baza",
    "grebna baza": "grebna baza",

    # Grèce
    "olympic complex": "telekom center athens p5",
    "telekom center athens p5": "telekom center athens p5",

    # Italie
    "ippodromo del visarno": "visarno arena",
    "visarno arena": "visarno arena",

    # Portugal
    "cidade desportiva da maia": "estadio municipal dr jose vieira de carvalho",
    "estadio municipal dr jose vieira de carvalho":
        "estadio municipal dr jose vieira de carvalho",

    # Isle of Wight
    "main stage": "seaclose park",
    "seaclose park": "seaclose park",
}


CORE_ARTISTS = {
    "the cure",
    "easy cure",
    "malice",
}


def log(*args):
    print(*args, flush=True)


def canonical_city(value):
    """
    Normalise le nom d'une ville pour le matching uniquement.
    """
    value = normalize(value)

    return CITY_ALIASES.get(
        value,
        value,
    )


def canonical_venue(value):
    """
    Normalise le nom d'une salle pour le matching uniquement.
    """
    value = normalize(value)

    return VENUE_ALIASES.get(
        value,
        value,
    )


def is_cure_concert(concert):
    """
    Empêche une entrée setlist.fm The Cure d'être associée
    par erreur à une guest appearance.
    """

    if concert.get("isTheCureConcert") is False:
        return False

    if (
        str(
            concert.get("eventType") or ""
        ).strip().lower()
        == "guest appearance"
    ):
        return False

    artist = normalize(
        concert.get("artist")
        or "The Cure"
    )

    return artist in CORE_ARTISTS


def get(path, params, key, retries=4):
    url = (
        API
        + path
        + "?"
        + urllib.parse.urlencode(params)
    )

    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "x-api-key": key,
            "User-Agent": UA,
        },
    )

    for attempt in range(
        1,
        retries + 1,
    ):
        try:
            with urllib.request.urlopen(
                req,
                timeout=30,
            ) as response:

                return json.loads(
                    response
                    .read()
                    .decode("utf-8")
                )

        except urllib.error.HTTPError as exc:

            # Une recherche valide sans résultat peut
            # retourner 404.
            if exc.code == 404:

                log(
                    f"[setlist.fm] "
                    f"no result: {url}"
                )

                return {
                    "setlist": [],
                    "total": 0,
                    "page": 1,
                    "itemsPerPage": 20,
                }

            # Rate limit
            if exc.code == 429:

                retry_after = (
                    exc.headers.get(
                        "Retry-After"
                    )
                )

                try:
                    wait = max(
                        2,
                        int(retry_after),
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    wait = min(
                        60,
                        5 * attempt,
                    )

                log(
                    "[setlist.fm] HTTP 429 — "
                    f"waiting {wait}s "
                    f"(attempt "
                    f"{attempt}/{retries})"
                )

                time.sleep(wait)

                continue

            # Erreur serveur temporaire
            if (
                500 <= exc.code <= 599
                and attempt < retries
            ):
                wait = min(
                    30,
                    3 * attempt,
                )

                log(
                    "[setlist.fm] "
                    f"HTTP {exc.code} — "
                    f"retry in {wait}s"
                )

                time.sleep(wait)

                continue

            body = ""

            try:
                body = (
                    exc.read()
                    .decode(
                        "utf-8",
                        "replace",
                    )[:500]
                )

            except Exception:
                pass

            raise RuntimeError(
                f"setlist.fm HTTP "
                f"{exc.code} for {url}"
                + (
                    f" — {body}"
                    if body
                    else ""
                )
            ) from exc

        except urllib.error.URLError as exc:

            if attempt >= retries:

                raise RuntimeError(
                    "setlist.fm network "
                    f"error for {url}: "
                    f"{exc}"
                ) from exc

            wait = min(
                30,
                3 * attempt,
            )

            log(
                "[setlist.fm] "
                "network error — "
                f"retry in {wait}s: "
                f"{exc}"
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
        f"[setlist.fm] "
        f"scanning year {year}"
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

        items = (
            data.get("setlist")
            or []
        )

        out.extend(items)

        total = int(
            data.get("total")
            or 0
        )

        per_page = int(
            data.get("itemsPerPage")
            or 20
        )

        if not items:
            break

        if (
            page * per_page
            >= total
        ):
            break

        page += 1

        time.sleep(0.7)

    log(
        f"[setlist.fm] "
        f"{year}: "
        f"{len(out)} setlist(s)"
    )

    return out


def songs(item):
    out = []

    sets = (
        (item.get("sets") or {})
        .get("set")
        or []
    )

    for set_block in sets:

        encore = (
            set_block.get(
                "encore"
            )
        )

        section = (
            f"Encore {encore}"
            if encore
            else "Mainset"
        )

        position = 0

        for song in (
            set_block.get("song")
            or []
        ):

            # Intro/tape non comptée
            if song.get("tape"):
                continue

            name = (
                song.get("name")
                or ""
            ).strip()

            if not name:
                continue

            position += 1

            out.append(
                {
                    "section":
                        section,

                    "position":
                        position,

                    "song":
                        name,
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
    V4.9

    Trouve UNIQUEMENT un concert canonique déjà existant.

    Cure Concerts Guide reste la source de référence.

    Ordre de rapprochement :

      1. date + ville normalisée + salle normalisée
      2. date + ville normalisée si résultat unique

    On ne fait PAS de simple date-only si plusieurs événements
    existent ce jour-là.

    Les différences telles que :

      Göteborg / Gothenburg
      Firenze / Florence
      Plowdiw / Plovdiv

    sont reconnues grâce aux alias.
    """

    same_date = [
        c
        for c in concerts
        if (
            c.get("date") == date
            and is_cure_concert(c)
        )
    ]

    if not same_date:
        return None, "no-date"

    city_norm = (
        canonical_city(
            city_name
        )
    )

    venue_norm = (
        canonical_venue(
            venue_name
        )
    )

    # ============================================================
    # 1 — DATE + VILLE + SALLE
    # ============================================================

    exact = [
        c
        for c in same_date
        if (
            canonical_city(
                c.get("city")
            )
            == city_norm

            and

            canonical_venue(
                c.get("venue")
            )
            == venue_norm
        )
    ]

    if len(exact) == 1:

        return (
            exact[0],
            "exact",
        )

    if len(exact) > 1:

        log(
            "[setlist.fm] "
            "ambiguous exact match:",
            date,
            "|",
            city_name,
            "|",
            venue_name,
            "|",
            len(exact),
            "Cure Guide events",
        )

        return (
            None,
            "ambiguous",
        )

    # ============================================================
    # 2 — DATE + VILLE
    #
    # Autorisé seulement si UNIQUE.
    #
    # Cela permet par exemple :
    #
    # Maia :
    # Cidade Desportiva da Maia
    # ↔ Estádio Municipal Dr. José Vieira de Carvalho
    #
    # Newport :
    # Main Stage
    # ↔ Seaclose Park
    # ============================================================

    city_matches = [
        c
        for c in same_date
        if (
            canonical_city(
                c.get("city")
            )
            == city_norm
        )
    ]

    if len(city_matches) == 1:

        return (
            city_matches[0],
            "city",
        )

    if len(city_matches) > 1:

        log(
            "[setlist.fm] "
            "ambiguous city match:",
            date,
            "|",
            city_name,
            "|",
            len(city_matches),
            "Cure Guide events",
        )

        return (
            None,
            "ambiguous",
        )

    # ============================================================
    # 3 — UNIQUE DATE FALLBACK
    #
    # Si Cure Guide ne possède qu'UN SEUL concert The Cure
    # ce jour-là, nous pouvons raisonnablement associer la
    # setlist malgré une différence complète de géographie.
    #
    # MAIS on log explicitement ce rapprochement.
    #
    # Cela reste impossible les jours à plusieurs concerts.
    # ============================================================

    if len(same_date) == 1:

        concert = same_date[0]

        log(
            "[setlist.fm] "
            "unique-date fallback:",
            date,
            "| setlist.fm:",
            city_name or "?",
            "/",
            venue_name or "?",
            "| Cure Guide:",
            concert.get("city")
            or "?",
            "/",
            concert.get("venue")
            or "?",
        )

        return (
            concert,
            "date",
        )

    return (
        None,
        "ambiguous",
    )


def main():

    key = os.getenv(
        "SETLISTFM_API_KEY",
        "",
    ).strip()

    if not key:

        log(
            "[setlist.fm] "
            "SETLISTFM_API_KEY "
            "missing; "
            "synchronization skipped"
        )

        return

    log(
        "[setlist.fm] "
        "sync V4.9 started"
    )

    concerts = load(
        "concerts.json",
        [],
    )

    setlists = load(
        "setlists.json",
        [],
    )

    changes = load(
        "changelog.json",
        [],
    )

    current_year = (
        dt.datetime.now().year
    )

    matched_count = 0
    exact_count = 0
    alias_or_city_count = 0
    date_fallback_count = 0

    unmatched_count = 0
    ambiguous_count = 0
    enriched_count = 0

    # ============================================================
    # ANNÉE COURANTE + ANNÉE PRÉCÉDENTE
    # ============================================================

    for year in (
        current_year - 1,
        current_year,
    ):

        items = year_items(
            year,
            key,
        )

        for index, item in enumerate(
            items,
            1,
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
                item.get("venue")
                or {}
            )

            city = (
                venue.get("city")
                or {}
            )

            country = (
                city.get("country")
                or {}
            )

            city_name = (
                city.get("name")
            )

            venue_name = (
                venue.get("name")
            )

            country_name = (
                country.get("name")
            )

            (
                concert,
                match_type,
            ) = find_concert(
                concerts,
                event_date,
                city_name,
                venue_name,
            )

            # ====================================================
            # AUCUNE CORRESPONDANCE
            #
            # setlist.fm NE CRÉE JAMAIS un concert canonique.
            # ====================================================

            if concert is None:

                if (
                    match_type
                    == "no-date"
                ):
                    unmatched_count += 1

                else:
                    ambiguous_count += 1

                log(
                    "[setlist.fm] "
                    "unmatched — "
                    "NOT added to "
                    "canonical archive:",
                    event_date,
                    "|",
                    city_name or "?",
                    "|",
                    venue_name or "?",
                    "|",
                    item.get("url")
                    or "",
                )

                continue

            matched_count += 1

            if match_type == "exact":

                exact_count += 1

            elif match_type == "city":

                alias_or_city_count += 1

                log(
                    "[setlist.fm] "
                    "matched by canonical city:",
                    event_date,
                    "|",
                    city_name,
                    "|",
                    venue_name,
                    "→",
                    concert.get("city"),
                    "|",
                    concert.get("venue"),
                )

            elif match_type == "date":

                date_fallback_count += 1

            # ====================================================
            # SOURCES
            # ====================================================

            sources = (
                concert.setdefault(
                    "sources",
                    {},
                )
            )

            # Cure Guide reste source primaire.
            if not sources.get(
                "primary"
            ):
                sources[
                    "primary"
                ] = (
                    "cure-concerts.de"
                )

            sources[
                "secondary"
            ] = (
                "setlist.fm"
            )

            concert[
                "setlistFmUrl"
            ] = (
                item.get("url")
            )

            concert[
                "setlistFmId"
            ] = (
                item.get("id")
            )

            concert[
                "setlistFmVersionId"
            ] = (
                item.get(
                    "versionId"
                )
            )

            concert[
                "setlistFmLastUpdated"
            ] = (
                item.get(
                    "lastUpdated"
                )
            )

            # ====================================================
            # DONNÉES HISTORIQUES
            #
            # setlist.fm remplit seulement les cases vides.
            # Il n'écrase jamais Cure Guide.
            # ====================================================

            for (
                key_name,
                value,
            ) in [

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

            # ====================================================
            # SETLIST
            # ====================================================

            new_songs = songs(
                item
            )

            if new_songs:

                # Une fois le concert identifié,
                # on travaille UNIQUEMENT avec concertId.
                existing = [
                    row
                    for row in setlists
                    if (
                        str(
                            row.get(
                                "concertId"
                            )
                            or ""
                        )
                        ==
                        str(
                            concert["id"]
                        )
                    )
                ]

                cure_status = str(
                    concert.get(
                        "setlistConfirmation"
                    )
                    or
                    concert.get(
                        "cureGuideSetlistStatus"
                    )
                    or
                    concert.get(
                        "setlistStatus"
                    )
                    or
                    ""
                ).lower()

                # Cure Guide Confirmed est protégé.
                replace_allowed = (
                    not existing
                    or
                    cure_status
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
                        for row
                        in setlists
                        if (
                            str(
                                row.get(
                                    "concertId"
                                )
                                or ""
                            )
                            !=
                            str(
                                concert["id"]
                            )
                        )
                    ]

                    setlists += [
                        {
                            "concertId":
                                concert[
                                    "id"
                                ],

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
                    ] = (
                        len(
                            new_songs
                        )
                    )

                    concert[
                        "setlistFmStatus"
                    ] = (
                        "Community"
                    )

                    if not concert.get(
                        "setlistConfirmation"
                    ):
                        concert[
                            "setlistConfirmation"
                        ] = (
                            "Unknown"
                        )

                    if not concert.get(
                        "setlistStatus"
                    ):
                        concert[
                            "setlistStatus"
                        ] = (
                            concert.get(
                                "setlistConfirmation"
                            )
                            or
                            "Unknown"
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
                        or
                        "setlist.fm",
                        "NEW_SETLIST",
                    )

            if (
                index % 10 == 0
                or
                index == len(items)
            ):

                log(
                    "[setlist.fm] "
                    f"{year}: "
                    f"{index}/"
                    f"{len(items)} "
                    "processed"
                )

            time.sleep(0.25)

        time.sleep(0.7)

    # ============================================================
    # SAUVEGARDE
    # ============================================================

    save(
        "concerts.json",
        sorted(
            concerts,
            key=lambda x:
                x.get("date")
                or
                "9999-99-99",
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
        {},
    )

    state[
        "setlistFmLastSync"
    ] = now()

    state[
        "setlistFmMatched"
    ] = matched_count

    state[
        "setlistFmExactMatched"
    ] = exact_count

    state[
        "setlistFmCanonicalCityMatched"
    ] = alias_or_city_count

    state[
        "setlistFmDateFallbackMatched"
    ] = date_fallback_count

    state[
        "setlistFmUnmatched"
    ] = unmatched_count

    state[
        "setlistFmAmbiguous"
    ] = ambiguous_count

    state[
        "setlistFmEnriched"
    ] = enriched_count

    state[
        "setlistFmSyncVersion"
    ] = "4.9"

    save(
        "state.json",
        state,
    )

    # ============================================================
    # RÉSUMÉ
    # ============================================================

    log(
        "[setlist.fm] "
        "sync V4.9 completed"
    )

    log(
        "[setlist.fm] summary:",
        matched_count,
        "matched |",
        exact_count,
        "exact |",
        alias_or_city_count,
        "canonical-city |",
        date_fallback_count,
        "date-fallback |",
        enriched_count,
        "setlists enriched |",
        unmatched_count,
        "setlist.fm-only ignored |",
        ambiguous_count,
        "ambiguous ignored",
    )


if __name__ == "__main__":
    main()
