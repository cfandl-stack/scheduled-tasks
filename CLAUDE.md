# Finanztools – Hinweise für Claude

Monorepo für Finanz-Tools. Jedes Tool ist ein eigenes Python-Paket mit `main.py` (Einstieg `python -m <paket>.main`, Exit-Code 0/1) und schreibt JSON nach `dashboard/data/`. Das Dashboard ist eine einzelne statische `dashboard/index.html` (Vanilla JS, Cyberpunk-Stil, kein Build).

## Struktur

- `cot/` – CFTC-COT-Signale (Commercials auf 52W-Hoch + Kurs > SMA50 > SMA200), optional E-Mail
- `insider/` – OpenInsider-Screener (Käufe, Wesentlichkeitsfilter, Cluster-Erkennung)
- `feargreed/` – Fear & Greed Index nach CNN-Methodik, eigene Berechnung über yfinance
- `research/` – Research Report über die Claude API mit Websuche
- `dashboard/` – statisches Dashboard + `data/*.json` (von den Workflows geschrieben)
- `tests/<paket>/` – pytest, ohne Netzwerk (Fixtures/Mocks)

## Regeln

- JSON-Schemas in `dashboard/data/` sind der Vertrag zwischen Tool und Dashboard: Felder nur ergänzen, nicht umbenennen, ohne `dashboard/index.html` anzupassen.
- Ein fehlgeschlagener Lauf darf die vorhandene JSON-Datei nicht überschreiben.
- Neue Daten-Workflows: Concurrency-Gruppe `data-commit`, Commit als github-actions[bot] mit `[skip ci]`, vor dem Push `git pull --rebase`, und den Workflow-Namen in `pages.yml` unter `workflow_run` ergänzen.
- Tests: `python -m pytest tests -q`
