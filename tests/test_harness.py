from pathlib import Path
import json
import httpx
import pytest
from research_harness.harness import (ResearchClient, deduplicate, gate_claims, normal_doi,
                                      parse_tei_references, verify_references, write_matrix)
from research_harness.cli import main


def test_doi_and_deduplication():
    assert normal_doi('https://doi.org/10.1234/A.B.') == '10.1234/a.b'
    a = {"title": "A Formal Theorem", "doi": "10.1234/a", "year": 2025, "authors": [], "abstract": "", "url": "", "open_access_pdf": "", "sources": ["openalex"], "source_ids": {"openalex": "1"}}
    b = {**a, "sources": ["semantic_scholar"], "source_ids": {"semantic_scholar": "2"}}
    out = deduplicate([a, b])
    assert len(out) == 1
    assert set(out[0]["sources"]) == {"openalex", "semantic_scholar"}


def test_provider_parsers_and_dedup():
    atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/2401.00001</id><title>A Formal Theorem</title><summary>Result</summary><published>2024-01-01T00:00:00Z</published><author><name>Smith</name></author><link title="pdf" href="https://arxiv.org/pdf/2401.00001"/></entry></feed>'''
    def handle(request):
        if 'openalex' in str(request.url):
            return httpx.Response(200, json={"results": [{"title": "A Formal Theorem", "doi": "10.1234/test", "publication_year": 2024, "id": "W1"}]})
        if 'semanticscholar' in str(request.url):
            return httpx.Response(200, json={"data": [{"title": "A Formal Theorem", "year": 2024, "externalIds": {"DOI": "10.1234/test"}, "paperId": "S1"}]})
        return httpx.Response(200, content=atom)
    with ResearchClient(transport=httpx.MockTransport(handle)) as c:
        papers = deduplicate(c.openalex('theorem', 2) + c.semantic('theorem', 2) + c.arxiv('theorem', 2))
    assert len(papers) == 1
    assert set(papers[0]['sources']) == {'openalex', 'semantic_scholar', 'arxiv'}


def test_tei_and_crossref_verification():
    xml = b'''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><back><listBibl><biblStruct><analytic><title>Important Research Paper</title><author><persName><surname>Smith</surname></persName></author></analytic><idno type="DOI">10.1234/xyz</idno><note type="raw_reference">Smith ...</note></biblStruct></listBibl></back></text></TEI>'''
    refs = parse_tei_references(xml)
    assert len(refs) == 1 and refs[0]['doi'] == '10.1234/xyz'
    def handle(request):
        assert request.url.path.endswith('10.1234%2Fxyz') or request.url.path.endswith('10.1234/xyz')
        return httpx.Response(200, json={"message": {"title": ["Important Research Paper"], "DOI": "10.1234/xyz"}})
    with ResearchClient(transport=httpx.MockTransport(handle)) as client:
        checked = verify_references(refs, client)
    assert checked[0]['status'] == 'MATCHED_METADATA'


def test_crossref_not_found_is_not_fake():
    with ResearchClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as c:
        x = verify_references([{"doi": "10.9999/unknown", "title": "Unknown"}], c)
    assert x[0]['status'] == 'NOT_FOUND_IN_CROSSREF'


def test_gate_fails_closed():
    data = json.loads(Path('examples/claims.template.json').read_text())
    assert gate_claims(data)['status'] == 'BLOCKED'
    c = data['claims'][0]
    c['proof_independently_checked'] = True
    c['experiment_independently_reproduced'] = True
    c['claim'] = 'The system is stable under explicit hypotheses'
    c['formal_proof'] = 'proofs/theorem-1.tex'
    c['reproducible_experiment'] = 'python experiments/reproduce.py'
    c['closest_prior_work_comparison'] = 'Smith 2022 Proposition 1 vs our theorem'
    c['evidence'][0]['excerpt'] = 'Exact statement describing the hypothesis' 
    assert gate_claims(data)['status'] == 'READY_FOR_EXTERNAL_REVIEW'


def test_matrix_and_cli(tmp_path):
    source = tmp_path / 'in.json'
    source.write_text(json.dumps({"papers": [{"title": "Research", "doi": "10.1/x", "year": 2025, "sources": ["openalex"]}]}))
    output = tmp_path / 'out.csv'
    assert main(['matrix', str(source), '--out', str(output)]) == 0
    assert 'NOT_REVIEWED' in output.read_text()
    assert main(['discover', 'x', '--limit', '0']) == 2


def test_pdf_exfiltration_guard(tmp_path):
    pdf = tmp_path / 'test.pdf'
    pdf.write_bytes(b'%PDF-1.4 fake')
    with ResearchClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as c:
        with pytest.raises(ValueError, match='local'):
            c.grobid_references(pdf, 'https://example.org')
