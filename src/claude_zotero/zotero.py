"""Core Zotero operations: read library, add papers by DOI, search — no plugin, no restart.

Reads the local Zotero SQLite directly (from a safe copy) and adds new items through Zotero's
always-on connector server (localhost:23119). Cross-platform data-dir detection.
"""
from __future__ import annotations
import glob, json, os, re, shutil, sqlite3, subprocess, tempfile, urllib.error, urllib.request, uuid

CONNECTOR = "http://127.0.0.1:23119/connector"
UA = "claude-zotero/1.0 (+https://github.com/Moin-11/claude-zotero)"
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.I)

ENTRY_TYPE = {"journalArticle": "article", "book": "book", "bookSection": "incollection",
              "conferencePaper": "inproceedings", "thesis": "phdthesis", "report": "techreport",
              "webpage": "misc", "preprint": "article", "manuscript": "unpublished",
              "magazineArticle": "article", "newspaperArticle": "article"}
CONTAINER = {"publicationTitle": "journal", "bookTitle": "booktitle", "proceedingsTitle": "booktitle",
             "conferenceName": "booktitle"}
FIELD_MAP = {"volume": "volume", "issue": "number", "pages": "pages", "publisher": "publisher",
             "place": "address", "DOI": "doi", "url": "url", "ISBN": "isbn", "ISSN": "issn",
             "series": "series", "edition": "edition", "institution": "institution"}


# ---------- data-dir detection ----------
def _profile_prefs():
    home = os.path.expanduser("~")
    pats = [f"{home}/Library/Application Support/Zotero/Profiles/*/prefs.js",   # macOS
            f"{home}/.zotero/zotero/*/prefs.js",                                # Linux
            f"{os.environ.get('APPDATA', '')}/Zotero/Zotero/Profiles/*/prefs.js"]  # Windows
    for pat in pats:
        for f in glob.glob(pat):
            return f
    return None


def find_data_dir() -> str:
    env = os.environ.get("ZOTERO_DATA_DIR")
    if env and os.path.exists(os.path.join(os.path.expanduser(env), "zotero.sqlite")):
        return os.path.expanduser(env)
    prefs = _profile_prefs()
    if prefs:
        try:
            m = re.search(r'extensions\.zotero\.dataDir",\s*"([^"]+)"', open(prefs).read())
            if m and os.path.exists(os.path.join(m.group(1), "zotero.sqlite")):
                return m.group(1)
        except Exception:
            pass
    default = os.path.expanduser("~/Zotero")
    if os.path.exists(os.path.join(default, "zotero.sqlite")):
        return default
    raise RuntimeError("Zotero data dir not found. Set ZOTERO_DATA_DIR to the folder containing zotero.sqlite.")


def _snapshot(data_dir: str) -> str:
    src = os.path.join(data_dir, "zotero.sqlite")
    tmp = tempfile.mkdtemp(prefix="czot-")
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(src + ext):
            shutil.copy2(src + ext, os.path.join(tmp, "zotero.sqlite" + ext))
    return os.path.join(tmp, "zotero.sqlite")


def local_user_key(data_dir: str) -> str:
    db = sqlite3.connect(_snapshot(data_dir)); db.row_factory = sqlite3.Row
    row = db.execute("SELECT value FROM settings WHERE setting='account' AND key='localUserKey'").fetchone()
    db.close()
    return row["value"] if row else "local"


