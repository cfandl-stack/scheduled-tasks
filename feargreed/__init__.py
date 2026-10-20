"""Fear & Greed Index nach CNN-Methodik, berechnet aus freien Yahoo-Finance-Daten.

Approximations vs. CNN: new highs/lows and up/down volume use a ~100-stock large-cap
basket instead of the NYSE; the put/call ratio is replaced by the VIX/VIX3M term
structure; junk bond demand uses HYG-vs-IEF relative returns instead of yield spreads.
Each component is the percentile rank of today's value within its trailing 252 days.
"""
