"""Core Zotero operations: read library, add papers by DOI, search — no plugin, no restart.

Reads the local Zotero SQLite directly (from a safe copy) and adds new items through Zotero's
always-on connector server (localhost:23119). Cross-platform data-dir detection.
"""
from __future__ import annotations
import glob, json, os, re, shutil, sqlite3, subprocess, tempfile, urllib.error, urllib.parse, urllib.request, uuid

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
            f"{os.environ.get('APPDATA', '')}/Zotero/Zotero/Profiles/*/prefs.js",     # Windows
            f"{os.environ.get('LOCALAPPDATA', '')}/Zotero/Zotero/Profiles/*/prefs.js"]  # Windows (alt)
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


ARXIV_RE = re.compile(r"(?:arxiv[:/ ]\s*)?(\d{4}\.\d{4,5})(v\d+)?", re.I)
PMID_RE = re.compile(r"(?:pmid[:\s]*)?(\d{7,8})$", re.I)
ISBN_RE = re.compile(r"(?:isbn[:\s]*)?((?:97[89][-\s]?)?[\d-]{9,17}[\dXx])$", re.I)


def resolve_identifier(s: str):
    """Classify an identifier: ('doi'|'arxiv'|'pmid'|'isbn'|'url', value). None if unrecognised."""
    s = s.strip()
    doi = extract_doi(s)
    if doi:
        return ("doi", doi)
    if s.lower().startswith(("http://", "https://")):
        return ("url", s)
    m = ARXIV_RE.fullmatch(s) or (ARXIV_RE.search(s) if "arxiv" in s.lower() else None)
    if m:
        return ("arxiv", m.group(1))
    if PMID_RE.fullmatch(s):
        return ("pmid", PMID_RE.fullmatch(s).group(1))
    if ISBN_RE.fullmatch(s):
        return ("isbn", re.sub(r"[-\s]", "", ISBN_RE.fullmatch(s).group(1)))
    return None


def doi_from_url(url: str):
    """Follow a URL and scrape a DOI out of it (many publisher pages embed one)."""
    doi = extract_doi(url)
    if doi:
        return doi
    try:
        st, body = _http(url)
        if st == 200:
            m = re.search(r'(?:citation_doi"?\s*content=")([^"]+)', body) or DOI_RE.search(body)
            if m:
                return extract_doi(m.group(1) if m.lastindex else m.group(0))
    except Exception:
        pass
    return None


def bibtex_from_arxiv(aid: str):
    """arXiv metadata -> BibTeX. Prefers the published DOI when arXiv reports one."""
    try:
        st, body = _http(f"http://export.arxiv.org/api/query?id_list={aid}")
        if st != 200:
            return None
        doi = re.search(r"<arxiv:doi[^>]*>([^<]+)</arxiv:doi>", body)
        if doi:
            bt = fetch_bibtex(doi.group(1).strip())
            if bt:
                return bt
        title = re.search(r"<title>(.*?)</title>", body, re.S)
        title = " ".join(title.group(1).split()) if title else aid
        authors = re.findall(r"<name>([^<]+)</name>", body)
        year = (re.search(r"<published>(\d{4})", body) or [None, ""])[1] if re.search(r"<published>(\d{4})", body) else ""
        auth = " and ".join(a.strip() for a in authors)
        key = f"arxiv{aid.replace('.', '')}"
        return (f"@article{{{key},\n  title = {{{title}}},\n  author = {{{auth}}},\n"
                f"  year = {{{year}}},\n  journal = {{arXiv preprint}},\n"
                f"  eprint = {{{aid}}},\n  url = {{https://arxiv.org/abs/{aid}}}\n}}")
    except Exception:
        return None


