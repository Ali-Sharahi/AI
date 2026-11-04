"""Non-secret operational diagnostics and opt-in live service probes."""
from __future__ import annotations

import importlib.metadata
import os
import shutil
import subprocess
import sys
from typing import Any

import httpx

from .harness import ResearchClient, utc_now, validate_grobid_local_url


def _installed(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def doctor(*, grobid_url: str = "http://127.0.0.1:8070") -> dict[str, Any]:
    """Report availability, never display credential values or contact external providers."""
    grobid_url = validate_grobid_local_url(grobid_url)
    docker = shutil.which("docker") is not None
    daemon = False
    if docker:
        try:
            cmd = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                                 check=False, capture_output=True, text=True, timeout=4)
            daemon = cmd.returncode == 0
        except (subprocess.SubprocessError, OSError):
            pass
    grobid_alive = False
    try:
        with httpx.Client(timeout=3, follow_redirects=False) as client:
            response = client.get(grobid_url.rstrip("/") + "/api/isalive")
            grobid_alive = response.status_code == 200 and response.text.strip().lower() in ("true", "alive")
    except httpx.HTTPError:
        pass
    return {
        "checked_at_utc": utc_now(), "python": sys.version.split()[0],
        "packages": {"harness": _installed("scientific-research-harness"), "paper-qa": _installed("paper-qa")},
        "commands": {"pqa": bool(shutil.which("pqa")), "docker": docker, "docker_daemon": daemon},
        "grobid_local_alive": grobid_alive,
        "credentials_present": {"openalex": bool(os.getenv("OPENALEX_API_KEY")),
                                "semantic_scholar": bool(os.getenv("SEMANTIC_SCHOLAR_API_KEY")),
                                "crossref_contact": bool(os.getenv("CROSSREF_MAILTO")),
                                "llm_provider": bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))},
        "note": "Credential presence does not verify authorization. No secrets are logged.",
    }


def smoke_live(*, query: str = "distributed control", limit: int = 2) -> dict[str, Any]:
    """Probe real public scholarly services (never runs unless explicitly invoked)."""
    if not 1 <= limit <= 5:
        raise ValueError("smoke limit must be 1..5")
    status: dict[str, Any] = {}
    with ResearchClient(timeout=15) as client:
        for name, run in (
            ("openalex", lambda: client.openalex(query, limit)),
            ("semantic_scholar", lambda: client.semantic(query, limit)),
            ("arxiv", lambda: client.arxiv(query, limit)),
            ("crossref", lambda: client.crossref(title="deep learning")),
        ):
            try:
                response = run()
                count = len(response) if isinstance(response, list) else int(bool(response))
                status[name] = {"status": "ok" if count else "empty", "records": count}
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                label = "rate_limited" if code == 429 else "unauthorized" if code in (401, 403) else "http_error"
                status[name] = {"status": label, "http_code": code}
            except (httpx.HTTPError, ValueError, KeyError, ImportError, OSError) as exc:
                status[name] = {"status": "error", "error_type": type(exc).__name__}
    return {"checked_at_utc": utc_now(), "query": query, "services": status,
            "status": "ok" if all(v["status"] == "ok" for v in status.values()) else "incomplete",
            "note": "API reachability is not scientific validation or exhaustive literature coverage."}
