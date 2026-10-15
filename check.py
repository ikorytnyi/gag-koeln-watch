#!/usr/bin/env python3
"""Fetch current rental listings from gag-koeln.de and diff them against stored state.

Usage:
  python3 check.py                     # print current listings as JSON
  python3 check.py --state seen.json   # diff against seen.json, overwrite it with
                                       # the current listings and print the
                                       # Ukrainian Telegram report (empty = nothing new)

The script never commits or pushes anything — run.sh owns the git side
(state lives in the `claude/state` branch, see README).

State format: every listing ever seen, {object_id: {...listing, first_seen,
gone_since}}. gone_since is null while the listing is on the site;
a listing that reappears after gone_since was set is reported as "повторно".
If the site returns 0 listings while some are active, the script exits
non-zero without touching the state (a parsing failure, not a real wipe).

The listing page no longer renders apartments into the initial HTML — they
are loaded client-side via a TYPO3 Extbase AJAX action once the page's JS
runs. This script instead replays that AJAX call directly: it scrapes the
filter form's hidden fields (which carry TYPO3's Extbase referrer/trusted-
properties tokens) out of the page HTML and POSTs them back to the form's
action URL to get the same JSON payload the browser would receive.

Listing format: {object_id: {title, address, rent, area, rooms, facilities, url}}
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

URL = "https://www.gag-koeln.de/immobiliensuche/wohnung-mieten"
STAMP_FORMAT = "%Y-%m-%dT%H:%MZ"


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_listings_html(page_html: str) -> str:
    """Replay the page's filter-form AJAX request to get the listings partial."""
    start = page_html.find('<form data-filter-form=')
    end = page_html.find("</form>", start)
    form = page_html[start:end]

    action_match = re.search(r'action="([^"]+)"', form)
    action_url = html.unescape(action_match.group(1))

    fields = re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', form)
    body = urllib.parse.urlencode([(name, html.unescape(value)) for name, value in fields])

    req = urllib.request.Request(
        action_url,
        data=body.encode("utf-8"),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": URL,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["html"]


def parse_listings(html_fragment: str) -> dict:
    listings = {}
    chunks = html_fragment.split('class="appartment overflow-hidden')[1:]
    for chunk in chunks:
        m_id = re.search(r'href="https://www\.gag-koeln\.de/immobiliensuche/([a-zA-Z0-9_-]+)"', chunk)
        if not m_id:
            continue
        obj_id = m_id.group(1)

        m_title = re.search(r'appartment__header h3">([^<]*)</div>', chunk)
        title = m_title.group(1).strip() if m_title else ""

        m_addr = re.search(r'appartment__address[^>]*>(.*?)</div>', chunk, re.S)
        address = " ".join(m_addr.group(1).split()) if m_addr else ""
        address = re.sub(r"\s*,\s*", ", ", address)

        m_rent = re.search(r'<span class="h4">([^<]*)</span>\s*<small>\s*Gesamtmiete', chunk, re.S)
        rent = m_rent.group(1).strip() if m_rent else ""

        m_area = re.search(r'<span class="h4">([^<]*)</span>\s*<small>\s*Wohnfl\xe4che', chunk, re.S)
        area = m_area.group(1).strip() if m_area else ""

        m_rooms = re.search(r'<span class="h4">([^<]*)</span>\s*<small>\s*Zimmer', chunk, re.S)
        rooms = m_rooms.group(1).strip() if m_rooms else ""

        facilities = re.findall(r'appartment__facilities__item">([^<]*)</span>', chunk)

        listings[obj_id] = {
            "title": title,
            "address": address,
            "rent": rent,
            "area": area,
            "rooms": rooms,
            "facilities": facilities,
            "url": f"https://www.gag-koeln.de/immobiliensuche/{obj_id}",
        }
    return listings


def rooms_key(rooms: str):
    try:
        return (0, float(rooms.replace(",", ".")), rooms)
    except ValueError:
        return (1, 0.0, rooms)


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime(STAMP_FORMAT)


def days_since(stamp: str, now: str) -> int:
    then = datetime.strptime(stamp, STAMP_FORMAT)
    return (datetime.strptime(now, STAMP_FORMAT) - then).days


def build_report(new: dict, returned: dict, previous: dict, now: str) -> str:
    """new/returned: {object_id: listing}; previous supplies gone_since for returned ones."""
    appeared = {**new, **returned}
    counts, returned_counts = {}, {}
    for obj_id, item in appeared.items():
        counts[item["rooms"]] = counts.get(item["rooms"], 0) + 1
        if obj_id in returned:
            returned_counts[item["rooms"]] = returned_counts.get(item["rooms"], 0) + 1

    header = f"Нові оголошення на gag-koeln.de: {len(appeared)}"
    if returned:
        header += f" (з них повторно: {len(returned)})"
    lines = [header, "", "За кількістю кімнат:"]
    for rooms in sorted(counts, key=rooms_key):
        line = f"  {rooms} кімн.: {counts[rooms]}"
        if rooms in returned_counts:
            line += f" ({returned_counts[rooms]} повторно)"
        lines.append(line)

    if returned:
        lines += ["", "Повернулись на сайт:"]
        for obj_id, item in returned.items():
            gone_since = previous[obj_id]["gone_since"]
            days = days_since(gone_since, now)
            ago = f"{days} дн." if days else "менше доби"
            lines += [f"  {item['title']} — не було з {gone_since[:10]} ({ago})", f"  {item['url']}"]

    five = [(obj_id, item) for obj_id, item in appeared.items() if item["rooms"] == "5"]
    if five:
        lines += ["", "Деталі 5-кімнатних квартир:"]
        for i, (obj_id, item) in enumerate(five):
            if i:
                lines.append("")
            title = item["title"] + (" (повторно)" if obj_id in returned else "")
            lines += [
                title,
                item["address"],
                f"{item['rent']}, {item['area']}",
                ", ".join(item["facilities"]),
                item["url"],
            ]
    return "\n".join(lines)


def update_state(previous: dict, current: dict, now: str) -> dict:
    """Merge current listings into state; listings that vanished are kept with gone_since set.

    Nothing here changes from run to run unless the listings do, so run.sh
    only commits real changes (no per-run "last seen" timestamp on purpose).
    """
    state = {}
    for obj_id, item in current.items():
        first_seen = previous.get(obj_id, {}).get("first_seen") or now
        state[obj_id] = {**item, "first_seen": first_seen, "gone_since": None}
    for obj_id, entry in previous.items():
        if obj_id not in current:
            entry = {k: v for k, v in entry.items() if k != "last_seen"}
            state[obj_id] = {**entry, "gone_since": entry.get("gone_since") or now}
    return state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", help="seen.json to diff against and overwrite with current listings")
    args = parser.parse_args()

    page_html = fetch_html(URL)
    listings_html = fetch_listings_html(page_html)
    current = parse_listings(listings_html)

    if not args.state:
        print(json.dumps(current, ensure_ascii=False, indent=2))
        return

    previous = {}
    if os.path.exists(args.state):
        with open(args.state, encoding="utf-8") as f:
            previous = json.load(f)

    active = [obj_id for obj_id, entry in previous.items() if not entry.get("gone_since")]
    if not current and active:
        # Almost certainly a parsing/site failure, not every listing vanishing at once.
        # Keep the state untouched so the next run doesn't report everything as new.
        sys.exit(f"Site returned 0 listings but {len(active)} were active; refusing to update state")

    now = now_stamp()
    new = {obj_id: item for obj_id, item in current.items() if obj_id not in previous}
    returned = {
        obj_id: item
        for obj_id, item in current.items()
        if obj_id in previous and previous[obj_id].get("gone_since")
    }

    state = update_state(previous, current, now)
    with open(args.state, "w", encoding="utf-8") as f:
        f.write(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    if new or returned:
        print(build_report(new, returned, previous, now))


if __name__ == "__main__":
    main()
