from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from feargreed import indicators
from feargreed.config import JUNK, SP500, STOCKS, TREASURIES, VIX, VIX3M


@dataclass
class MarketData:
    close: pd.DataFrame
    basket_close: pd.DataFrame
    basket_volume: pd.DataFrame


@dataclass(frozen=True)
class Component:
    key: str
    name: str
    name_de: str
    description_de: str
    invert: bool
    compute: Callable[[MarketData], pd.Series]
    label: Callable[[float], str]


def _signed(v: float, unit: str = "%") -> str:
    return f"{v:+.1f}{unit}"


COMPONENTS: list[Component] = [
    Component(
        key="momentum",
        name="Market Momentum",
        name_de="Marktmomentum",
        description_de="S&P 500 im Vergleich zu seinem gleitenden 125-Tage-Durchschnitt. "
        "Deutlich darüber = Gier.",
        invert=False,
        compute=lambda md: indicators.momentum(md.close, SP500),
        label=lambda v: f"S&P 500 vs. 125T-Schnitt: {_signed(v)}",
    ),
    Component(
        key="strength",
        name="Stock Price Strength",
        name_de="Kursstärke",
        description_de="Anteil der ~100 größten US-Aktien auf 52-Wochen-Hoch minus Anteil auf "
        "52-Wochen-Tief (Näherung für NYSE-Hochs/-Tiefs).",
        invert=False,
        compute=lambda md: indicators.net_new_highs(md.basket_close),
        label=lambda v: f"Netto 52W-Hochs: {_signed(v)} des Korbs",
    ),
    Component(
        key="breadth",
        name="Stock Price Breadth",
        name_de="Marktbreite",
        description_de="Volumen steigender minus fallender Aktien des Korbs über 20 Tage "
        "(Näherung für den McClellan Volume Summation Index).",
        invert=False,
        compute=lambda md: indicators.net_up_volume(md.basket_close, md.basket_volume),
        label=lambda v: f"Netto-Aufwärtsvolumen (20T): {_signed(v)}",
    ),
    Component(
        key="put_call",
        name="Put and Call Options",
        name_de="Put/Call-Optionen",
        description_de="5-Tage-Schnitt von VIX/VIX3M als Ersatz für die Put/Call-Ratio. "
        "Hoher Wert = teure kurzfristige Absicherung = Angst.",
        invert=True,
        compute=lambda md: indicators.vix_term_structure(md.close, VIX, VIX3M),
        label=lambda v: f"VIX/VIX3M (5T-Ø): {v:.2f}",
    ),
    Component(
        key="volatility",
        name="Market Volatility",
        name_de="Marktvolatilität",
        description_de="VIX im Vergleich zu seinem gleitenden 50-Tage-Durchschnitt. "
        "Steigende Volatilität = Angst.",
        invert=True,
        compute=lambda md: indicators.volatility(md.close, VIX),
        label=lambda v: f"VIX vs. 50T-Schnitt: {_signed(v)}",
    ),
    Component(
        key="safe_haven",
        name="Safe Haven Demand",
        name_de="Nachfrage nach sicheren Häfen",
        description_de="20-Tage-Rendite von Aktien (SPY) minus Staatsanleihen (IEF). "
        "Anleihen vorne = Flucht in Sicherheit = Angst.",
        invert=False,
        compute=lambda md: indicators.relative_return(md.close, STOCKS, TREASURIES),
        label=lambda v: f"SPY − IEF (20T): {_signed(v, ' Pp')}",
    ),
    Component(
        key="junk_bond",
        name="Junk Bond Demand",
        name_de="Nachfrage nach Hochzinsanleihen",
        description_de="20-Tage-Rendite von Hochzinsanleihen (HYG) minus Staatsanleihen (IEF) "
        "als Näherung für den Renditeaufschlag. Junk Bonds vorne = Gier.",
        invert=False,
        compute=lambda md: indicators.relative_return(md.close, JUNK, TREASURIES),
        label=lambda v: f"HYG − IEF (20T): {_signed(v, ' Pp')}",
    ),
]
