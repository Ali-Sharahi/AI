import json
from unittest.mock import patch

import httpx

from research_harness.cli import main
from research_harness.diagnostics import doctor, smoke_live


def test_doctor_never_exposes_credentials(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "SECRET_DO_NOT_LOG")
    with patch("research_harness.diagnostics.shutil.which", return_value=None):
        with patch("research_harness.diagnostics.httpx.Client.get", side_effect=httpx.ConnectError("offline")):
            report = doctor()
    assert report["credentials_present"]["openalex"] is True
    assert "SECRET_DO_NOT_LOG" not in json.dumps(report)
    assert report["grobid_local_alive"] is False


def test_doctor_rejects_remote_grobid():
    try:
        doctor(grobid_url="https://papers.example.com")
        assert False, "Remote GROBID URL unexpectedly accepted"
    except ValueError:
        pass


def test_live_smoke_all_success():
    with patch("research_harness.diagnostics.ResearchClient") as cls:
        cl = cls.return_value.__enter__.return_value
        cl.openalex.return_value = [{"title": "a"}]
        cl.semantic.return_value = [{"title": "b"}]
        cl.arxiv.return_value = [{"title": "c"}]
        cl.crossref.return_value = {"DOI": "10.1/a"}
        report = smoke_live()
    assert report["status"] == "ok"
    assert all(entry["status"] == "ok" for entry in report["services"].values())


def test_smoke_partial_failure_does_not_claim_success():
    with patch("research_harness.diagnostics.ResearchClient") as cls:
        cl = cls.return_value.__enter__.return_value
        cl.openalex.return_value = [{"title": "a"}]
        cl.semantic.side_effect = httpx.ConnectError("offline")
        cl.arxiv.return_value = []
        cl.crossref.return_value = {"DOI": "10.1/a"}
        report = smoke_live()
    assert report["status"] == "incomplete"
    assert report["services"]["semantic_scholar"]["status"] == "error"
    assert report["services"]["arxiv"]["status"] == "empty"


def test_cli_smoke_diagnostics(tmp_path):
    out = tmp_path / "status.json"
    with patch("research_harness.cli.smoke_live", return_value={"status": "incomplete"}):
        assert main(["smoke", "--out", str(out)]) == 2
    assert json.loads(out.read_text())["status"] == "incomplete"


def test_grobid_blocks_userinfo_redirect_like_url(tmp_path):
    from research_harness.harness import ResearchClient, validate_grobid_local_url
    import pytest
    malicious = ["http://localhost:8070@evil.example", "http://127.0.0.1:8070@evil.example",
                 "http://localhost:8070/other", "https://localhost:8070", "http://[::1]:8070@evil.example"]
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    for url in malicious:
        with pytest.raises(ValueError):
            validate_grobid_local_url(url)
        with ResearchClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))) as client:
            with pytest.raises(ValueError):
                client.grobid_references(pdf, url)
