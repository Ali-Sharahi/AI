# Research harness: Codex instructions

Use the repository's `research-audit` skill for literature searches, reference checks, or novelty reviews.

1. Distinguish metadata discovery from full-text reading and experimental replication. Never infer theorem assumptions or novelty from titles or abstracts alone.
2. Never fabricate identifiers, DOI values, paper content, quotations, page numbers, experiments, or references.
3. Mark unknown or unreviewed evidence as `NOT_REVIEWED`. Record source identifiers, dates and exact locations for every substantive claim.
4. For originality: compare the nearest prior formal results, assumptions, counterexamples, and experimental baselines; report unresolved overlap explicitly. Never label a contribution "proven novel" because a literature search returned no match.
5. Keep unpublished PDFs, credentials and project data outside Git; never transmit local PDFs to third-party services without explicit authorization. GROBID is local-only by default.
6. Run `python -m pytest -q` before proposing code changes. Keep API errors visible, not masked as empty results.
7. Codex should use the CLI from an activated environment: `rh discover`, `rh bibliography`, `rh matrix`, `rh gate`, or `rh ask`.


## Operational checks

- Run `rh doctor` to inspect local Docker, GROBID and optional PaperQA readiness.
- Run `rh smoke` only when network access and rate budgets permit; inspect all
  provider statuses before reporting discovery completeness.
- Use `docker compose up -d grobid` for local extraction. Do not upload private
  manuscripts to remote PDF parsing services without the owner's explicit approval.
- `pqa --help` verifies CLI installation only; live LLM invocation requires separate
  credentials/permissions and may incur costs. Never promise it works without testing.
