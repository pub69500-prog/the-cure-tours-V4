#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser

from bs4 import BeautifulSoup
from common import load, save, log_change, now, normalize


BASE = "https://www.cure-concerts.de"
UA = "STATICURE-archive-sync/4.6 (+https://github.com/pub69500-prog/the-cure-tours-V4)"

TITLE_RE = re.compile(
    r"^(?P<artist>.*?)\s+"
    r"(?P<date>\d{4}-(?:\d{2}|xx)-(?:\d{2}|xx))\s+"
    r"(?P<city>.+?)\s+-\s+(?P<venue>.+?)\s+\((?P<country>[^)]+)\)"
)

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

# Artistes considérés comme faisant partie de l'historique
# principal de The Cure.
CORE_ARTISTS = {
    "the cure",
    "easy cure",
    "malice",
}

_ROBOTS = None
_ROBOTS_READY = False


def _log(*args):
    print(*args, flush=True)


def _respect_robots():
    return os.getenv(
        "CUREGUIDE_RESPECT_ROBOTS",
        "true"
    ).lower() not in {
        "0",
        "false",
        "no",
    }


def _load_robots_once():
    global _ROBOTS, _ROBOTS_READY

    if _ROBOTS_READY:
        return _ROBOTS

    _ROBOTS_READY = True

    if not _respect_robots():
        _log(
            "[cureguide] robots.txt check "
            "disabled by configuration"
        )
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

        with urllib.request.urlopen(
            req,
            timeout=8
        ) as response:
            body = response.read().decode(
                "utf-8",
                "replace"
            )

        rp.parse(body.splitlines())

        _ROBOTS = rp

        _log(
            "[cureguide] robots.txt loaded once"
        )

    except Exception as exc:
        _ROBOTS = None

        _log(
            "[cureguide] WARNING: "
            f"robots.txt unavailable ({exc}); "
            "continuing"
        )

    return _ROBOTS


def allowed(url):
    if not _respect_robots():
        return True

    rp = _load_robots_once()

    return (
        True
        if rp is None
        else rp.can_fetch(UA, url)
    )


def fetch(url):
    if not allowed(url):
        raise RuntimeError(
            f"robots.txt interdit {url}"
        )

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept":
                "text/html,application/xhtml+xml",
            "Accept-Language":
                "en,fr;q=0.8",
        },
    )

    with urllib.request.urlopen(
        req,
        timeout=20
    ) as response:
        return response.read().decode(
            "utf-8",
            "replace"
        )


def _inline_confirmation_hint(anchor):
    """
    Déduit prudemment le statut de confirmation
    depuis les informations HTML explicites
    présentes sur les pages année / updates.

    Si aucun indice suffisamment fiable n'est
    présent, retourne Unknown.
    """

    bits = []

    node = anchor

    for _ in range(4):
        if node is None:
            break

        bits += list(
            node.get("class") or []
        )

        bits.append(
            node.get("style") or ""
        )

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

    if (
        "confirmed" in blob
        and "unconfirmed" not in blob
    ):
        return "Confirmed"

    # On accepte uniquement les couleurs
    # explicitement présentes dans le HTML.

    if re.search(
        r"color\s*:\s*"
        r"(?:grey|gray|#(?:777|888|999|aaa|bbb)\b)",
        blob,
    ):
        return "Unconfirmed"

    if re.search(
        r"color\s*:\s*"
        r"(?:white|#fff(?:fff)?\b)",
        blob,
    ):
        return "Confirmed"

    return "Unknown"


def candidates():
    year = dt.datetime.now().year

    pages = [
        f"{BASE}/main/updates.php",
        f"{BASE}/main/{year}.php",
        f"{BASE}/main/{year - 1}.php",
    ]

    found = {}

    for page in pages:

        _log(
            f"[cureguide] scanning {page}"
        )

        try:
            soup = BeautifulSoup(
                fetch(page),
                "html.parser"
            )

            for a in soup.find_all(
                "a",
                href=True
            ):
                url = urllib.parse.urljoin(
                    page,
                    a["href"]
                )

                if re.search(
                    r"/concerts/"
                    r"\d{4}-(?:\d{2}|xx)-"
                    r"(?:\d{2}|xx)\.php$",
                    url,
                ):
                    hint = (
                        _inline_confirmation_hint(a)
                    )

                    previous = found.get(
                        url,
                        "Unknown"
                    )

                    # Ne jamais remplacer un statut
                    # explicite par Unknown.
                    found[url] = (
                        hint
                        if hint != "Unknown"
                        else previous
                    )

        except Exception as exc:
            _log(
                "[cureguide] ERROR scanning "
                f"{page}: {exc}"
            )

        time.sleep(0.8)

    return [
        (url, found[url])
        for url in sorted(found)
    ]


