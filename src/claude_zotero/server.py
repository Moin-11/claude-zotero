"""MCP server exposing Zotero research tooling to Claude Code.

Tools: zotero_status, zotero_search, zotero_add, zotero_refresh, build_live_docx.
The loop it enables: agent finds a paper online -> zotero_add(DOI) -> writes it into Zotero and
returns a citekey -> agent drafts markdown citing [@citekey] -> build_live_docx -> a Word file
whose citations are LIVE, refreshable Zotero fields.
"""
from __future__ import annotations
import json, os, platform, shutil

from mcp.server.fastmcp import FastMCP

from . import openalex, zotero
from .docx import build_live_docx as _build_docx, DEFAULT_STYLE

mcp = FastMCP("claude-zotero")

HOME = os.path.expanduser(os.environ.get("CLAUDE_ZOTERO_HOME", "~/.claude-zotero"))
BIB = os.path.join(HOME, "references.bib")
CITEMAP = os.path.join(HOME, "zotero-citemap.json")
PDFCACHE = os.path.join(HOME, "pdf-cache")


def _refresh(collection: str | None = None) -> dict:
    os.makedirs(HOME, exist_ok=True)
    data_dir = zotero.find_data_dir()
    recs = zotero.read_library(data_dir, collection)
    zotero.write_bib(recs, BIB)
    zotero.write_citemap(recs, CITEMAP)
    return {"count": len(recs), "bib": BIB, "citemap": CITEMAP, "data_dir": data_dir}


def _pdf_extractor() -> str | None:
    if shutil.which("pdftotext"):
        return "pdftotext"
    try:
        import pypdf  # noqa: F401
        return "pypdf"
    except ImportError:
        return None


@mcp.tool()
def zotero_status() -> dict:
    """Check the Zotero setup: data dir, library size, connector reachability, pandoc, PDF extraction."""
    out = {"platform": platform.system(), "pandoc": bool(shutil.which("pandoc")),
           "connector_running": zotero.connector_up(), "pdf_extractor": _pdf_extractor()}
    try:
        out["data_dir"] = zotero.find_data_dir()
        out["items"] = len(zotero.read_library(out["data_dir"]))
        out["zotero_version"] = zotero.zotero_version()
    except Exception as e:
        out["error"] = str(e)
    if not out["connector_running"]:
        out["hint"] = "Start the Zotero desktop app — adding papers needs its connector on port 23119."
    if not out["pandoc"]:
        out["hint_pandoc"] = "Install pandoc (brew install pandoc) — required to build .docx files."
    return out


@mcp.tool()
def zotero_search(query: str, limit: int = 20) -> list[dict]:
    """Search the local Zotero library by title/author/DOI. Returns citekeys you can cite as [@citekey]."""
    recs = zotero.read_library(zotero.find_data_dir())
    q = query.lower().strip()
    hits = [r for r in recs
            if q in r["title"].lower() or q in r["doi"] or any(q in a.lower() for a in r["authors"])]
    return [{"citekey": r["citekey"], "title": r["title"], "year": r["year"],
             "doi": r["doi"], "authors": r["authors"][:4], "itemKey": r["itemKey"]}
            for r in hits[:limit]]


@mcp.tool()
def zotero_add(identifiers: list[str]) -> list[dict]:
    """Add papers to Zotero by DOI, arXiv ID, PMID, ISBN, or URL. Returns citekeys to cite.

    Skips anything already in the library (returns the existing citekey). Each result is
    {identifier, kind, status, citekey} with status 'added', 'reused', or 'failed'.
    Cite the returned citekey as [@citekey]. New items land in My Library (or the collection
    currently selected in Zotero).
    """
    if not zotero.connector_up():
        return [{"status": "failed", "reason": "Zotero is not running (connector unreachable on port 23119)"}]
    _refresh()
    cmap = json.load(open(CITEMAP))
    existing = {v.get("doi", "") for v in cmap.values() if v.get("doi")}
    d2k = {v["doi"]: k for k, v in cmap.items() if v.get("doi")}

    results, added = [], False
    for raw in identifiers:
        res = zotero.resolve_identifier(raw)
        if not res:
            results.append({"identifier": raw, "status": "failed",
                            "reason": "not a recognised DOI / arXiv ID / PMID / ISBN / URL"}); continue
        kind, value = res
        if kind == "doi" and value.lower() in existing:
            results.append({"identifier": raw, "kind": kind, "doi": value,
                            "status": "reused", "citekey": d2k.get(value.lower())}); continue
        bib = zotero.bibtex_for(kind, value)
        if not bib:
            results.append({"identifier": raw, "kind": kind, "status": "failed",
                            "reason": f"no metadata found for {kind} {value}"}); continue
        doi = zotero.extract_doi(bib) or (value if kind == "doi" else None)
        if doi and doi.lower() in existing:
            results.append({"identifier": raw, "kind": kind, "doi": doi,
                            "status": "reused", "citekey": d2k.get(doi.lower())}); continue
        try:
            key = zotero.add_bibtex(bib)
        except Exception as e:
            results.append({"identifier": raw, "kind": kind, "status": "failed", "reason": str(e)}); continue
        if key:
            added = True
            if doi:
                existing.add(doi.lower())
            results.append({"identifier": raw, "kind": kind, "doi": doi, "status": "added",
                            "itemKey": key if isinstance(key, str) else None})
        else:
            results.append({"identifier": raw, "kind": kind, "status": "failed",
                            "reason": "connector rejected the item"})

    if added:
        _refresh()
        cmap = json.load(open(CITEMAP))
        d2k = {v["doi"]: k for k, v in cmap.items() if v.get("doi")}
        k2 = {v["itemKey"]: k for k, v in cmap.items()}
        for r in results:
            if r.get("status") == "added":
                r["citekey"] = (d2k.get((r.get("doi") or "").lower())
                                or k2.get(r.get("itemKey")))
    return results


