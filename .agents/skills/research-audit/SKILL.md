---
name: research-audit
description: Use for scientific literature discovery, evidence matrices, PDF bibliography authenticity screening, claim verification, and novelty comparisons requiring source traceability. Do not use for creative prose or for declaring a breakthrough without full-text, proofs, and reproduced experiments.
---

# Scientific research audit (Codex skill)

## Discovery
1. Execute `rh discover "<topic>" --limit 15 --out results/discovery.json`.
2. Inspect `provider_errors`; never interpret a failed provider as zero published papers.
3. Execute `rh matrix results/discovery.json --out results/evidence-matrix.csv`.
4. Prioritize high-overlap papers. Open **full text** before filling assumptions, theorem claims, or experimental comparisons. Each entry must have a page/section/DOI locator and review status.

## Bibliography
1. Start GROBID locally with a pinned Docker image version; check `http://localhost:8070/api/isalive`.
2. Execute `rh bibliography manuscript.pdf --verify --out results/bibliography.json` only if it is permitted to send reference metadata to Crossref. Without `--verify`, processing stays local.
3. `MATCHED_METADATA` proves only a strong title/DOI metadata match. Review author, venue, year, pages, and retraction/correction status separately. `NOT_FOUND_IN_CROSSREF` does not prove fabrication, because Crossref is not the only DOI registration agency.

## PaperQA (optional)
1. Install `pip install '.[paperqa]'`, configure the selected LLM keys, and confirm API costs/privacy requirements.
2. Execute `rh ask "<question>" --pdf-dir /path/to/authorized/pdfs`.
3. Verify all model-generated citations against the underlying PDF before including them in a manuscript.

## Novelty gating
1. Prepare claims with the schema in `examples/claims.template.json`.
2. Run `rh gate examples/claims.template.json --out results/gate-report.json`.
3. The `READY_FOR_EXTERNAL_REVIEW` gate means fields are present and self-reported as independently checked. It does **not** establish novelty, formal correctness, or reproducibility; expert verification is indispensable.
4. Provide a conservative report: nearest prior work, assumption-by-assumption differences, proof status, counterexamples, baseline parity, uncertainty, and reproducibility commands.
