"""Command-line interface for the research harness."""
from __future__ import annotations
import argparse
import json
import sys
import httpx
import xml.etree.ElementTree as ET
import subprocess
from pathlib import Path

from .harness import (ResearchClient, VERSION, deduplicate, gate_claims, paperqa_ask,
                      utc_now, verify_references, write_json, write_matrix)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rh", description="Research discovery and evidence auditing")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("discover", help="Search scholarly metadata providers")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10, help="Max records per provider (1..100)")
    s.add_argument("--providers", nargs="+", choices=["openalex", "semantic", "arxiv"],
                   default=["openalex", "semantic", "arxiv"])
    s.add_argument("--out", type=Path, default=Path("results/discovery.json"))
    b = sub.add_parser("bibliography", help="Extract PDF references with local GROBID")
    b.add_argument("pdf", type=Path)
    b.add_argument("--grobid-url", default="http://localhost:8070")
    b.add_argument("--verify", action="store_true", help="Send extracted DOI/titles to Crossref for metadata checks")
    b.add_argument("--out", type=Path, default=Path("results/bibliography.json"))
    m = sub.add_parser("matrix", help="Generate a blank, reviewable evidence matrix CSV")
    m.add_argument("discovery", type=Path)
    m.add_argument("--out", type=Path, default=Path("results/evidence-matrix.csv"))
    g = sub.add_parser("gate", help="Fail-closed claim evidence checklist")
    g.add_argument("claims", type=Path)
    g.add_argument("--out", type=Path, default=Path("results/gate-report.json"))
    a = sub.add_parser("ask", help="Run separately installed PaperQA on local PDF folder")
    a.add_argument("question")
    a.add_argument("--pdf-dir", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "discover":
            if not 1 <= args.limit <= 100:
                raise ValueError("--limit must be between 1 and 100")
            papers = []
            errors = {}
            with ResearchClient() as client:
                for name in dict.fromkeys(args.providers):
                    try:
                        papers.extend(getattr(client, name)(args.query, args.limit))
                    except Exception as exc:
                        errors[name] = (f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError)
                                        else type(exc).__name__)
            unique = deduplicate(papers)
            write_json(args.out, {"query": args.query, "retrieved_at_utc": utc_now(),
                                  "providers": args.providers, "count": len(unique),
                                  "papers": unique, "provider_errors": errors})
            print(f"Saved {len(unique)} records to {args.out}; provider errors: {len(errors)}")
            return 0 if unique and not errors else 2
        if args.command == "bibliography":
            with ResearchClient() as client:
                refs = client.grobid_references(args.pdf, args.grobid_url)
                if args.verify:
                    refs = verify_references(refs, client)
            write_json(args.out, {"pdf_name": args.pdf.name, "retrieved_at_utc": utc_now(),
                                  "crossref_checked": args.verify, "references": refs})
            print(f"Saved {len(refs)} extracted references to {args.out}")
            return 0
        if args.command == "matrix":
            obj = json.loads(args.discovery.read_text(encoding="utf-8"))
            write_matrix(obj["papers"], args.out)
            print(f"Evidence matrix: {args.out}")
            return 0
        if args.command == "gate":
            obj = json.loads(args.claims.read_text(encoding="utf-8"))
            report = gate_claims(obj)
            write_json(args.out, report)
            print(f"Evidence gate: {report['status']}; report: {args.out}")
            return 0 if report["status"] == "READY_FOR_EXTERNAL_REVIEW" else 2
        if args.command == "ask":
            paperqa_ask(args.pdf_dir, args.question)
            return 0
        raise RuntimeError("Unknown command")
    except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError,
            httpx.HTTPError, ET.ParseError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
