#!/usr/bin/env python3
"""Fetch current rental listings from gag-koeln.de and print them as JSON.

State/diffing is NOT done here — the calling agent compares this output
against a previously stored state (e.g. a file in Google Drive) and decides
whether to notify and how to update the stored state. This keeps the script
free of any write access requirements (GitHub push, etc).

The listing page no longer renders apartments into the initial HTML — they
are loaded client-side via a TYPO3 Extbase AJAX action once the page's JS
runs. This script instead replays that AJAX call directly: it scrapes the
filter form's hidden fields (which carry TYPO3's Extbase referrer/trusted-
properties tokens) out of the page HTML and POSTs them back to the form's
action URL to get the same JSON payload the browser would receive.

Output: JSON object {object_id: {title, address, rent, area, rooms, facilities, url}}
"""
import html
import json
import re
import urllib.parse
import urllib.request

URL = "https://www.gag-koeln.de/immobiliensuche/wohnung-mieten"


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


def main() -> None:
    page_html = fetch_html(URL)
    listings_html = fetch_listings_html(page_html)
    current = parse_listings(listings_html)
    print(json.dumps(current, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