def _all_marker_text(soup):
    """
    Cure Concerts Guide utilise notamment
    des images avec des labels comme
    'setlist unknown'.

    BeautifulSoup.get_text() n'inclut pas
    les attributs alt des images, donc
    on les inspecte séparément.
    """

    parts = []

    for img in soup.find_all("img"):

        for attr in (
            "alt",
            "title",
        ):
            value = img.get(attr)

            if value:
                parts.append(
                    str(value)
                )

    for tag in soup.find_all(True):

        title = tag.get("title")

        if title:
            parts.append(
                str(title)
            )

    return " ".join(parts).lower()


def _confirmation_status(
    soup,
    text,
    songs_played
):
    """
    Conserve séparément :
      - confirmation du concert
      - confirmation de la setlist

    Règle Cure Concerts Guide :
      - setlists blanches = confirmées
      - setlists grises = non confirmées

    Si aucun marqueur suffisamment fiable
    n'est présent, le statut reste Unknown.
    """

    markers = _all_marker_text(soup)

    combined = (
        markers
        + " "
        + text.lower()
    )

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
        or
        "setlist unconfirmed" in combined
    ):
        setlist_confirmation = (
            "Unconfirmed"
            if has_named_setlist
            else "Unknown"
        )

    elif (
        "setlist confirmed"
        in combined
    ):
        setlist_confirmation = (
            "Confirmed"
        )

    else:
        # L'absence de marqueur ne suffit pas
        # pour déclarer la setlist confirmée.
        setlist_confirmation = (
            "Unknown"
        )

    if (
        "concert unconfirmed" in combined
        or
        "concert unknown" in combined
    ):
        concert_confirmation = (
            "Unconfirmed"
        )

    elif (
        "concert confirmed"
        in combined
    ):
        concert_confirmation = (
            "Confirmed"
        )

    else:
        concert_confirmation = (
            "Unknown"
        )

    return (
        concert_confirmation,
        setlist_confirmation
    )


def _classify_artist(artist):
    """
    V4.6

    Détermine si l'événement est un concert
    principal Cure ou une apparition chez
    un autre artiste.

    Exemple :
      artist = "The Cure"
        -> Concert

      artist = "Olivia Rodrigo"
        -> Guest appearance

    Les apparitions restent dans l'archive,
    mais seront exclues des statistiques
    principales par build_site.py.
    """

    cleaned = (
        str(artist or "The Cure")
        .strip()
        .rstrip(":")
        .strip()
    )

    normalized = cleaned.lower()

    is_core = (
        normalized in CORE_ARTISTS
    )

    if is_core:
        event_type = "Concert"
    else:
        event_type = (
            "Guest appearance"
        )

    return (
        cleaned,
        is_core,
        event_type,
    )


