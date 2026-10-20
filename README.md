# Finanztools

Alle Finanz-Tools in einem Repo. Jedes Tool läuft als GitHub Action, schreibt seine Ergebnisse als JSON nach `dashboard/data/`, und das Dashboard (`dashboard/index.html`, über GitHub Pages) zeigt alles an.

| Tool | Ordner | Zeitplan (UTC) | Ausgabe |
|---|---|---|---|
| **Fear & Greed Index** (Nachbau der CNN-Methodik) | `feargreed/` | Mo–Fr 22:15 | `dashboard/data/feargreed.json` |
| **COT-Signale** (CFTC Commitment of Traders) | `cot/` | Fr 21:00 | `dashboard/data/cot.json` + E-Mail |
| **Insider-Screener** (OpenInsider-Käufe) | `insider/` | Mo 07:00 | `dashboard/data/insider.json` |
| **Research Report** (Claude + Websuche) | `research/` | alle 48 h, 06:17 | `dashboard/data/research*.json` + GitHub Issue |
| **Positions-Rechner** | nur im Dashboard | – | – |

## Dashboard

`dashboard/index.html` ist eine statische Seite ohne Build-Schritt. Tabs: Übersicht, Fear & Greed, COT, Insider, Research, Rechner. Oben laufen Krypto-Kurse (BTC, ETH, PEPE) live über CoinGecko.

Lokal ansehen:

```bash
cd dashboard && python -m http.server 8000
# http://localhost:8000
```

Deployment: `.github/workflows/pages.yml` veröffentlicht `dashboard/` auf GitHub Pages, bei jedem Push auf `main` und nach jedem Daten-Workflow.

## Einrichtung

1. **GitHub Pages aktivieren:** Settings → Pages → Source: *GitHub Actions*.
2. **Secrets anlegen** (Settings → Secrets and variables → Actions):

   | Secret | Für | Pflicht |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | Research Report | ohne Key wird der Report übersprungen |
   | `SENDER_EMAIL` | COT-E-Mail (Gmail-Adresse) | ohne wird nur das Dashboard befüllt |
   | `SENDER_PASSWORD` | COT-E-Mail (Gmail **App-Passwort**) | 〃 |
   | `RECIPIENT_EMAIL` | COT-E-Mail (Empfänger) | 〃 |

3. **Erster Lauf:** Actions → jeweiligen Workflow → *Run workflow*. Erst danach hat das Dashboard Daten.

## Lokal ausführen

```bash
pip install -r requirements.txt
python -m feargreed.main
python -m cot.main
python -m insider.main
ANTHROPIC_API_KEY=... python -m research.main
python -m pytest tests -q
```

## Datenfluss

```
GitHub Actions (cron) ──► python -m <tool>.main ──► dashboard/data/<tool>.json ──► git commit
                                                                               └──► Pages-Deploy ──► Dashboard
```

Die Daten-Workflows teilen sich die Concurrency-Gruppe `data-commit` und machen vor dem Push `git pull --rebase`, damit sich ihre Commits nicht in die Quere kommen. Schlägt ein Tool fehl, bleibt die letzte JSON-Datei unverändert.
