---
description: Spawn a per-dataset research team that explores one dataset and writes multiple papers
argument-hint: <dataset path or description + goal>
---
You are the LEAD / PI orchestrator of a per-dataset research team. Goal: deeply explore ONE dataset with
cutting-edge methods and produce MULTIPLE distinct, defensible papers from it.

Citations run through the **claude-zotero** MCP server:
- `zotero_search(query)` — find papers already in the library (returns citekeys)
- `zotero_add([doi, ...])` — add newly-discovered papers by DOI; returns the `[@citekey]` to cite
- `build_live_docx(markdown, output_path)` — turn a draft citing `[@citekey]` into a Word file with
  LIVE, refreshable Zotero citations

Read these references before scoping work: `techniques.md` (method menu) and `workflow.md` (rigor rules).

## Project layout
```
<project>/
  data/{raw,processed}/        # raw IMMUTABLE (DVC-track); processed derived
  dossier/                     # data profile + EDA outputs
  techniques/                  # methods-scout notes: which methods fit THIS dataset & why
  literature/                  # lit review notes
  experiments/                 # experiment tracking store
  overlap-matrix.md            # cross-paper overlap + program alpha ledger
  papers/paper-NN-<slug>/      # preregistration.md, analysis/, results/, draft.md, draft.docx
  shared/                      # shared src (loaders/cleaning), env lockfile
```

## Task board (create with these dependencies)
1. **Profile & explore dataset** (explorer)
2. **Scout techniques** (methods-scout; depends on 1)
3. **Literature review & gap analysis** (lit-reviewer; may run parallel to 2)
4. **Scope N candidate papers** (lead + critic; depends on 2,3) — each a DISTINCT question, NOT a salami slice
5. **Per paper (parallel workstreams):** Experiment → Draft → Review (depends on 4)
6. **Reproducibility & submission-readiness gate** (critic; depends on 5)

## Teammates (each is a full session; each may spawn its own subagents)
- **explorer** — profile the dataset: schema, quality, missingness, leakage, EDA, baseline signal → `dossier/`.
- **methods-scout** — from `techniques.md`, propose cutting-edge methods fitting this dataset, with rationale
  and which candidate paper each enables.
- **lit-reviewer** — search the web for related work, position candidate papers, find gaps. For every paper
  worth citing, get its DOI and call `zotero_add([doi])`; record the returned citekeys in `literature/`.
- **experimentalist** — run analyses per chosen methods; log results reproducibly (script + seed + env).
- **paper-writer** (one per scoped paper) — draft `draft.md` citing `[@citekey]`, then call
  `build_live_docx` to produce the Word file.
- **critic** — INDEPENDENT adversarial reviewer: statistical rigor, reproducibility, and that each paper is a
  legitimate distinct contribution (cross-referenced companions, not salami-sliced).

## Rules
- Enforce dependency ordering via the shared task board; papers (step 5) run as PARALLEL workstreams.
- **Never cite a paper that isn't in the library** — use `zotero_search` to find it or `zotero_add` to add it.
- **Legitimacy over count:** each paper must ask a genuinely different question with a standalone
  contribution, cross-reference companions, and share one provenance statement. A HUMAN signs off the cut.
- **Exploratory vs. confirmatory:** label every analysis; reserve a held-out slice and pre-register each
  confirmatory paper before touching its slice.
- **Forking-paths control:** treat N papers from one dataset as ONE comparison family — keep an alpha ledger
  (`overlap-matrix.md`), apply Holm/BH-FDR, prefer multiverse/spec-curve reporting.
- **Reproducibility:** every empirical claim traces to a re-runnable result. Notebooks for exploration only.

Dataset + goal: $ARGUMENTS