def bibtex_from_pmid(pmid: str):
    """PubMed -> DOI (preferred) or minimal BibTeX."""
    try:
        st, body = _http("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                         f"?db=pubmed&id={pmid}&retmode=json")
        if st != 200:
            return None
        rec = (json.loads(body).get("result") or {}).get(pmid) or {}
        for aid in rec.get("articleids", []):
            if aid.get("idtype") == "doi" and aid.get("value"):
                bt = fetch_bibtex(aid["value"])
                if bt:
                    return bt
        title = rec.get("title", "").rstrip(".")
        auth = " and ".join(a.get("name", "") for a in rec.get("authors", []))
        year = (rec.get("pubdate", "") or "")[:4]
        return (f"@article{{pmid{pmid},\n  title = {{{title}}},\n  author = {{{auth}}},\n"
                f"  year = {{{year}}},\n  journal = {{{rec.get('fulljournalname','')}}},\n"
                f"  note = {{PMID: {pmid}}}\n}}")
    except Exception:
        return None


def bibtex_from_isbn(isbn: str):
    try:
        st, body = _http(f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data")
        if st != 200:
            return None
        rec = (json.loads(body) or {}).get(f"ISBN:{isbn}")
        if not rec:
            return None
        auth = " and ".join(a.get("name", "") for a in rec.get("authors", []))
        year = re.search(r"\d{4}", rec.get("publish_date", "") or "")
        pub = (rec.get("publishers") or [{}])[0].get("name", "")
        return (f"@book{{isbn{isbn},\n  title = {{{rec.get('title','')}}},\n  author = {{{auth}}},\n"
                f"  year = {{{year.group(0) if year else ''}}},\n  publisher = {{{pub}}},\n"
                f"  isbn = {{{isbn}}}\n}}")
    except Exception:
        return None


def bibtex_for(kind: str, value: str):
    """BibTeX for any supported identifier kind."""
    if kind == "doi":
        return fetch_bibtex(value)
    if kind == "arxiv":
        return bibtex_from_arxiv(value)
    if kind == "pmid":
        return bibtex_from_pmid(value)
    if kind == "isbn":
        return bibtex_from_isbn(value)
    if kind == "url":
        doi = doi_from_url(value)
        return fetch_bibtex(doi) if doi else None
    return None


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
    """POST BibTeX to the connector with a unique session; return the new itemKey or None.

    NOTE: /connector/import is the only connector write path used. /connector/saveItems was tested and
    destabilised the Zotero process, so it is deliberately not used.
    """
    st, body = _http(f"{CONNECTOR}/import?session={uuid.uuid4()}", data=bibtex.encode(),
                     headers={"Content-Type": "application/x-bibtex"}, method="POST")
    if 200 <= st < 300:
        try:
            items = json.loads(body)
            return items[0].get("key") if items else True
        except Exception:
            return True
    return None


# ---------- collections (read-only) ----------
def list_collections(data_dir: str) -> list[dict]:
    db = sqlite3.connect(_snapshot(data_dir)); db.row_factory = sqlite3.Row
    rows = db.execute("""SELECT c.collectionName AS name, c.key, count(ci.itemID) AS items
                         FROM collections c LEFT JOIN collectionItems ci ON c.collectionID=ci.collectionID
                         GROUP BY c.collectionID ORDER BY c.collectionName""").fetchall()
    db.close()
    return [{"name": r["name"], "key": r["key"], "items": r["items"]} for r in rows]


# ---------- portable Zotero version ----------
def zotero_version() -> str:
    prefs = _profile_prefs()
    if prefs:
        try:
            txt = open(prefs).read()
            for key in ("extensions.lastAppVersion", "extensions.zotero.lastVersion"):
                m = re.search(re.escape(key) + r'",\s*"([^"]+)"', txt)
                if m:
                    return m.group(1)
        except Exception:
            pass
    return "6.0.0"


# ---------- PDFs: locate, fetch (open access), extract text ----------
def pdf_path_for(data_dir: str, item_key: str):
    """Absolute path of the first PDF attached to the item with this key, or None."""
    db = sqlite3.connect(_snapshot(data_dir)); db.row_factory = sqlite3.Row
    row = db.execute("""SELECT ai.key AS akey, att.path AS path
                        FROM items parent
                        JOIN itemAttachments att ON att.parentItemID = parent.itemID
                        JOIN items ai ON ai.itemID = att.itemID
                        WHERE parent.key = ? AND att.contentType = 'application/pdf'
                        ORDER BY ai.itemID LIMIT 1""", (item_key,)).fetchone()
    db.close()
    if not row or not row["path"]:
        return None
    path = row["path"]
    if path.startswith("storage:"):
        p = os.path.join(data_dir, "storage", row["akey"], path[len("storage:"):])
        return p if os.path.exists(p) else None
    if path.startswith("attachments:"):
        return None
    return path if os.path.isabs(path) and os.path.exists(path) else None


def arxiv_pdf_url(text: str):
    """Direct arXiv PDF URL if the text contains an arXiv id/link (arXiv is always open access)."""
    if not text:
        return None
    m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", text, re.I) or \
        re.search(r"arxiv[:\s]*(\d{4}\.\d{4,5})", text, re.I)
    return f"https://arxiv.org/pdf/{m.group(1)}" if m else None


def oa_pdf_for_record(rec: dict):
    """Best open-access PDF URL for a library record: DOI lookup first, then arXiv."""
    if rec.get("doi"):
        url = find_oa_pdf(rec["doi"])
        if url:
            return url
    d = rec.get("_data") or {}
    for field in ("url", "extra", "publicationTitle", "archiveID"):
        url = arxiv_pdf_url(d.get(field, ""))
        if url:
            return url
    return None


def find_oa_pdf(doi: str):
    """Open-access PDF URL for a DOI via OpenAlex, else Unpaywall. None if paywalled."""
    try:
        st, body = _http(f"https://api.openalex.org/works/doi:{doi}?mailto=claude-zotero@users.noreply.github.com")
        if st == 200:
            loc = (json.loads(body) or {}).get("best_oa_location") or {}
            if loc.get("pdf_url"):
                return loc["pdf_url"]
    except Exception:
        pass
    try:
        st, body = _http(f"https://api.unpaywall.org/v2/{doi}?email=claude-zotero@users.noreply.github.com")
        if st == 200:
            loc = (json.loads(body) or {}).get("best_oa_location") or {}
            if loc.get("url_for_pdf"):
                return loc["url_for_pdf"]
    except Exception:
        pass
    return None


def cache_pdf(url: str, cache_dir: str, name: str):
    """Download a PDF into cache_dir; return the path (or None). Never touches Zotero."""
    os.makedirs(cache_dir, exist_ok=True)
    dest = os.path.join(cache_dir, f"{name}.pdf")
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return dest
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as fh:
            head = r.read(5)
            if not head.startswith(b"%PDF"):
                return None
            fh.write(head); shutil.copyfileobj(r, fh)
        return dest if os.path.getsize(dest) > 1000 else None
    except Exception:
        return None


def extract_text(pdf_path: str):
    """(text, pages) from a PDF. Prefers pdftotext (fast); falls back to pypdf."""
    if shutil.which("pdftotext"):
        try:
            out = subprocess.run(["pdftotext", "-q", pdf_path, "-"],
                                 capture_output=True, text=True, timeout=120)
            if out.stdout.strip():
                return out.stdout, out.stdout.count("\f") + 1
        except Exception:
            pass
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, 0
    try:
        rd = PdfReader(pdf_path)
        return "\n\n".join((p.extract_text() or "") for p in rd.pages), len(rd.pages)
    except Exception:
        return None, 0
