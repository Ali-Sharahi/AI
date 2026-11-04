"""Literature discovery, PDF citation auditing, and evidence gating.

Metadata matching is not a verification of scientific conclusions.
"""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit
import xml.etree.ElementTree as ET

import httpx

VERSION = "0.2.0"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
TEI = "{http://www.tei-c.org/ns/1.0}"
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def validate_grobid_local_url(url: str) -> str:
    """Reject userinfo, remote hosts, unexpected paths and malformed loopback URLs."""
    try:
        parsed = urlsplit(url)
        allowed_host = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        safe = (parsed.scheme == "http" and allowed_host and parsed.port is not None
                and parsed.username is None and parsed.password is None
                and parsed.path in ("", "/") and not parsed.query and not parsed.fragment)
    except ValueError:
        safe = False
    if not safe:
        raise ValueError("GROBID URL must be a local loopback HTTP URL with an explicit port, e.g. http://127.0.0.1:8070")
    return url.rstrip("/")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normal_doi(value: Any) -> str | None:
    if not value:
        return None
    m = DOI_RE.search(str(value))
    return m.group(0).lower().rstrip(".,;)") if m else None


def clean_title(value: str) -> str:
    return re.sub(r"[^\w]+", " ", (value or "").casefold()).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, clean_title(a), clean_title(b)).ratio()


def paper(title: str, source: str, **kwargs: Any) -> dict[str, Any]:
    doi = normal_doi(kwargs.get("doi"))
    return {
        "title": " ".join((title or "").split()),
        "doi": doi,
        "year": kwargs.get("year"),
        "authors": kwargs.get("authors") or [],
        "abstract": kwargs.get("abstract") or "",
        "url": kwargs.get("url") or "",
        "open_access_pdf": kwargs.get("open_access_pdf") or "",
        "sources": [source],
        "source_ids": {source: kwargs.get("source_id") or ""},
    }