# ---------- read library ----------
def _slug(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def read_library(data_dir: str, collection: str | None = None) -> list[dict]:
    """Return one record per real item: citekey, itemKey, itemID, type, title, year, doi, authors, fields."""
    db = sqlite3.connect(_snapshot(data_dir)); db.row_factory = sqlite3.Row
    c = db.cursor()
    coll_items = None
    if collection:
        rows = c.execute("""SELECT ci.itemID FROM collectionItems ci JOIN collections co
                            ON ci.collectionID=co.collectionID WHERE lower(co.collectionName) LIKE ?""",
                         (f"%{collection.lower()}%",)).fetchall()
        coll_items = {r["itemID"] for r in rows}
    deleted = {r["itemID"] for r in c.execute("SELECT itemID FROM deletedItems")}
    items = c.execute("""SELECT i.itemID, i.key, it.typeName FROM items i JOIN itemTypes it
                         ON i.itemTypeID=it.itemTypeID
                         WHERE it.typeName NOT IN ('attachment','note','annotation') ORDER BY i.itemID""").fetchall()
    recs, seen = [], {}
    for it in items:
        iid = it["itemID"]
        if iid in deleted or (coll_items is not None and iid not in coll_items):
            continue
        data = {r["fieldName"]: r["value"] for r in c.execute(
            """SELECT f.fieldName, v.value FROM itemData d JOIN fields f ON d.fieldID=f.fieldID
               JOIN itemDataValues v ON d.valueID=v.valueID WHERE d.itemID=?""", (iid,))}
        creators = c.execute("""SELECT cr.firstName, cr.lastName, cr.fieldMode, ct.creatorType
                                FROM itemCreators ic JOIN creators cr ON ic.creatorID=cr.creatorID
                                JOIN creatorTypes ct ON ic.creatorTypeID=ct.creatorTypeID
                                WHERE ic.itemID=? ORDER BY ic.orderIndex""", (iid,)).fetchall()
        auth = [x for x in creators if x["creatorType"] in ("author", "programmer", "inventor")] \
            or [x for x in creators if x["creatorType"] == "editor"]

        def fmt(n):
            return (n["lastName"] or "").strip() if (n["fieldMode"] == 1 or not n["firstName"]) \
                else f"{n['lastName'].strip()}, {n['firstName'].strip()}"

        year = ""
        mm = re.search(r"\d{4}", data.get("date", ""))
        if mm: year = mm.group(0)
        last = _slug(auth[0]["lastName"]) if auth else "anon"
        word = ""
        for w in re.findall(r"[A-Za-z0-9]+", data.get("title", "")):
            if w.lower() not in ("a", "an", "the", "on", "of", "for", "and", "to", "in"):
                word = _slug(w); break
        base = f"{last}{year}{word}" or f"item{iid}"
        key = base
        if base in seen:
            seen[base] += 1; key = f"{base}{chr(96 + seen[base])}"
        else:
            seen[base] = 0
        recs.append({"citekey": key, "itemKey": it["key"], "itemID": iid, "type": it["typeName"],
                     "title": data.get("title", ""), "year": year, "doi": (data.get("DOI") or "").lower(),
                     "authors": [fmt(a) for a in auth], "_data": data})
    db.close()
    return recs


def _bibtex(rec: dict) -> str:
    d = rec["_data"]; fields = []
    if rec["authors"]:
        fields.append(("author", " and ".join(rec["authors"])))
    if d.get("title"): fields.append(("title", d["title"]))
    if rec["year"]: fields.append(("year", rec["year"]))
    for zf, bf in CONTAINER.items():
        if d.get(zf): fields.append((bf, d[zf])); break
    for zf, bf in FIELD_MAP.items():
        if d.get(zf): fields.append((bf, d[zf]))
    esc = lambda s: s.replace("&", r"\&").replace("%", r"\%").replace("_", r"\_").replace("#", r"\#")
    body = ",\n".join(f"  {bf} = {{{esc(str(v))}}}" for bf, v in fields)
    return f"@{ENTRY_TYPE.get(rec['type'], 'misc')}{{{rec['citekey']},\n{body}\n}}"


def write_bib(recs, path):
    open(os.path.expanduser(path), "w").write("\n\n".join(_bibtex(r) for r in recs) + "\n")


def write_citemap(recs, path):
    disp = lambda r: (f"{r['authors'][0].split(',')[0]}" + (" et al." if len(r['authors']) > 1 else "")
                      + (f", {r['year']}" if r['year'] else "")) if r['authors'] else (r['year'] or "Anon")
    m = {r["citekey"]: {"itemKey": r["itemKey"], "cite": disp(r), "doi": r["doi"]} for r in recs}
    json.dump(m, open(os.path.expanduser(path), "w"), indent=0)


# ---------- add by DOI (connector) ----------
def extract_doi(s: str):
    m = DOI_RE.search(s.strip())
    return m.group(0).rstrip(".,;)") if m else None


def _http(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace")


def fetch_bibtex(doi: str):
    for url, hdr in ((f"https://doi.org/{doi}", {"Accept": "application/x-bibtex"}),
                     (f"https://api.crossref.org/works/{doi}/transform/application/x-bibtex", {})):
        try:
            st, body = _http(url, headers=hdr)
            if st == 200 and "@" in body:
                return body
        except Exception:
            continue
    return None


def connector_up() -> bool:
    try:
        st, _ = _http(f"{CONNECTOR}/ping")
        return st == 200
    except Exception:
        return False


def add_bibtex(bibtex: str):
    """POST BibTeX to the connector with a unique session; return the new itemKey or None."""
    st, body = _http(f"{CONNECTOR}/import?session={uuid.uuid4()}", data=bibtex.encode(),
                     headers={"Content-Type": "application/x-bibtex"}, method="POST")
    if 200 <= st < 300:
        try:
            items = json.loads(body)
            return items[0].get("key") if items else True
        except Exception:
            return True
    return None
