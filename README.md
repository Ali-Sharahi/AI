# Scientific Research Harness for Codex

A reproducible, **fail-closed** research workflow: OpenAlex + Semantic Scholar + arXiv discovery; GROBID bibliography extraction; Crossref metadata comparison; evidence matrices; optional PaperQA; and an explicit claim-quality gate.

This repository includes `AGENTS.md` and a Codex-native skill at `.agents/skills/research-audit/SKILL.md`. It is a toolchain for research auditing, **not** a machine that proves scientific novelty.

## Install

Requires Python 3.11 or newer. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

Set API keys in your own environment. OpenAlex supports small anonymous queries, but a free key improves quota. Semantic Scholar can work without a key subject to stricter rate limits. Do not commit `.env` or secret values.

```bash
export OPENALEX_API_KEY='...'
export SEMANTIC_SCHOLAR_API_KEY='...'
export CROSSREF_MAILTO='your-public-contact@example.org'
```

## Literature discovery and matrix

```bash
rh discover 'distributed safety control finite-bit communication' --limit 10 --out results/discovery.json
rh matrix results/discovery.json --out results/evidence-matrix.csv
```

Discovery queries three providers and records **provider errors** instead of silently treating failures as empty results. Results are deduplicated by DOI or exact normalized title (when years agree). Read the actual full text before completing matrix cells. There is **no automated theorem comparison** in v0.1.

## PDF bibliography audit (local GROBID)

Install Docker and run GROBID locally using a [pinned image version](https://grobid.readthedocs.io/). Example only (choose a currently supported version instead of a floating tag):

```bash
docker run --rm --init -p 8070:8070 grobid/grobid:0.9.1-crf
curl http://localhost:8070/api/isalive
```

Then:

```bash
rh bibliography /path/to/manuscript.pdf --out results/bibliography.json
rh bibliography /path/to/manuscript.pdf --verify --out results/bibliography-checked.json
```

The first command sends the manuscript **only to the local** GROBID instance. The `--verify` flag additionally sends extracted DOI/title metadata (not the PDF) to Crossref. Crossref may not cover a record registered with another DOI agency. `MATCHED_METADATA` means the DOI lookup and title comparison agree; it is *not* proof that all citation fields are accurate or that the article is unretracted.

## Optional PaperQA

```bash
pip install '.[paperqa]'
# Configure the model provider and its credentials; this may incur API charges.
rh ask 'What assumptions govern the stability results?' --pdf-dir /path/to/authorized/pdfs
```

PaperQA processes local PDFs, but its chosen LLM/embedding provider may receive content. Only use PDFs for which the configured provider is authorized. Its answers must be checked against cited source locations.

## Claim gate

Copy and fill `examples/claims.template.json` and execute:

```bash
rh gate examples/claims.template.json --out results/gate-report.json
```

Exit code **2** means blocked or a provider error; code **0** from the gate means only `READY_FOR_EXTERNAL_REVIEW`, never "breakthrough proven". A gate cannot independently verify boolean attestations or scientific originality.

## Tests and caveats

- Tests use offline HTTP mocks and synthetic bibliography XML; no live API or GROBID server is needed.
- No automated scraping of restricted PDFs and no automatic mass paper downloads.
- No novel-theorem prover, full-text similarity solver, or experimental validation is claimed.
- arXiv search is full-text metadata query by default; it is not an exhaustive systematic review.
- Literature coverage depends on provider indexing, API permissions, and query strategy.
- Keep unpublished papers, API keys, and `results/` out of public Git history.

## Documentation

[Codex skill locations](https://learn.chatgpt.com/docs/build-skills) · [OpenAlex API](https://help.openalex.org/api/) · [Semantic Scholar API](https://api.semanticscholar.org/api-docs/graphs) · [GROBID API](https://grobid.readthedocs.io/) · [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) · [PaperQA on PyPI](https://pypi.org/project/paper-qa/)
