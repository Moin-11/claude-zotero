"""Snowball literature search via OpenAlex — no API key required.

Given a seed paper, return the works it cites (backward) and the works citing it (forward), each marked
with whether it is already in the local Zotero library. Feed the rest straight into zotero_add().
"""
from __future__ import annotations
import json, urllib.parse

from .zotero import _http

API = "https://api.openalex.org"
MAILTO = "claude-zotero@users.noreply.github.com"


def _get(url: str):
    sep = "&" if "?" in url else "?"
    st, body = _http(f"{url}{sep}mailto={MAILTO}")
    return json.loads(body) if st == 200 else None


def _slim(w: dict, direction: str) -> dict:
    doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
    return {
        "title": w.get("title") or w.get("display_name") or "",
        "year": w.get("publication_year"),
        "doi": doi,
        "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
        "cited_by_count": w.get("cited_by_count"),
        "authors": [a.get("author", {}).get("display_name", "")
                    for a in (w.get("authorships") or [])[:5]],
        "open_access_pdf": ((w.get("best_oa_location") or {}).get("pdf_url")),
        "direction": direction,
    }


def related(doi: str, direction: str = "both", limit: int = 25) -> dict:
    """{seed, references:[...], citing:[...]} for a seed DOI."""
    seed = _get(f"{API}/works/doi:{doi}")
    if not seed:
        return {"error": f"OpenAlex has no record for DOI {doi}"}
    out = {"seed": {"title": seed.get("title"), "year": seed.get("publication_year"), "doi": doi},
           "references": [], "citing": []}

    if direction in ("both", "backward"):
        ids = [r.split("/")[-1] for r in (seed.get("referenced_works") or [])][:limit]
        for i in range(0, len(ids), 50):
            batch = "|".join(ids[i:i + 50])
            d = _get(f"{API}/works?filter=openalex_id:{batch}&per-page=50")
            if d:
                out["references"] += [_slim(w, "reference") for w in d.get("results", [])]

    if direction in ("both", "forward"):
        d = _get(f"{API}/works?filter=cites:{seed['id'].split('/')[-1]}"
                 f"&per-page={min(limit, 50)}&sort=cited_by_count:desc")
        if d:
            out["citing"] = [_slim(w, "citing") for w in d.get("results", [])][:limit]

    return out


def search(query: str, limit: int = 25, from_year: int | None = None) -> list[dict]:
    """Topic search across OpenAlex — for discovering papers not yet in the library."""
    q = urllib.parse.quote(query)
    url = f"{API}/works?search={q}&per-page={min(limit, 50)}&sort=relevance_score:desc"
    if from_year:
        url += f"&filter=from_publication_date:{from_year}-01-01"
    d = _get(url)
    return [_slim(w, "search") for w in (d or {}).get("results", [])][:limit]
