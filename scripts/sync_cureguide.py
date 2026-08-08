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
UA = "STATICURE-archive-sync/4.2 (+https://github.com/pub69500-prog/the-cure-tours-V4)"

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

_ROBOTS = None
_ROBOTS_READY = False


def _log(*args):
    print(*args, flush=True)


def _respect_robots():
    return os.getenv("CUREGUIDE_RESPECT_ROBOTS", "true").lower() not in {
        "0", "false", "no"
    }


def _load_robots_once():
    """Charge robots.txt UNE seule fois par exécution, avec timeout."""
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
            headers={"User-Agent": UA, "Accept": "text/plain,*/*;q=0.1"},
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            body = response.read().decode("utf-8", "replace")
        rp.parse(body.splitlines())
        _ROBOTS = rp
        _log("[cureguide] robots.txt loaded once")
    except Exception as exc:
        # Même comportement de repli que la V4 initiale : ne pas rester bloqué
        # si robots.txt est temporairement indisponible.
        _ROBOTS = None
        _log(f"[cureguide] WARNING: robots.txt unavailable ({exc}); continuing")

    return _ROBOTS


def allowed(url):
    if not _respect_robots():
        return True
    rp = _load_robots_once()
    return True if rp is None else rp.can_fetch(UA, url)


def fetch(url):
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
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read().decode("utf-8", "replace")


def candidates():
    year = dt.datetime.now().year
    pages = [
        f"{BASE}/main/updates.php",
        f"{BASE}/main/{year}.php",
        f"{BASE}/main/{year - 1}.php",
    ]

    urls = set()

    for page in pages:
        _log(f"[cureguide] scanning {page}")
        try:
            soup = BeautifulSoup(fetch(page), "html.parser")
            for a in soup.find_all("a", href=True):
                url = urllib.parse.urljoin(page, a["href"])
                if re.search(
                    r"/concerts/\d{4}-(?:\d{2}|xx)-(?:\d{2}|xx)\.php$",
                    url,
                ):
                    urls.add(url)
        except Exception as exc:
            _log(f"[cureguide] ERROR scanning {page}: {exc}")

        time.sleep(0.8)

    return sorted(urls)


def parse(url, html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = "\n".join(
        x.strip() for x in soup.get_text("\n").splitlines() if x.strip()
    )

    m = TITLE_RE.search(title) or TITLE_RE.search(text)
    date_match = re.search(
        r"(\d{4}-(?:\d{2}|xx)-(?:\d{2}|xx))",
        url,
    )
    if not date_match:
        raise ValueError(f"date introuvable dans l'URL: {url}")

    date = date_match.group(1)

    out = {
        "id": None,
        "date": date,
        "year": int(date[:4]),
        "sourceUrl": url,
        "scrapedAt": now(),
        "pageTitle": title,
        "sources": {"primary": "cure-concerts.de"},
    }

    if m:
        out.update(
            {
                "artist": m["artist"].strip() or "The Cure",
                "city": m["city"].strip(),
                "venue": m["venue"].strip(),
                "country": m["country"].strip(),
            }
        )

    lines = text.splitlines()

    for i, line in enumerate(lines):
        for label, key in LABELS.items():
            if line.rstrip(":").lower() == label.lower() and i + 1 < len(lines):
                value = lines[i + 1]

                if key in {
                    "songsPlayed",
                    "attendance",
                    "concertCapacity",
                    "setLengthMin",
                }:
                    number = re.search(r"\d[\d,]*", value)
                    if number:
                        value = int(number.group(0).replace(",", ""))

                out[key] = value

    return out


def main():
    _log("[cureguide] sync started")
    _load_robots_once()

    concerts = load("concerts.json", [])
    changes = load("changelog.json", [])

    byid = {c["id"]: c for c in concerts}
    byurl = {
        c.get("sourceUrl"): c
        for c in concerts
        if c.get("sourceUrl")
    }

    urls = candidates()
    _log(f"[cureguide] {len(urls)} candidate pages")

    for index, url in enumerate(urls, 1):
        _log(f"[cureguide] {index}/{len(urls)} {url}")

        try:
            patch = parse(url, fetch(url))
        except Exception as exc:
            _log(f"[cureguide] skip {url}: {exc}")
            continue

        old = byurl.get(url)

        if old is None:
            same = [
                c
                for c in byid.values()
                if c.get("date") == patch["date"]
                and normalize(c.get("city")) == normalize(patch.get("city"))
                and normalize(c.get("venue")) == normalize(patch.get("venue"))
            ]
            old = same[0] if len(same) == 1 else None

        if old is None:
            base = (
                f"cureguide:{patch['date']}:"
                f"{normalize(patch.get('city')).replace(' ', '-')}:"
                f"{normalize(patch.get('venue')).replace(' ', '-')}"
            ).rstrip(":")

            cid = base
            duplicate = 2

            while cid in byid:
                cid = f"{base}:{duplicate}"
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
                if key in {"id", "sources"} or value in (None, ""):
                    continue

                if key == "scrapedAt":
                    old[key] = value
                    continue

                if old.get(key) != value:
                    log_change(
                        changes,
                        old["id"],
                        old["date"],
                        key,
                        old.get(key),
                        value,
                        url,
                        "HISTORICAL_CORRECTION"
                        if old["year"] < dt.datetime.now().year
                        else "UPDATED_EVENT",
                    )
                    old[key] = value

            old.setdefault("sources", {})["primary"] = "cure-concerts.de"

        time.sleep(0.8)

    save(
        "concerts.json",
        sorted(byid.values(), key=lambda concert: concert["date"]),
    )
    save("changelog.json", changes[-5000:])

    state = load("state.json", {})
    state["cureGuideLastSync"] = now()
    state["cureGuideCandidates"] = len(urls)
    save("state.json", state)

    _log("[cureguide] sync completed")


if __name__ == "__main__":
    main()