def parse(
    url,
    html,
    concert_hint="Unknown"
):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    title = (
        soup.title.get_text(
            " ",
            strip=True
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

    # ----------------------------------------------------------
    # ARTISTE / VILLE / SALLE / PAYS
    # ----------------------------------------------------------

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
                    m["city"].strip(),

                "venue":
                    m["venue"].strip(),

                "country":
                    m["country"].strip(),
            }
        )

    # ----------------------------------------------------------
    # V4.6 — CLASSIFICATION
    # ----------------------------------------------------------

    artist, is_core, event_type = (
        _classify_artist(
            out.get("artist")
        )
    )

    out["artist"] = artist

    out["isTheCureConcert"] = (
        is_core
    )

    out["guestAppearance"] = (
        not is_core
    )

    out["eventType"] = (
        event_type
    )

    # ----------------------------------------------------------
    # DONNÉES DU CONCERT
    # ----------------------------------------------------------

    lines = text.splitlines()

    for i, line in enumerate(lines):

        for label, key in (
            LABELS.items()
        ):

            if (
                line.rstrip(":").lower()
                == label.lower()
                and i + 1 < len(lines)
            ):
                value = (
                    lines[i + 1]
                )

                if key in {
                    "songsPlayed",
                    "attendance",
                    "concertCapacity",
                    "setLengthMin",
                }:

                    # Le champ doit contenir
                    # au moins un chiffre.
                    #
                    # Cela évite notamment :
                    # int('')
                    number = re.search(
                        r"\d[\d,']*",
                        value
                    )

                    if number:
                        value = int(
                            number
                            .group(0)
                            .replace(",", "")
                            .replace("'", "")
                        )

                    else:
                        continue

                out[key] = value

    # ----------------------------------------------------------
    # CONFIRMATION
    # ----------------------------------------------------------

    (
        page_concert_status,
        setlist_status,
    ) = _confirmation_status(
        soup,
        text,
        out.get("songsPlayed")
    )

    # Un statut explicite trouvé sur la page
    # du concert est prioritaire.
    #
    # Sinon on utilise l'indice éventuel
    # trouvé sur la page année / updates.

    out["concertConfirmation"] = (
        page_concert_status
        if page_concert_status
        != "Unknown"
        else concert_hint
    )

    out["setlistConfirmation"] = (
        setlist_status
    )

    # Compatibilité avec l'interface
    # actuelle.
    out["setlistStatus"] = (
        setlist_status
    )

    return out


def main():

    _log(
        "[cureguide] sync V4.6 started"
    )

    _load_robots_once()

    concerts = load(
        "concerts.json",
        []
    )

    changes = load(
        "changelog.json",
        []
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

    items = candidates()

    _log(
        f"[cureguide] "
        f"{len(items)} candidate pages"
    )

    for index, (
        url,
        concert_hint
    ) in enumerate(
        items,
        1
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
                concert_hint
            )

        except Exception as exc:
            _log(
                "[cureguide] skip "
                f"{url}: {exc}"
            )

            continue

        old = byurl.get(url)

        # ------------------------------------------------------
        # Recherche d'un concert déjà existant
        # ------------------------------------------------------

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

        # ------------------------------------------------------
        # NOUVEL ÉVÉNEMENT
        # ------------------------------------------------------

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

        # ------------------------------------------------------
        # MISE À JOUR D'UN ÉVÉNEMENT EXISTANT
        # ------------------------------------------------------

        else:

            for key, value in (
                patch.items()
            ):

                if (
                    key in {
                        "id",
                        "sources",
                    }
                    or value in (
                        None,
                        "",
                    )
                ):
                    continue

                if key == "scrapedAt":
                    old[key] = value
                    continue

                # Ne jamais remplacer un statut
                # Confirmed / Unconfirmed existant
                # par Unknown.

                if (
                    key in {
                        "concertConfirmation",
                        "setlistConfirmation",
                        "setlistStatus",
                    }

                    and value
                    == "Unknown"

                    and old.get(key)
                    in {
                        "Confirmed",
                        "Unconfirmed",
                    }
                ):
                    continue

                if old.get(key) != value:

                    # Les changements de classification
                    # sont eux aussi considérés comme des
                    # changements de statut.

                    if key in {
                        "concertConfirmation",
                        "setlistConfirmation",
                        "setlistStatus",
                        "eventType",
                        "isTheCureConcert",
                        "guestAppearance",
                    }:
                        change_type = (
                            "STATUS_CHANGE"
                        )

                    elif (
                        old["year"]
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
                {}
            )["primary"] = (
                "cure-concerts.de"
            )

            old[
                "confirmationSource"
            ] = (
                "cure-concerts.de"
            )

        time.sleep(0.8)

    # ----------------------------------------------------------
    # SAUVEGARDE
    # ----------------------------------------------------------

    save(
        "concerts.json",
        sorted(
            byid.values(),
            key=lambda concert:
                concert["date"]
        ),
    )

    save(
        "changelog.json",
        changes[-5000:]
    )

    state = load(
        "state.json",
        {}
    )

    state[
        "cureGuideLastSync"
    ] = now()

    state[
        "cureGuideCandidates"
    ] = len(items)

    state[
        "cureGuideVersion"
    ] = "4.6"

    save(
        "state.json",
        state
    )

    _log(
        "[cureguide] sync V4.6 completed"
    )


if __name__ == "__main__":
    main()
