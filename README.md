# claude-zotero

**Let AI agents grow your Zotero library and write papers with _live_ citations.**

An MCP server that closes the research loop:

```
agent finds a paper online  →  zotero_add("10.1016/…")  →  it's in your Zotero, returns [@citekey]
                            →  agent drafts markdown citing [@citekey]
                            →  build_live_docx(…)       →  .docx with LIVE, refreshable Zotero fields
```

No Better BibTeX. No RTF/ODF Scan. No manual "Add Citation" clicking. The Word file opens with real
Zotero citation fields already in it — press **Refresh** and restyle to any CSL style.

---

## Why this exists

Most Zotero automation stops at *reading* your library or emitting a **static** bibliography — text that
looks like a citation but isn't connected to Zotero, so you still re-insert everything by hand.

`claude-zotero` does the two things that actually matter:

1. **Writes new papers into Zotero** from a DOI, so an agent can cite literature you don't have yet.
2. **Emits genuine Zotero Word field codes** (`ADDIN ZOTERO_ITEM CSL_CITATION …`) so citations are live
   and refreshable the moment you open the file.

## Requirements

- **Zotero desktop, running** — adding papers uses its built-in connector on `localhost:23119`
- **pandoc** — `brew install pandoc` (or your package manager)
- **Python ≥ 3.10**

No Zotero plugin, no Zotero account/sync, and no restart or preference changes required.

## Install

<details open>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add claude-zotero -- uvx --from git+https://github.com/Moin-11/claude-zotero claude-zotero-mcp
```
</details>

<details>
<summary><b>Claude Desktop</b></summary>

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "claude-zotero": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Moin-11/claude-zotero", "claude-zotero-mcp"]
    }
  }
}
```
</details>

Verify with the `zotero_status` tool — it reports your data directory, item count, whether Zotero is
running, and whether pandoc is installed.

## Where it works

This server reads your **local** Zotero SQLite database, talks to Zotero on `localhost`, and writes files
to your local disk. So it works wherever it runs on the same machine as Zotero:

| Client | Works | Why |
|---|:--:|---|
| Claude Code (local) | ✅ | Runs local stdio MCP servers |
| Claude Desktop | ✅ | Runs local stdio MCP servers |
| Claude web (claude.ai) | ❌ | Only connects to remote MCP servers — can't reach your localhost Zotero or local files |
| Cloud / remote agent sessions | ❌ | The sandbox has no access to your Zotero database |

This is a constraint of Zotero being a **desktop** application, not a packaging choice — there is no
version of this that lets a cloud sandbox touch your local library.

## Tools

| Tool | What it does |
|---|---|
| `zotero_status()` | Data dir, library size, connector reachable, pandoc present |
| `zotero_search(query, limit)` | Search your library by title/author/DOI → citekeys to cite |
| `zotero_add(dois)` | **Add papers by DOI.** Skips ones already present (returns the existing citekey). Returns `{doi, status, citekey}` with status `added` / `reused` / `failed` |
| `zotero_refresh(collection?)` | Re-export `references.bib` + citemap (optionally one collection) |
| `build_live_docx(markdown, output_path, style?)` | Markdown citing `[@citekey]` → `.docx` with live Zotero fields |

## Usage

Just talk to your agent:

> Find recent papers on CO₂-brine interfacial tension, add them to my Zotero, and write me a
> two-paragraph literature review as a Word document.

The agent searches the web, calls `zotero_add()` with the DOIs it finds, drafts the review citing the
returned citekeys, and calls `build_live_docx()`. You open the `.docx` and hit **Refresh** in the Zotero tab.

### Citation syntax

Inside the markdown you pass to `build_live_docx`:

```markdown
Nanodots lower CO2-brine IFT [@sakthivel2024influence].
Multiple sources [@a; @b], with a locator [@key, p. 12].

# References
```

`# References` marks where the bibliography field goes (added at the end if omitted).

### Citation styles

Default is Chicago author-date. Pass any CSL style URL:

```
build_live_docx(md, "paper.docx", style="http://www.zotero.org/styles/elsevier-harvard")
```

Or just change it in Word via Zotero → **Document Preferences** — the citations are live fields, so
restyling works normally.

## How the live citations work

Zotero stores Word citations as field codes. This server generates them directly:

- each citation → a Word field containing `ADDIN ZOTERO_ITEM CSL_CITATION {…}` with the item's
  CSL metadata and its Zotero URI (`http://zotero.org/users/local/<key>/items/<itemKey>`)
- a bibliography field (`ADDIN ZOTERO_BIBL … CSL_BIBLIOGRAPHY`)
- a document-preferences field (`ADDIN ZOTERO_PREF_1 …`) pinning the style and `fieldType=Field`

Because the item URIs point at real entries in your library, Zotero resolves them on **Refresh**.

## Notes & limitations

- **Zotero must be running** to add papers (the connector is part of the app). Reading/searching and
  building documents work offline.
- New items land in **My Library** (or whatever collection is selected in Zotero).
- Citekeys are generated as `lastnameyearword` and are stable for a given item.
- Papers without a DOI aren't supported by `zotero_add` yet — add them in Zotero, then `zotero_refresh()`.
- The live-field docx has been validated against Zotero 7+/9 on macOS. If Refresh doesn't resolve
  citations on your setup, please open an issue with your Zotero version.

## Bundled Claude Code assets

`claude/` contains optional extras for research work:

- `commands/team-research.md` — a `/team-research` command that spins up a per-dataset research team
  (explorer, methods-scout, lit-reviewer, experimentalist, writer, critic) with the add→cite loop wired in
- `reference/techniques.md` — a cutting-edge dataset-exploration technique menu
- `reference/workflow.md` — a rigor playbook for extracting multiple papers from one dataset
  (avoiding salami-slicing, forking-paths control, reproducibility)

Copy them into `~/.claude/` to use.

## License

MIT © Moin Sabri
