from __future__ import annotations

from bs4 import BeautifulSoup


def extract_who_metadata(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "WHO page"
    text = " ".join(soup.stripped_strings)[:5000]
    return {
        "title": title,
        "excerpt": text,
    }
