.PHONY: db init-db install test run backfill report site

db:
	docker compose up -d db

init-db:
	.venv/bin/boreas init-db

install:
	python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest -q

run:
	.venv/bin/boreas run

backfill:
	.venv/bin/boreas backfill --days 365

report:
	.venv/bin/boreas report

site:
	cd site && npm run dev
