# Cutting-Edge Dataset Exploration — Technique Menu (2025–2026)

Purpose: a menu the **methods-scout** consults to match a dataset to cutting-edge methods, and to
turn one dataset into several distinct paper angles. Each entry: what it's for / when / modern tool.
🔴 = bleeding-edge/unstable — treat as a *paper angle*, not infrastructure. Always re-benchmark on the
actual dataset; leaderboard rank ≠ performance on your data.

---

## 0. Domain priorities — EXAMPLE: applied ML for sustainability
*(Replace this section with your own domain's priorities. Shown as a worked example: fuel cells, CO₂ capture, renewables, wastewater.)*
Reach for these FIRST in this domain; they're where the strongest, most defensible papers live.

- **Physics-informed ML (PINNs / physics-constrained NNs)** — embed governing equations (mass/charge transport,
  reaction kinetics, thermodynamics) so models respect physics with scarce data; great for fuel-cell/electrolyzer
  polarization, CO₂-capture kinetics, wastewater reaction–transport. → **DeepXDE**, **NVIDIA Modulus**, `torchphysics`. 🔴 training stiffness real.
- **Surrogate modeling + Bayesian optimization** — cheap emulators of expensive experiments/simulations, then
  optimize operating conditions / material composition sample-efficiently. → **BoTorch/Ax**, **scikit-optimize**, GP surrogates. Materials: **pymatgen/matminer**.
- **Multi-objective optimization** — the sustainability core: trade off efficiency vs. cost vs. emissions vs. durability; report Pareto fronts. → **pymoo** (NSGA-II/III), Ax multi-objective.
- **Uncertainty quantification / conformal prediction** — distribution-free prediction intervals with coverage
  guarantees; makes every engineering claim reviewer-proof. → **MAPIE**, **crepes**, **TorchCP**; Bayesian/ensemble via **laplace-torch**. (⚠ conformal assumes exchangeability — check for drift.)
- **Causal inference for interventions** — move from "correlates" to "causes/effect of changing operating variable X". → PyWhy: **DoWhy** + **EconML** + **causal-learn**.
- **Time-series foundation models** — renewables generation/load, sensor streams: zero-shot forecasting + probabilistic intervals + TS embeddings. → **Chronos-2**, **Moirai-2.0**, **TimesFM**. 🔴 moves weekly.
- **LCA / techno-economic framing** — a distinct paper angle: pair the ML result with life-cycle-assessment or
  techno-economic analysis (cost/CO₂ per unit). Often the highest-impact companion paper. (`brightway2` for LCA.)

---

## 1. Representation learning & foundation-model embeddings
Embed raw modality → features matrix everything downstream runs on. Embed first, then explore.
- **Tabular ICL FMs** — instant zero-shot baseline + "is there signal?" probe on small–medium tables. → **TabPFN-2.5** (~100k rows), **TabICLv2** 🔴.
- **Text embeddings** — semantic clustering/retrieval/dedup/drift over text columns. → **Qwen3-Embedding-8B**, **BGE-M3**; check live **MTEB**.
- **Image encoders** — dense visual features (SEM/microscopy imagery, defect detection). → **DINOv3**, **SigLIP 2**.
- **Graph FMs** — relational/network data with little tuning. → **GraphPFN** 🔴, **PyG**/**DGL**.
- **Time-series FMs** — see domain section above.

## 2. Self-supervised / contrastive
Labels scarce/absent → learn structure, then probe. → **DINOv3** (images), **SubTab/SCARF** (tabular), **MOMENT/TS2Vec** (time-series).

## 3. Causal discovery & inference
Turn "X correlates Y" into a higher-value "X causes Y" paper. Discovery: **causal-learn** (PC, GES, LiNGAM, NOTEARS).
Effects: **DoWhy** (+refutation tests), **EconML** (heterogeneous), **CausalML** (uplift). LLM-proposed edges 🔴 — hypotheses only, always test.

## 4. TDA / manifold / dimensionality reduction
Exploratory backbone — maps + shape features that seed figures/hypotheses. → **PaCMAP** (balanced local+global) + **UMAP** baseline;
topology via **giotto-tda** / **Ripser** / **gudhi**. ⚠ DR plots lie about distances/cluster sizes — validate with HDBSCAN/TDA before claiming clusters.

## 5. Clustering & community detection
Each meaningful cluster = a potential subgroup paper. → **HDBSCAN** (on embeddings), **Leiden** (`leidenalg`, graphs), deep clustering for images.

## 6. Anomaly / novelty / OOD
Find the strange 1% — rare events, data-quality issues, "interesting exceptions" papers. → **PyOD 3** (60+ detectors, unified API),
DINOv3-based few-shot anomaly 🔴, Mahalanobis/energy on embeddings + **pytorch-ood**.

## 7. Interpretability / explainability
Black-box result → explanation (often what makes it a *paper*). → **shap** + **captum** (deep), **InterpretML** (EBM, PDP/ALE),
Concept Bottleneck Models; mechanistic/SAE (`TransformerLens`, `nnsight`) 🔴 for models you train.

## 8. AutoML & automated feature discovery
Cheap strong baselines + auto features → spend time on novelty, not grid search. → **AutoGluon** (tabular/TS/multimodal), **FLAML**;
features via **featuretools**, **OpenFE**, **tsfresh** (time-series).

## 9. Multimodal fusion
When the dataset spans modalities the joint view is often the most novel paper. → shared-space embeddings, CLIP/SigLIP aligners, cross-attention/late fusion (**transformers**, Lightning).

## 10. LLM-assisted analysis (agents that hypothesize, code, critique)
Orchestration layer — propose hypotheses, write/run analysis code, self-critique. → **Data Interpreter** (MetaGPT), **DS-STAR** pattern 🔴.
Guardrails: conformal + refutation tests. Verify every agent claim statistically.

---

## Practical default stack
Embeddings: TabPFN-2.5 (tabular), Qwen3/BGE-M3 (text), Chronos-2/Moirai-2 (time-series) · DR: PaCMAP+UMAP, giotto-tda ·
Clustering: HDBSCAN, Leiden · Anomaly: PyOD 3 · Causal: DoWhy+EconML+causal-learn · AutoML/features: AutoGluon+tsfresh ·
Explain: SHAP+InterpretML+Captum · UQ: MAPIE · Domain: DeepXDE (PINNs), BoTorch/Ax (surrogate+BO), pymoo (multi-objective), brightway2 (LCA).

## Cross-cutting cautions
1. TS/tabular FMs move weekly — re-benchmark on your data. 2. DR plots distort distances/sizes — validate before claiming clusters.
3. LLM/agent hypotheses + causal edges are unverified until tested. 4. Conformal needs exchangeability — check for drift/time-series.

*Compiled from a 2026 web sweep (TabPFN-2.5, TabICLv2, PaCMAP, giotto-tda, MAPIE, PyOD 3, DINOv3, PyWhy, Chronos-2/Moirai-2/TimesFM, DS-STAR).*
