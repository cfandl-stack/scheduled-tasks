"""Bitcoin Futures Fear & Greed: zehn Bausteine aus Futures-Markt, Flows und Makro.

Every component is a daily raw series scored as the percentile rank of the day's value
within that component's own trailing 365 calendar days (no fixed thresholds). The daily
composite is the equal-weight mean of available component scores; the headline index is
the 7-day mean of the daily composite. Many free endpoints expose little history, so raw
daily values are persisted in dashboard/data/futuresfg_raw.json and grow run by run.
"""
