# Finanztools – Hinweise für Claude

Monorepo für Finanz-Tools. Jedes Tool ist ein eigenes Python-Paket mit `main.py` (Einstieg `python -m <paket>.main`, Exit-Code 0/1) und schreibt JSON nach `dashboard/data/`. Das Dashboard ist eine einzelne statische `dashboard/index.html` (Vanilla JS, Cyberpunk-Stil, kein Build).

## Struktur

- `cot/` – CFTC-COT-Signale (Commercials auf 52W-Hoch + Kurs > SMA50 > SMA200), optional E-Mail
- `insider/` – OpenInsider-Screener (Käufe, Wesentlichkeitsfilter, Cluster-Erkennung)
- `futuresfg/` – Bitcoin Futures Fear & Greed: 10 Bausteine, je Perzentil gegen eigene 365 Tage, Anzeige = 7-Tage-Mittel; Rohdaten werden in `dashboard/data/futuresfg_raw.json` fortgeschrieben, weil viele Gratis-APIs kaum Historie liefern. Jeder Baustein hat eine Quellen-Kette (Binance/Bybit sperren US-IPs der GitHub-Runner)
- `feargreed/` – Aktienmarkt Fear & Greed nach CNN-Methodik, eigene Berechnung über yfinance
- `research/` – Research Report über OpenRouter (Modell im Preset `finanztools-research`, derzeit Claude Haiku 5.5; Exa-Websuche)
- `dashboard/` – statisches Dashboard + `data/*.json` (von den Workflows geschrieben)
- `tests/<paket>/` – pytest, ohne Netzwerk (Fixtures/Mocks)

## Regeln

- JSON-Schemas in `dashboard/data/` sind der Vertrag zwischen Tool und Dashboard: Felder nur ergänzen, nicht umbenennen, ohne `dashboard/index.html` anzupassen.
- Ein fehlgeschlagener Lauf darf die vorhandene JSON-Datei nicht überschreiben.
- Neue Daten-Workflows: Concurrency-Gruppe `data-commit`, Commit als github-actions[bot] mit `[skip ci]`, vor dem Push `git pull --rebase`, und den Workflow-Namen in `pages.yml` unter `workflow_run` ergänzen.
- Tests: `python -m pytest tests -q`
