#!/usr/bin/env python3
"""Check gag-koeln.de for new rental listings, diff against stored state, email on changes.

State file: seen.json — {"ids": {object_id: {title, address, rent, area, rooms, facilities, url}}}
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://www.gag-koeln.de/immobiliensuche/wohnung-mieten"
STATE_FILE = Path(__file__).parent / "seen.json"


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_listings(html: str) -> dict:
    listings = {}
    chunks = html.split('class="appartment overflow-hidden')[1:]
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


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"ids": {}}


def save_state(current: dict) -> None:
    STATE_FILE.write_text(json.dumps({"ids": current}, ensure_ascii=False, indent=2))


def format_report(new_ids: list, current: dict) -> str:
    by_rooms: dict[str, int] = {}
    for oid in new_ids:
        rooms = current[oid]["rooms"] or "?"
        by_rooms[rooms] = by_rooms.get(rooms, 0) + 1

    lines = [f"Нові оголошення на gag-koeln.de: {len(new_ids)}", ""]
    lines.append("За кількістю кімнат:")
    for rooms in sorted(by_rooms, key=lambda r: (r == "?", r)):
        lines.append(f"  {rooms} кімн.: {by_rooms[rooms]}")

    five_room = [oid for oid in new_ids if current[oid]["rooms"] == "5"]
    if five_room:
        lines.append("")
        lines.append("Деталі 5-кімнатних квартир:")
        for oid in five_room:
            item = current[oid]
            lines.append(f"- {item['title']}")
            lines.append(f"  {item['address']}")
            lines.append(f"  {item['rent']}, {item['area']}")
            if item["facilities"]:
                lines.append(f"  {', '.join(item['facilities'])}")
            lines.append(f"  {item['url']}")
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    html = fetch_html(URL)
    current = parse_listings(html)
    state = load_state()
    previous_ids = set(state["ids"].keys())
    current_ids = set(current.keys())
    new_ids = sorted(current_ids - previous_ids)

    save_state(current)

    if new_ids:
        print("CHANGED")
        print(format_report(new_ids, current))
    else:
        print("NO_CHANGE")


if __name__ == "__main__":
    main()