def deduplicate(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use DOI where possible; use strong normalized title match otherwise."""
    out: list[dict[str, Any]] = []
    for p in papers:
        if not p.get("title"):
            continue
        target = next((q for q in out if p.get("doi") and q.get("doi") == p["doi"]), None)
        if target is None:
            target = next((q for q in out if clean_title(q["title"]) == clean_title(p["title"])
                           and (q.get("year") == p.get("year") or not q.get("year") or not p.get("year"))), None)
        if target is None:
            out.append(dict(p))
            continue
        for source in p["sources"]:
            if source not in target["sources"]:
                target["sources"].append(source)
        target["source_ids"].update(p["source_ids"])
        for key in ("doi", "year", "abstract", "url", "open_access_pdf"):
            if not target.get(key) and p.get(key):
                target[key] = p[key]
        if len(p.get("authors", [])) > len(target.get("authors", [])):
            target["authors"] = p["authors"]
    return out


def openalex_abstract(inverted: Any) -> str:
    if not isinstance(inverted, dict):
        return ""
    loc = [(pos, word) for word, places in inverted.items() for pos in places if isinstance(pos, int) and 0 <= pos < 5000]
    loc.sort()
    return " ".join(word for _, word in loc)


class ResearchClient:
    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 30):
        self.http = httpx.Client(timeout=timeout, transport=transport,
                                 headers={"User-Agent": "scientific-research-harness/0.2 (research metadata auditing)"},
                                 follow_redirects=False)

    def __enter__(self) -> "ResearchClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.http.close()

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        # Bounded retry; never retry arbitrary non-transient HTTP failures.
        for attempt in range(3):
            try:
                r = self.http.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == 2:
                    raise
                time.sleep(0.25 * (2 ** attempt))
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                retry_after = r.headers.get("Retry-After", "")
                delay = min(float(retry_after), 6.0) if retry_after.replace(".", "", 1).isdigit() else 0.5 * (2 ** attempt)
                time.sleep(delay)
                continue
            r.raise_for_status()
            return r
        raise RuntimeError("Unreachable retry state")

    def openalex(self, query: str, limit: int) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"search": query, "per_page": limit}
        if os.getenv("OPENALEX_API_KEY"):
            params["api_key"] = os.environ["OPENALEX_API_KEY"]
        payload = self.request("GET", "https://api.openalex.org/works", params=params).json()
        result = []
        for item in payload.get("results", []):
            result.append(paper(item.get("display_name") or item.get("title", ""), "openalex",
                                doi=item.get("doi"), year=item.get("publication_year"),
                                authors=[x.get("author", {}).get("display_name") for x in item.get("authorships", []) if x.get("author", {}).get("display_name")],
                                abstract=openalex_abstract(item.get("abstract_inverted_index")),
                                url=item.get("id"),
                                open_access_pdf=(item.get("best_oa_location") or {}).get("pdf_url"),
                                source_id=item.get("id")))
        return result

    def semantic(self, query: str, limit: int) -> list[dict[str, Any]]:
        headers = {}
        if os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
            headers["x-api-key"] = os.environ["SEMANTIC_SCHOLAR_API_KEY"]
        payload = self.request("GET", "https://api.semanticscholar.org/graph/v1/paper/search",
                               params={"query": query, "limit": limit,
                                       "fields": "title,year,authors,abstract,url,externalIds,openAccessPdf"},
                               headers=headers).json()
        return [paper(x.get("title", ""), "semantic_scholar",
                      doi=(x.get("externalIds") or {}).get("DOI"), year=x.get("year"),
                      authors=[a.get("name") for a in x.get("authors", []) if a.get("name")],
                      abstract=x.get("abstract"), url=x.get("url"),
                      open_access_pdf=(x.get("openAccessPdf") or {}).get("url"),
                      source_id=x.get("paperId")) for x in payload.get("data", [])]

    def arxiv(self, query: str, limit: int) -> list[dict[str, Any]]:
        # HTTPS Atom endpoint. arXiv sets service limits; do not batch aggressively.
        response = self.request("GET", "https://export.arxiv.org/api/query",
                                params={"search_query": " AND ".join(f"all:{term}" for term in re.findall(r"[\w-]+", query)) or "all:research", "start": 0, "max_results": limit,
                                        "sortBy": "relevance", "sortOrder": "descending"})
        root = ET.fromstring(response.content)
        out = []
        for e in root.findall(f"{ATOM}entry"):
            url = e.findtext(f"{ATOM}id") or ""
            pdfs = [x.attrib.get("href", "") for x in e.findall(f"{ATOM}link") if x.attrib.get("title") == "pdf"]
            published = e.findtext(f"{ATOM}published") or ""
            out.append(paper(e.findtext(f"{ATOM}title") or "", "arxiv",
                             doi=e.findtext(f"{ARXIV}doi"), year=int(published[:4]) if published[:4].isdigit() else None,
                             authors=[a.findtext(f"{ATOM}name") for a in e.findall(f"{ATOM}author") if a.findtext(f"{ATOM}name")],
                             abstract=e.findtext(f"{ATOM}summary"), url=url,
                             open_access_pdf=pdfs[0] if pdfs else "", source_id=url))
        return out

    def crossref(self, *, doi: str | None = None, title: str | None = None) -> dict[str, Any] | None:
        if not doi and not title:
            raise ValueError("DOI or title required")
        params: dict[str, Any] = {}
        if os.getenv("CROSSREF_MAILTO"):
            params["mailto"] = os.environ["CROSSREF_MAILTO"]
        if doi:
            normal = normal_doi(doi)
            if not normal:
                return None
            url = "https://api.crossref.org/works/" + quote(normal, safe="")
        else:
            url = "https://api.crossref.org/works"
            params.update({"query.bibliographic": title, "rows": 1})
        try:
            data = self.request("GET", url, params=params).json()["message"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        if title:
            return next(iter(data.get("items", [])), None)
        return data

    def grobid_references(self, pdf: Path, grobid_url: str) -> list[dict[str, Any]]:
        if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
            raise ValueError("Expected an existing PDF")
        # Do not upload private PDFs to a remote host disguised as a loopback URL.
        grobid_url = validate_grobid_local_url(grobid_url)
        with pdf.open("rb") as f:
            resp = self.request("POST", grobid_url.rstrip("/") + "/api/processReferences",
                                files={"input": (pdf.name, f, "application/pdf")},
                                data={"includeRawCitations": "1", "consolidateCitations": "0"},
                                timeout=120)
        return parse_tei_references(resp.content)


def parse_tei_references(content: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(content)
    entries = root.findall(f".//{TEI}listBibl/{TEI}biblStruct")
    if not entries:
        entries = root.findall(f".//{TEI}biblStruct")
    result = []
    for i, e in enumerate(entries, 1):
        title = (e.findtext(f".//{TEI}analytic/{TEI}title")
                 or e.findtext(f".//{TEI}monogr/{TEI}title") or "")
        doi = next((node.text for node in e.findall(f".//{TEI}idno")
                    if (node.attrib.get("type") or "").lower() == "doi"), None)
        raw = next(("".join(node.itertext()).strip() for node in e.findall(f".//{TEI}note")
                    if node.attrib.get("type") == "raw_reference"), "")
        surnames = [s.text for s in e.findall(f".//{TEI}author/{TEI}persName/{TEI}surname") if s.text]
        result.append({"index": i, "title": " ".join(title.split()), "doi": normal_doi(doi),
                       "authors": surnames, "raw_reference": raw,
                       "status": "NOT_CHECKED", "matched_title": "", "matched_doi": "", "title_similarity": None})
    return result


def verify_references(refs: list[dict[str, Any]], client: ResearchClient) -> list[dict[str, Any]]:
    checked = []
    for item in refs:
        row = dict(item)
        try:
            record = client.crossref(doi=row["doi"]) if row["doi"] else client.crossref(title=row["title"]) if row["title"] else None
            if record is None:
                row["status"] = "NOT_FOUND_IN_CROSSREF" if row["doi"] else "UNVERIFIED"
            else:
                matched_title = next(iter(record.get("title") or []), "")
                score = similarity(row["title"], matched_title) if row["title"] and matched_title else 0.0
                row.update(matched_title=matched_title, matched_doi=normal_doi(record.get("DOI")) or "",
                           title_similarity=round(score, 3))
                if row["doi"]:
                    row["status"] = "MATCHED_METADATA" if score >= 0.9 else "METADATA_MISMATCH_OR_INCOMPLETE"
                else:
                    row["status"] = "POSSIBLE_MATCH_REVIEW_REQUIRED" if score >= 0.9 else "UNVERIFIED"
        except (httpx.HTTPError, ValueError, KeyError) as e:
            row["status"] = "LOOKUP_ERROR"
            row["error"] = type(e).__name__
        checked.append(row)
    return checked


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_matrix(papers: list[dict[str, Any]], target: Path) -> None:
    fields = ["paper_id", "title", "doi", "year", "sources", "assumptions", "theorem_or_claim",
              "method", "evidence_locator", "experiment_and_dataset", "relation_to_our_work", "review_status"]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for i, p in enumerate(papers, 1):
            writer.writerow({"paper_id": f"P{i:04d}", "title": p["title"], "doi": p.get("doi") or "",
                             "year": p.get("year") or "", "sources": "; ".join(p.get("sources", [])),
                             "review_status": "NOT_REVIEWED"})


def gate_claims(obj: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed eligibility check, not a scientific novelty certification."""
    output = []
    for i, claim in enumerate(obj.get("claims", []), 1):
        missing = []
        for k in ("claim", "formal_proof", "proof_independently_checked", "reproducible_experiment",
                  "experiment_independently_reproduced", "closest_prior_work_comparison"):
            v = claim.get(k)
            if ((v is not True) if k in ("proof_independently_checked", "experiment_independently_reproduced")
                else (not v or (isinstance(v, str) and v.strip().upper().startswith("REPLACE")))):
                missing.append(k)
        evidence = claim.get("evidence", [])
        if not isinstance(evidence, list) or not evidence or not all(
            isinstance(e, dict) and e.get("paper_id") and e.get("locator") and e.get("excerpt") and not str(e["excerpt"]).startswith("exact short")
            for e in evidence
        ):
            missing.append("locatable_primary_evidence")
        output.append({"claim_index": i, "claim": claim.get("claim", ""),
                       "gate": "READY_FOR_EXTERNAL_REVIEW" if not missing else "BLOCKED",
                       "missing": missing})
    return {"status": "READY_FOR_EXTERNAL_REVIEW" if output and all(x["gate"] == "READY_FOR_EXTERNAL_REVIEW" for x in output)
            else "BLOCKED", "claims": output,
            "warning": "A passed checklist does not establish novelty, validity, or publication readiness."}


def paperqa_ask(directory: Path, question: str) -> None:
    if not directory.is_dir() or not list(directory.glob("*.pdf")):
        raise ValueError("Provide a directory containing at least one PDF")
    try:
        subprocess.run(["pqa", "ask", question], cwd=directory, check=True)
    except FileNotFoundError as e:
        raise RuntimeError("PaperQA not installed. Run: pip install 'paper-qa>=5'") from e
