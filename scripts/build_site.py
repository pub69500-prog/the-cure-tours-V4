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

CORE_ARTISTS = {"the cure", "easy cure", "malice"}


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "oui", "y"}


def normalize_artist(value):
    return (
        str(value or "The Cure")
        .strip()
        .rstrip(":")
        .strip()
        .lower()
    )


def classify_event(c):
    """
    V4.7

    Distingue les vrais concerts Cure des apparitions
    chez d'autres artistes.

    IMPORTANT :
    "The Cure live concert" doit être considéré comme
    un concert de The Cure et non comme une apparition.
    """

    raw_artist = (
        str(c.get("artist") or "The Cure")
        .strip()
        .rstrip(":")
        .strip()
    )

    artist_norm = normalize_artist(raw_artist)

    # ============================================================
    # THE CURE
    # ============================================================

    if (
        artist_norm == "the cure"
        or artist_norm.startswith("the cure ")
    ):
        return "The Cure", True, "Concert"

    # ============================================================
    # EASY CURE
    # ============================================================

    if (
        artist_norm == "easy cure"
        or artist_norm.startswith("easy cure ")
    ):
        return "Easy Cure", True, "Concert"

    # ============================================================
    # MALICE
    # ============================================================

    if (
        artist_norm == "malice"
        or artist_norm.startswith("malice ")
    ):
        return "Malice", True, "Concert"

    # ============================================================
    # SÉCURITÉ VIA LE TITRE DE LA PAGE
    #
    # Certaines données V4.6 peuvent avoir un champ "artist"
    # incorrect alors que le titre Cure Concerts Guide indique
    # clairement qu'il s'agit d'un concert Cure.
    # ============================================================

    page_title = (
        str(c.get("pageTitle") or "")
        .strip()
        .lower()
    )

    if "the cure live concert" in page_title:
        return "The Cure", True, "Concert"

    if "easy cure live concert" in page_title:
        return "Easy Cure", True, "Concert"

    if "malice live concert" in page_title:
        return "Malice", True, "Concert"

    # ============================================================
    # ARTISTE EXTÉRIEUR
    #
    # Seulement ici l'événement devient une apparition.
    # Exemple : prestation avec Olivia Rodrigo.
    # ============================================================

    return (
        raw_artist or "Unknown",
        False,
        "Guest appearance",
    )


def clean_song_rows(rows):
    result = []

    for row in rows:
        song = row.get("song")

        if not song:
            continue

        if row.get("countsAsSong", True) is False:
            continue

        result.append(
            {
                "section": row.get("section") or "Mainset",
                "position": row.get("position"),
                "song": song,
                "status": row.get("status") or "Unknown",
                "sourceUrl": row.get("sourceUrl"),
            }
        )

    def section_rank(name):
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
            x.get("position")
            if isinstance(x.get("position"), int)
            else 9999,
        )
    )

    return result