@mcp.tool()
def zotero_collections() -> list[dict]:
    """List Zotero collections with item counts (use the name to scope zotero_refresh)."""
    return zotero.list_collections(zotero.find_data_dir())


@mcp.tool()
def zotero_read(citekey: str, max_chars: int = 20000, offset: int = 0) -> dict:
    """Read the FULL TEXT of a paper so you can summarise, extract data, or write about it accurately.

    Uses the PDF attached in Zotero; if none is attached, tries to fetch an open-access copy and caches
    it locally (Zotero itself is never modified). Long papers: page through with offset/max_chars.
    Always prefer reading a paper over inferring its content from the title.
    """
    data_dir = zotero.find_data_dir()
    recs = zotero.read_library(data_dir)
    rec = next((r for r in recs if r["citekey"] == citekey), None)
    if not rec:
        return {"error": f"no item with citekey '{citekey}' — use zotero_search() to find the right key"}

    path = zotero.pdf_path_for(data_dir, rec["itemKey"])
    source = "zotero-attachment"
    if not path:
        url = zotero.oa_pdf_for_record(rec)
        if url:
            path = zotero.cache_pdf(url, PDFCACHE, rec["itemKey"])
            source = "open-access-cache"
    if not path:
        return {"citekey": citekey, "title": rec["title"],
                "error": "no PDF attached in Zotero and no open-access copy found (likely paywalled). "
                         "Attach the PDF in Zotero to make this paper readable."}
    if not _pdf_extractor():
        return {"error": "no PDF extractor available — install pypdf (a dependency) or poppler's pdftotext"}

    text, pages = zotero.extract_text(path)
    if not text or not text.strip():
        return {"citekey": citekey, "title": rec["title"], "path": path, "pages": pages,
                "error": "PDF yielded no text — it is probably a scanned image (OCR is not supported)"}
    chunk = text[offset:offset + max_chars]
    return {"citekey": citekey, "title": rec["title"], "year": rec["year"], "doi": rec["doi"],
            "source": source, "pages": pages, "total_chars": len(text), "offset": offset,
            "returned_chars": len(chunk),
            "more": offset + len(chunk) < len(text),
            "next_offset": offset + len(chunk) if offset + len(chunk) < len(text) else None,
            "text": chunk}


@mcp.tool()
def find_related(seed: str, direction: str = "both", limit: int = 25) -> dict:
    """Snowball a literature search from a seed paper (citekey or DOI) using OpenAlex.

    Returns the works it cites ('references') and works citing it ('citing'), each marked with
    in_library/citekey so you can pipe the new ones straight into zotero_add(). direction:
    'both' | 'backward' (references) | 'forward' (citing).
    """
    doi = zotero.extract_doi(seed)
    recs = zotero.read_library(zotero.find_data_dir())
    if not doi:
        rec = next((r for r in recs if r["citekey"] == seed), None)
        if not rec or not rec["doi"]:
            return {"error": f"'{seed}' is not a DOI and has no DOI in the library"}
        doi = rec["doi"]
    out = openalex.related(doi, direction, limit)
    if "error" in out:
        return out
    have = {r["doi"]: r["citekey"] for r in recs if r["doi"]}
    for bucket in ("references", "citing"):
        for w in out.get(bucket, []):
            w["in_library"] = w["doi"] in have
            w["citekey"] = have.get(w["doi"])
    out["hint"] = "Add the ones you want with zotero_add([...dois]), then zotero_read(citekey) to read them."
    return out


@mcp.tool()
def search_literature(query: str, limit: int = 25, from_year: int | None = None) -> list[dict]:
    """Search OpenAlex for papers on a topic (not limited to your library). Marks ones you already have."""
    hits = openalex.search(query, limit, from_year)
    have = {r["doi"]: r["citekey"] for r in zotero.read_library(zotero.find_data_dir()) if r["doi"]}
    for h in hits:
        h["in_library"] = h["doi"] in have
        h["citekey"] = have.get(h["doi"])
    return hits


@mcp.tool()
def zotero_refresh(collection: str | None = None) -> dict:
    """Re-export the library to references.bib + citemap (call after adding items outside this server)."""
    return _refresh(collection)


@mcp.tool()
def build_live_docx(markdown: str, output_path: str, style: str = DEFAULT_STYLE) -> dict:
    """Turn markdown citing [@citekey] into a .docx with LIVE, refreshable Zotero citation fields.

    No RTF/ODF Scan and no manual insertion: open the result in Word with the Zotero plugin and press
    Refresh to reformat and populate the bibliography. Put `# References` where the bibliography goes.
    Locators: [@key, p. 12]. Multiple: [@a; @b].
    """
    if not shutil.which("pandoc"):
        return {"error": "pandoc not found — install it (e.g. brew install pandoc)"}
    state = _refresh()
    cmap = json.load(open(CITEMAP))
    res = _build_docx(markdown, output_path, data_dir=state["data_dir"],
                      bib_path=BIB, citemap=cmap, style=style)
    if res["warnings"]:
        res["note"] = ("These citekeys were not in the library and were left as plain text: "
                       + ", ".join(res["warnings"]) + ". Use zotero_add() or zotero_search() first.")
    return res


def main():
    mcp.run()


if __name__ == "__main__":
    main()
