#!/usr/bin/env python3
"""Fetch current rental listings from gag-koeln.de and print them as JSON.

State/diffing is NOT done here — the calling agent compares this output
against a previously stored state (e.g. a file in Google Drive) and decides
whether to notify and how to update the stored state. This keeps the script
free of any write access requirements (GitHub push, etc).

Output: JSON object {object_id: {title, address, rent, area, rooms, facilities, url}}
"""
import json
import re
import urllib.request

URL = "https://www.gag-koeln.de/immobiliensuche/wohnung-mieten"


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


def main() -> None:
    html = fetch_html(URL)
    current = parse_listings(html)
    print(json.dumps(current, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