def build_frontend_concerts(concerts, setlists):
    by_concert = defaultdict(list)
    by_date = defaultdict(list)

    for row in setlists:
        cid = row.get("concertId")

        if cid:
            by_concert[str(cid)].append(row)

        if row.get("date"):
            by_date[row["date"]].append(row)

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

        rows = by_concert.get(
            canonical_id,
            [],
        )

        if not rows and c.get("date"):
            same_date = by_date.get(
                c["date"],
                [],
            )

            concert_ids = {
                str(x.get("concertId") or "")
                for x in same_date
            }

            if len(concert_ids) <= 1:
                rows = same_date

        setlist = clean_song_rows(rows)

        songs_played = c.get(
            "songsPlayed"
        )

        if songs_played is None and setlist:
            songs_played = len(setlist)

        artist, is_core, event_type = classify_event(c)

        capacity = c.get(
            "concertCapacity"
        )

        if capacity is None:
            capacity = c.get(
                "capacity"
            )

        if capacity is None:
            capacity = c.get(
                "generalVenueCapacity"
            )

        item = {
            "id":
                frontend_id,

            "date":
                c.get("date"),

            "year":
                c.get("year"),

            "city":
                c.get("city"),

            "venue":
                c.get("venue"),

            "country":
                c.get("country"),

            "tour":
                c.get("tour"),

            "songsPlayed":
                songs_played,

            "attendance":
                c.get("attendance"),

            "capacity":
                capacity,

            "soldOut":
                as_bool(
                    c.get("soldOut")
                ),

            "dow":
                c.get("dayOfWeek")
                or c.get("dow"),

            "address":
                c.get("venueAddress")
                or c.get("address"),

            "setlist":
                setlist,

            "canonicalId":
                canonical_id,

            # ====================================================
            # CLASSIFICATION V4.7
            # ====================================================

            "artist":
                artist,

            "eventType":
                event_type,

            "isTheCureConcert":
                is_core,

            "guestAppearance":
                not is_core,

            # ====================================================

            "event":
                c.get("event"),

            "setLengthMin":
                c.get("setLengthMin"),

            "setTime":
                c.get("setTime"),

            "curfew":
                c.get("curfew"),

            "sourceUrl":
                c.get("sourceUrl"),

            "setlistFmUrl":
                c.get("setlistFmUrl"),

            "concertConfirmation":
                c.get("concertConfirmation")
                or "Unknown",

            "setlistConfirmation":
                c.get("setlistConfirmation")
                or c.get("setlistStatus")
                or "Unknown",

            "confirmationSource":
                c.get("confirmationSource"),

            "scrapedAt":
                c.get("scrapedAt"),
        }

        frontend.append(item)

    return frontend


