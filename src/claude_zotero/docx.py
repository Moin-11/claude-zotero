"""Build a .docx whose citations are LIVE, refreshable Zotero fields.

Injects Zotero Word field codes (ADDIN ZOTERO_ITEM CSL_CITATION), a bibliography field, and a
document-preferences field so the file opens in Word with the Zotero plugin already wired up —
no RTF/ODF Scan, no manual insertion.
"""
from __future__ import annotations
import json, os, re, subprocess, tempfile, uuid, zipfile
from . import zotero

CITE = re.compile(r"\[([^\]]*@[^\]]+)\]")
KEYPART = re.compile(r"@([A-Za-z0-9_:.\-]+)\s*(.*)")
DEFAULT_STYLE = "http://www.zotero.org/styles/chicago-author-date"


def _xesc(s): return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _author_year(csl):
    au = csl.get("author") or csl.get("editor") or []
    dp = (csl.get("issued") or {}).get("date-parts") or []
    yr = str(dp[0][0]) if dp and dp[0] else ""
    if not au:
        name = (csl.get("title", "") or "Anon")[:24]
    elif len(au) == 1:
        name = au[0].get("family", "")
    elif len(au) == 2:
        name = f"{au[0].get('family','')} & {au[1].get('family','')}"
    else:
        name = f"{au[0].get('family','')} et al."
    return name, yr


def _csl_by_citekey(bib):
    out = subprocess.run(["pandoc", "-f", "biblatex", "-t", "csljson", os.path.expanduser(bib)],
                         capture_output=True, text=True, check=True).stdout
    return {x["id"]: x for x in json.loads(out)}


def _zotero_version():
    for p in ("/Applications/Zotero.app/Contents/Info.plist",):
        try:
            return subprocess.run(["plutil", "-extract", "CFBundleShortVersionString", "raw", p],
                                  capture_output=True, text=True).stdout.strip() or "6.0.0"
        except Exception:
            pass
    return "6.0.0"


def _field(instr, display):
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve">{_xesc(instr)}</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:r><w:t xml:space="preserve">{_xesc(display)}</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>')


def build_live_docx(markdown: str, output_path: str, *, data_dir: str, bib_path: str,
                    citemap: dict, style: str = DEFAULT_STYLE) -> dict:
    """markdown ([@citekey]) -> .docx with live Zotero citation fields. Returns {path, citations, warnings}."""
    csl = _csl_by_citekey(bib_path)
    recs = zotero.read_library(data_dir)
    key2id = {r["itemKey"]: r["itemID"] for r in recs}
    local = zotero.local_user_key(data_dir)
    uri = lambda k: f"http://zotero.org/users/local/{local}/items/{k}"

    subs, counter, warn = {}, [0], set()

    def repl(m):
        items, disp = [], []
        for part in m.group(1).split(";"):
            km = KEYPART.search(part.strip())
            if not km:
                return m.group(0)
            ck, loc = km.group(1), km.group(2).strip().lstrip(",").strip()
            info, data = citemap.get(ck), csl.get(ck)
            if not info or not data:
                warn.add(ck); return m.group(0)
            ik = info["itemKey"]; iid = key2id.get(ik, ik)
            name, yr = _author_year(data)
            disp.append(f"{name}, {yr}")
            ci = {"id": iid, "uris": [uri(ik)], "uri": [uri(ik)], "itemData": {**data, "id": iid}}
            if loc:
                mm = re.match(r"(pp?\.?|p)\s*(.*)", loc)
                ci["locator"] = (mm.group(2) if mm else loc); ci["label"] = "page"
            items.append(ci)
        display = "(" + "; ".join(disp) + ")"
        cit = {"citationID": uuid.uuid4().hex[:8],
               "properties": {"formattedCitation": display, "plainCitation": display, "noteIndex": 0},
               "citationItems": items,
               "schema": "https://github.com/citation-style-language/schema/raw/master/csl-citation.json"}
        instr = " ADDIN ZOTERO_ITEM CSL_CITATION " + json.dumps(cit, ensure_ascii=False) + " "
        sent = f"ZXCITE{counter[0]}ZX"; counter[0] += 1
        subs[sent] = _field(instr, display)
        return sent

    md = CITE.sub(repl, markdown)

    subs["ZXBIBLIOZX"] = _field(' ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} CSL_BIBLIOGRAPHY ',
                                "Bibliography — press Refresh in Zotero to populate.")
    pref = (f'ADDIN ZOTERO_PREF_1 <data data-version="3" zotero-version="{_zotero_version()}">'
            f'<session id="{uuid.uuid4().hex[:8].upper()}"/><style id="{style}" locale="en-US" '
            f'hasBibliography="1" bibliographyStyleHasBeenSet="0"/><prefs>'
            f'<pref name="fieldType" value="Field"/>'
            f'<pref name="automaticJournalAbbreviations" value="false"/>'
            f'<pref name="noteType" value="0"/></prefs></data>')
    subs["ZXPREFZX"] = _field(pref, "")

    if re.search(r"^#\s+References", md, re.M):
        md = re.sub(r"^#\s+References.*$", "# References\n\nZXBIBLIOZX", md, flags=re.M)
    else:
        md += "\n\n# References\n\nZXBIBLIOZX"
    md += "\n\nZXPREFZX\n"

    out = os.path.expanduser(output_path)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tf:
        tf.write(md); tmpmd = tf.name
    tmp_docx = out + ".tmp.docx"
    try:
        subprocess.run(["pandoc", tmpmd, "-o", tmp_docx], check=True)
    finally:
        os.unlink(tmpmd)

    zin = zipfile.ZipFile(tmp_docx)
    doc = zin.read("word/document.xml").decode("utf-8")
    for sent, xml in subs.items():
        doc = doc.replace(sent, f'</w:t></w:r>{xml}<w:r><w:t xml:space="preserve">')
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            zout.writestr(it, doc if it.filename == "word/document.xml" else zin.read(it.filename))
    zin.close(); os.unlink(tmp_docx)
    return {"path": out, "citations": counter[0], "warnings": sorted(warn)}
