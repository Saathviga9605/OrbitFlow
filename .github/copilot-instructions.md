# OrbitFlow — standing instructions for Copilot

This repository is a hackathon project (ITU AI for Good Sandbox Build-a-thon 5.0). The single source of truth is
`docs/COPILOT_BUILD_SPEC.md`. Read it before any change and follow its milestone order (M1 → M10).

Always:
- Keep existing public signatures in `traffic/`, `digital_twin/`, `bam/`, `bridge/baselines.py`, `bridge/evaluate.py`, `audit/`.
- Take every tunable from `config.yaml`; seed everything from `config.yaml: seed`.
- CPU only; every training/eval script supports `--fast`.
- Run `python -m pytest -q tests` and the milestone ACCEPTANCE command before committing; one commit per milestone.
- Record assumptions as one line in `docs/ASSUMPTIONS.md`; do not stop to ask questions.

Never:
- Invent citations, section numbers, laws, or documents. Citations must resolve to ingested chunks (`rag/citations.py`).
- Train on the real dataset trace, or select models on the test split.
- Let an LLM override a guardrail or change a number.
- Call Gumbel-Top-K "differentiable selection" (it is a sampler with a Plackett-Luce log-probability; learning uses policy gradients).
- Hide negative results. Label synthetic and simulated components wherever they appear.
