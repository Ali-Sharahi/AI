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
