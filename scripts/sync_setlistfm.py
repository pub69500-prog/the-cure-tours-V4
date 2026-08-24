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
UA = "STATICURE/4.9.1 (+https://github.com/pub69500-prog/the-cure-tours-V4)"


# ================================================================
# ALIAS DE VILLES
#
# Cure Concerts Guide reste la référence.
# Ces alias servent UNIQUEMENT au rapprochement avec setlist.fm.
# Les valeurs enregistrées par Cure Guide ne sont jamais remplacées.
# ================================================================

CITY_ALIASES = {
    # Suède
    "gothenburg": "goteborg",
    "goteborg": "goteborg",

    # Bulgarie
    "plovdiv": "plowdiw",
    "plowdiw": "plowdiw",

    # Grèce
    "athens": "athina athens",
    "athina": "athina athens",
    "athina athens": "athina athens",

    # Italie
    "florence": "firenze",
    "firenze": "firenze",

    # Roumanie
    "comuna bontida": "bontida cluj napoca",
    "bontida": "bontida cluj napoca",
    "bontida cluj napoca": "bontida cluj napoca",

    # Royaume-Uni / Isle of Wight
    "newport": "newport isle of wight",
    "newport isle of wight": "newport isle of wight",

    # Écosse / Edinburgh Summer Sessions
    "ingliston": "ingliston edinburgh",
    "ingliston edinburgh": "ingliston edinburgh",

    # Portugal
    "maia": "maia porto",
    "maia porto": "maia porto",
}


# ================================================================
# ALIAS DE SALLES / SITES
#
# Utilisés uniquement pour la comparaison.
# Ils n'écrasent jamais les noms provenant de Cure Guide.
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
    "cidade desportiva da maia":
        "estadio municipal dr jose vieira de carvalho",

    "estadio municipal dr jose vieira de carvalho":
        "estadio municipal dr jose vieira de carvalho",

    # Écosse / Edinburgh Summer Sessions
    "royal highland centre showground": "royal highland showgrounds",
    "royal highland showgrounds": "royal highland showgrounds",

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
    Normalise une ville uniquement pour le matching.
    """
    value = normalize(value)

    return CITY_ALIASES.get(
        value,
        value,
    )


def canonical_venue(value):
    """
    Normalise une salle uniquement pour le matching.
    """
    value = normalize(value)

    return VENUE_ALIASES.get(
        value,
        value,
    )


def is_cure_concert(concert):
    """
    Empêche une entrée setlist.fm The Cure d'être associée
    à une apparition chez un autre artiste.
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


# ================================================================
# HTTP
# ================================================================

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
                    f"[setlist.fm] no result: {url}"
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
                    f"(attempt {attempt}/{retries})"
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


# ================================================================
# RÉCUPÉRATION PAR ANNÉE
# ================================================================

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


# ================================================================
# SETLIST
# ================================================================

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

            # Les bandes / intros ne sont pas
            # comptées comme chansons interprétées.
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


# ================================================================
# MATCHING CURE GUIDE ↔ SETLIST.FM
# ================================================================

def find_concert(
    concerts,
    date,
    city_name,
    venue_name,
):
    """
    V4.9.1

    Cure Concerts Guide possède l'événement canonique.

    setlist.fm ne peut enrichir qu'un concert Cure déjà présent.

    Ordre de rapprochement :

      1. date + ville normalisée + salle normalisée
      2. date + ville normalisée, uniquement si unique

    IMPORTANT :
    Aucun rapprochement par date seule.

    Cela protège les journées comportant plusieurs concerts,
    plusieurs shows ou plusieurs événements au même endroit.
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

        return (
            None,
            "no-date",
        )

    city_norm = canonical_city(
        city_name
    )

    venue_norm = canonical_venue(
        venue_name
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
    # Autorisé uniquement si un seul concert Cure Guide
    # correspond à cette ville ce jour-là.
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
    # PAS DE DATE-ONLY FALLBACK
    # ============================================================

    return (
        None,
        "ambiguous",
    )


# ================================================================
# SYNCHRONISATION
# ================================================================

def main():

    key = os.getenv(
        "SETLISTFM_API_KEY",
        "",
    ).strip()

    if not key:

        log(
            "[setlist.fm] "
            "SETLISTFM_API_KEY missing; "
            "synchronization skipped"
        )

        return

    log(
        "[setlist.fm] "
        "sync V4.9.1 started"
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
    canonical_city_count = 0

    unmatched_count = 0
    ambiguous_count = 0
    enriched_count = 0

    # ============================================================
    # ANNÉE PRÉCÉDENTE + ANNÉE COURANTE
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
            # setlist.fm ne crée jamais de concert canonique.
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

            if match_type == "exact":

                exact_count += 1

            elif match_type == "city":

                canonical_city_count += 1

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

            # ====================================================
            # SOURCES
            # ====================================================

            sources = (
                concert.setdefault(
                    "sources",
                    {},
                )
            )

            # Cure Guide reste la source principale.
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
            # setlist.fm remplit seulement une valeur vide.
            # Il n'écrase jamais Cure Concerts Guide.
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
                # seules les lignes portant le même concertId
                # sont concernées.
                #
                # Important pour les doubles shows.
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

                # Une setlist Cure Guide confirmée est protégée.
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
    ] = canonical_city_count

    # Toujours zéro dans cette version :
    # le rapprochement date-only est interdit.
    state[
        "setlistFmDateFallbackMatched"
    ] = 0

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
    ] = "4.9.1"

    save(
        "state.json",
        state,
    )

    # ============================================================
    # RÉSUMÉ
    # ============================================================

    log(
        "[setlist.fm] "
        "sync V4.9.1 completed"
    )

    log(
        "[setlist.fm] summary:",
        matched_count,
        "matched |",
        exact_count,
        "exact |",
        canonical_city_count,
        "canonical-city |",
        0,
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