def write_json(path: Path, value):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def main():

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

    state = load(
        "state.json",
        {},
    )

    if not SITE.exists():
        raise SystemExit(
            "[build] ERROR: site/ is missing"
        )

    if DIST.exists():
        shutil.rmtree(DIST)

    # ============================================================
    # COPIE DU FRONTEND
    # ============================================================

    shutil.copytree(
        SITE,
        DIST,
    )

    data_dir = DIST / "data"

    data_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ============================================================
    # CONSTRUCTION DES DONNÉES FRONTEND
    # ============================================================

    frontend_concerts = build_frontend_concerts(
        concerts,
        setlists,
    )

    # Fichier utilisé directement par l'interface
    write_json(
        data_dir / "concerts.json",
        frontend_concerts,
    )

    # Données canoniques
    write_json(
        data_dir / "canonical-concerts.json",
        concerts,
    )

    write_json(
        data_dir / "setlists.json",
        setlists,
    )

    write_json(
        data_dir / "changelog.json",
        changes,
    )

    write_json(
        data_dir / "state.json",
        state,
    )

    # ============================================================
    # STATISTIQUES V4.7
    #
    # Les statistiques principales comprennent uniquement :
    #
    # - The Cure
    # - Easy Cure
    # - Malice
    #
    # Les véritables apparitions chez d'autres artistes restent
    # visibles dans l'archive mais sont exclues des statistiques
    # principales.
    # ============================================================

    core_concerts = [
        c
        for c in concerts
        if classify_event(c)[1]
    ]

    guest_appearances = [
        c
        for c in concerts
        if not classify_event(c)[1]
    ]

    core_ids = {
        str(c.get("id") or "")
        for c in core_concerts
    }

    # ============================================================
    # CONCERTS PAR ANNÉE
    # ============================================================

    years = Counter(
        c.get("year")
        for c in core_concerts
        if c.get("year")
    )

    # ============================================================
    # PAYS
    # ============================================================

    countries = Counter(
        c.get("country")
        for c in core_concerts
        if c.get("country")
    )

    # ============================================================
    # SALLES
    # ============================================================

    venues = Counter(
        c.get("venue")
        for c in core_concerts
        if c.get("venue")
    )

    # ============================================================
    # TITRES JOUÉS
    #
    # IMPORTANT :
    # seules les chansons appartenant aux vrais concerts Cure
    # participent au classement.
    # ============================================================

    songs = Counter(
        x.get("song")
        for x in setlists

        if x.get(
            "countsAsSong",
            True,
        )

        and str(
            x.get("concertId") or ""
        ) in core_ids

        and x.get("song")

        and not str(
            x.get("song")
        ).startswith("[")
    )

    # ============================================================
    # STATISTIQUES GLOBALES
    # ============================================================

    stats = {

        # Vrais concerts Cure / Easy Cure / Malice
        "concerts":
            len(core_concerts),

        # Véritables apparitions chez d'autres artistes
        "guestAppearances":
            len(guest_appearances),

        # Ensemble des événements conservés
        "archiveEvents":
            len(concerts),

        # Nombre d'événements frontend
        "frontendConcerts":
            len(frontend_concerts),

        # Nombre brut de lignes de setlists
        "setlistEntries":
            len(setlists),

        "years":
            dict(
                sorted(
                    years.items()
                )
            ),

        "countries":
            countries.most_common(30),

        "venues":
            venues.most_common(30),

        "songs":
            songs.most_common(100),

        # ========================================================
        # CONFIRMATIONS CURE CONCERTS GUIDE
        # ========================================================

        "confirmation": {

            "concertsConfirmed":
                sum(
                    1
                    for c in core_concerts
                    if c.get(
                        "concertConfirmation"
                    ) == "Confirmed"
                ),

            "concertsUnconfirmed":
                sum(
                    1
                    for c in core_concerts
                    if c.get(
                        "concertConfirmation"
                    ) == "Unconfirmed"
                ),

            "setlistsConfirmed":
                sum(
                    1
                    for c in core_concerts
                    if c.get(
                        "setlistConfirmation"
                    ) == "Confirmed"
                ),

            "setlistsUnconfirmed":
                sum(
                    1
                    for c in core_concerts
                    if c.get(
                        "setlistConfirmation"
                    ) == "Unconfirmed"
                ),
        },

        "generatedAt":
            dt.datetime.now(
                dt.timezone.utc
            ).isoformat(),

        "lastSync":
            state.get("lastSync")
            or state.get(
                "cureGuideLastSync"
            )
            or state.get(
                "setlistFmLastSync"
            ),
    }

    write_json(
        data_dir / "stats.json",
        stats,
    )

    # ============================================================
    # CONTRÔLES DE COHÉRENCE
    # ============================================================

    if len(frontend_concerts) != len(concerts):
        raise SystemExit(
            "[build] ERROR: "
            f"frontend count {len(frontend_concerts)} "
            f"!= canonical count {len(concerts)}"
        )

    malformed = [
        c["id"]
        for c in frontend_concerts
        if not isinstance(
            c.get("setlist"),
            list,
        )
    ]

    if malformed:
        raise SystemExit(
            "[build] ERROR: "
            "malformed frontend setlist data"
        )

    # ============================================================
    # RÉSUMÉ
    # ============================================================

    print(
        "[build] V4.7 dist ready:",
        len(core_concerts),
        "Cure concerts |",
        len(guest_appearances),
        "guest appearances |",
        len(frontend_concerts),
        "archive events |",
        sum(
            len(c["setlist"])
            for c in frontend_concerts
            if c.get(
                "isTheCureConcert"
            )
        ),
        "Cure performed-song entries",
    )

    # ============================================================
    # DIAGNOSTIC V4.7
    #
    # On affiche dans le log chaque événement encore considéré
    # comme une apparition. Cela permettra de repérer immédiatement
    # une nouvelle erreur de classification.
    # ============================================================

    for c in guest_appearances:
        print(
            "[build] guest appearance:",
            c.get("date"),
            "| artist:",
            c.get("artist"),
            "| city:",
            c.get("city"),
            "| venue:",
            c.get("venue"),
        )


if __name__ == "__main__":
    main()
