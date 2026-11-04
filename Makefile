.PHONY: install test doctor smoke grobid-up grobid-down paperqa-install
install:
	python -m pip install -e '.[dev]'
test:
	python -m pytest -q
doctor:
	python -m research_harness doctor
smoke:
	python -m research_harness smoke
grobid-up:
	docker compose up -d grobid
grobid-down:
	docker compose down
paperqa-install:
	python -m pip install -e '.[paperqa]'
