"""MCP server exposing Zotero research tooling to Claude Code.

Tools: zotero_status, zotero_search, zotero_add, zotero_refresh, build_live_docx.
The loop it enables: agent finds a paper online -> zotero_add(DOI) -> writes it into Zotero and
returns a citekey -> agent drafts markdown citing [@citekey] -> build_live_docx -> a Word file
whose citations are LIVE, refreshable Zotero fields.
"""
from __future__ import annotations
import json, os, shutil

from mcp.server.fastmcp import FastMCP

from . import zotero
from .docx import build_live_docx as _build_docx, DEFAULT_STYLE

mcp = FastMCP("claude-zotero")

HOME = os.path.expanduser(os.environ.get("CLAUDE_ZOTERO_HOME", "~/.claude-zotero"))
BIB = os.path.join(HOME, "references.bib")
CITEMAP = os.path.join(HOME, "zotero-citemap.json")


def _refresh(collection: str | None = None) -> dict:
    os.makedirs(HOME, exist_ok=True)
    data_dir = zotero.find_data_dir()
    recs = zotero.read_library(data_dir, collection)
    zotero.write_bib(recs, BIB)
    zotero.write_citemap(recs, CITEMAP)
    return {"count": len(recs), "bib": BIB, "citemap": CITEMAP, "data_dir": data_dir}


@mcp.tool()
def zotero_status() -> dict:
    """Check the Zotero setup: data dir, library size, connector reachability, pandoc availability."""
    out = {"pandoc": bool(shutil.which("pandoc")), "connector_running": zotero.connector_up()}
    try:
        out["data_dir"] = zotero.find_data_dir()
        out["items"] = len(zotero.read_library(out["data_dir"]))
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
def zotero_add(dois: list[str]) -> list[dict]:
    """Add papers to Zotero by DOI (skips ones already in the library) and return their citekeys.

    Give it DOIs discovered while researching. Each result is {doi, status, citekey} where status is
    'added', 'reused' (already present), or 'failed'. Cite the returned citekey as [@citekey].
    """
    if not zotero.connector_up():
        return [{"status": "failed", "reason": "Zotero is not running (connector unreachable on port 23119)"}]
    state = _refresh()
    cmap = json.load(open(CITEMAP))
    existing = {v.get("doi", "") for v in cmap.values() if v.get("doi")}
    d2k = {v["doi"]: k for k, v in cmap.items() if v.get("doi")}

    results, added = [], False
    for raw in dois:
        doi = zotero.extract_doi(raw)
        if not doi:
            results.append({"input": raw, "status": "failed", "reason": "no DOI found"}); continue
        if doi.lower() in existing:
            results.append({"doi": doi, "status": "reused", "citekey": d2k.get(doi.lower())}); continue
        bib = zotero.fetch_bibtex(doi)
        if not bib:
            results.append({"doi": doi, "status": "failed", "reason": "no metadata for DOI"}); continue
        try:
            key = zotero.add_bibtex(bib)
        except Exception as e:
            results.append({"doi": doi, "status": "failed", "reason": str(e)}); continue
        if key:
            added = True; existing.add(doi.lower())
            results.append({"doi": doi, "status": "added", "itemKey": key if isinstance(key, str) else None})
        else:
            results.append({"doi": doi, "status": "failed", "reason": "connector rejected the item"})

    if added:
        _refresh()
        cmap = json.load(open(CITEMAP))
        d2k = {v["doi"]: k for k, v in cmap.items() if v.get("doi")}
        for r in results:
            if r.get("status") == "added":
                r["citekey"] = d2k.get(r["doi"].lower())
    return results


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
