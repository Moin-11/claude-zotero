# Multi-Paper-Per-Dataset Playbook (rigor + reproducibility)

Purpose: the process the team follows to extract MULTIPLE legitimate papers from ONE dataset without
salami-slicing or false positives. The **critic** enforces these rules; a **human owns the final go/no-go**.

---

## 1. Legitimate decomposition vs. salami slicing
A slice is legitimate only if ALL hold:
- Asks a **genuinely different question** (not same hypothesis+population+methods repackaged).
- Makes a **standalone contribution** unavailable from the companion papers.
- **Discloses the shared dataset** and **cross-references** companion papers explicitly.
- **Non-redundant framing** — no recycled intro/discussion/conclusions.

**Defensible axes** (each = a distinct paper): different research question/outcome · different sub-population or
time window · a **methods/benchmark/data-descriptor** paper vs. the findings paper · different level of analysis
(individual vs. network; cross-sectional vs. longitudinal) · different modality · **LCA/techno-economic companion**
to an ML-results paper (strong in this domain).
**Avoid** slicing by one more predictor, arbitrary subgroup, or single outcome variable — those are thin slices.

**Cross-reference protocol:** disclose all related/under-review papers to the editor; cite companions in text (back-fill
as they publish); state how each manuscript extends beyond the others; keep one identical provenance statement
(dataset ID, collection window, registration) across the paper family. Missing cross-refs is *the* trigger that turns
"companion papers" into "redundant publication" (COPE).

## 2. Statistical rigor when mining one dataset
**Garden of forking paths (Gelman & Loken):** false-positive rates inflate even without conscious p-hacking, as
long as any analytic choice is data-contingent. Mining one dataset for many papers multiplies these forks — this is
the central threat. Layered defenses (no single one suffices):
- **Label every analysis exploratory vs. confirmatory.**
- **Held-out / split-sample:** reserve a confirmation slice untouched during exploration; promote a finding to a
  confirmatory paper only after it survives the held-out test. (Cleanest exploratory→confirmatory paper pair.)
- **Pre-register** each confirmatory paper's hypotheses/outcomes/plan *before touching that data slice*.
- **Program-level multiple-comparison control** (Holm / Benjamini-Hochberg FDR): treat N papers from one dataset as
  ONE comparison family; keep an alpha ledger across papers.
- **Multiverse / specification-curve analysis:** run all justifiable preprocessing+modeling combinations, report the
  curve — surfaces whether a result is robust or a lucky fork. Complements pre-registration (which can't catch
  result-neutral forks like defensible transforms).

## 3. Reproducibility infrastructure (Python stack)
- **Data + pipeline versioning:** **DVC** (+ Git) — big files to remote, hash pointers in Git; `dvc.yaml`/`dvc.lock`
  capture the pipeline DAG. **Tag the exact data version per paper** so companions pin to reproducible snapshots.
- **Experiment tracking:** **MLflow** (or W&B) — params/metrics/artifacts/models per run. Division: DVC orchestrates
  data+stages; MLflow tracks what happens inside a stage.
- **Environment pinning:** `uv.lock` / `conda-lock` / `poetry.lock`, seed everything, record hardware if results are
  hardware-sensitive; Docker with digest-pinned base for confirmatory runs.
- **Notebook hygiene:** notebooks for exploration ONLY; promote confirmatory analyses to versioned scripts. Enforce
  top-to-bottom re-run (`papermill`/`nbval`), strip outputs in Git (`nbstripout`). No headline number lives only in a notebook.

## 4. Team roles, handoffs & gates
Structured artifacts (not chat) are the interface between agents. The **critic is a separate agent from the author**
(independence is what makes multi-agent critique work). Disagreements go to a judge/meta-review step, not silent averaging.

| Role | Mandate | Gate before handoff |
|---|---|---|
| **explorer** (profiler) | data dictionary, distributions, missingness, leakage/QC, candidate questions | profile regenerable from pinned data version; no leakage |
| **lit-reviewer** | novelty, prior art, positioning, companion landscape per question | claims cited to sources; novelty vs. own companions stated |
| **methods-scout** | match questions→defensible methods; enumerate the multiverse of justifiable pipelines | every analytic fork named + justified upfront |
| **lead / planner** | cut dataset into distinct paper units; assign slices; write per-paper pre-registration | each paper passes different-question/standalone test; alpha budget allocated |
| **experimentalist** | run pre-registered + multiverse analyses; log to MLflow; pin data via DVC | held-out test run; reproducible from commit; exp-vs-confirm labeled |
| **paper-writer** | draft each ms; companion cross-refs + provenance statement | cross-refs present; no recycled framing |
| **critic** | attack: forking-paths, salami risk, robustness, over-claiming; debate for/against+judge | independent of author; sign-off required to advance |

## 5. Phased workflow
0. **Charter & infra** — init mono-repo, DVC-track raw (immutable), pin env, stand up MLflow, write shared data dictionary + provenance statement.
1. **Profile & question generation** — explorer; gate: profile regenerable.
2. **Decompose into paper portfolio** — lead+lit-reviewer carve distinct units; draft overlap matrix + program alpha budget. **Gate: human sign-off the cut is legitimate, not salami.** 🔔
3. **Pre-register & split data** — per confirmatory paper, pre-register + reserve held-out slice before touching it; label exploratory vs. confirmatory. 🔔 notify human.
4. **Explore** — methods-scout+experimentalist iterate on the exploratory slice, enumerate the multiverse; promising findings become pre-registered hypotheses for Phase 5.
5. **Confirm** — run pre-registered analyses on held-out data + full spec-curve; log MLflow; pin data version per paper; apply program-wide multiple-comparison control.
6. **Write & cross-reference** — writer drafts (Markdown `@citekeys` → `md2docx.sh` → `.docx`), companion cross-refs, distinct framing, shared provenance.
7. **Adversarial review** — independent critic + for/against debate + judge adjudication; iterate. Gate: critic sign-off + human review.
8. **Coordinated submission** — reconcile overlap matrix, disclose related papers to editors, reconcile comparison ledger; submit as declared companion set. Human owns final go/no-go.

## Pitfalls → fixes
Redundant framing → overlap matrix + declared boilerplate · Missing cross-refs → automate a family cross-cite check ·
Untracked forking → program-level alpha ledger + multiverse reporting · Exploratory dressed as confirmatory → enforce
labels + pre-reg timestamps · Silent pipeline divergence → shared `src/` + pinned data · Notebook-only results → promote
to scripts · Over-trusting AI output → human-in-the-loop on novelty/ethics/final claims · Pre-reg overreliance → pair with multiverse.

*Compiled from a 2026 web sweep: COPE salami-slicing guidance, Gelman & Loken (forking paths), Steegen et al.
(multiverse), DVC+MLflow reproducibility, and LLM scientific-agent / multi-agent-review literature.*
