"""Optional networked test. GitHub Actions starts GROBID on localhost first."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from research_harness.harness import ResearchClient, utc_now, write_json


def make_fixture(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(55, 780, "A study of scientific bibliographies")
    c.setFont("Helvetica", 10)
    lines = [
        "Abstract. This technical note concerns the reproducibility of scientific references.",
        "The purpose of this document is to test structured bibliography extraction.",
        "A valid reference appears below in conventional scholarly formatting.",
        "", "References", "",
        "[1] Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L.,",
        "Gomez, A. N., Kaiser, L., and Polosukhin, I. Attention Is All You Need.",
        "Advances in Neural Information Processing Systems 30 (2017).",
        "[2] Kingma, D. P. and Ba, J. Adam: A Method for Stochastic Optimization.",
        "International Conference on Learning Representations (2015).",
    ]
    text = c.beginText(55, 735)
    for line in lines:
        text.textLine(line)
    c.drawText(text)
    c.save()


def main() -> None:
    with TemporaryDirectory() as td:
        pdf = Path(td) / "fixture.pdf"
        make_fixture(pdf)
        with ResearchClient() as client:
            refs = client.grobid_references(pdf, "http://127.0.0.1:8070")
        report = {"checked_at_utc": utc_now(), "grobid_test": "actual_pdf_upload_and_tei_parse",
                  "pdf_bytes": pdf.stat().st_size, "extracted_reference_count": len(refs),
                  "references": [{"index": r["index"], "title": r["title"], "doi": r["doi"]} for r in refs]}
        write_json(Path("results/grobid-smoke.json"), report)
        print(json.dumps(report, indent=2))
        if not refs:
            raise SystemExit("GROBID produced no references for fixture; inspect results/grobid-smoke.json")


if __name__ == "__main__":
    main()
