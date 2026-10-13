from __future__ import annotations

import re
from typing import List

import requests
from bs4 import BeautifulSoup

WHO_BASE = "https://www.who.int"


def search_who(query: str, limit: int = 2) -> List[dict]:
    if not query or not query.strip():
        return []
    limit = max(1, min(int(limit), 2))
    try:
        url = f"{WHO_BASE}/search?query={requests.utils.quote(query, safe='')}"
        response = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    items = []
    seen = set()

    for link in soup.select('a[href]'):
        href = link.get('href', '')
        if not href or not href.startswith('/'):
            continue
        text = link.get_text(" ", strip=True)
        if not text:
            continue
        if len(text) < 20:
            continue
        full_url = WHO_BASE + href
        if full_url in seen:
            continue
        items.append({
            "title": text[:200],
            "url": full_url,
            "excerpt": text[:500],
        })
        seen.add(full_url)
        if len(items) >= limit:
            break

    return items


def retrieve_who_source(url: str) -> dict:
    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    except Exception:
        return {"title": "WHO source unavailable", "url": url, "excerpt": ""}

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "WHO page"
    text = " ".join(soup.stripped_strings)
    text = re.sub(r"\s+", " ", text)
    return {
        "title": title,
        "url": url,
        "excerpt": text[:2000],
    }
