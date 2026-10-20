"""The ten components: source chains, how a stored raw value becomes metrics, and labels.

Stored raw values are floats, except liquidations ({"long", "short"} in USD),
rsi_vol ({"rsi", "vol"}) and dxy ({"level", "change"}).
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from futuresfg import derivatives, flows, markets
from futuresfg import formatting as fmt
from futuresfg.config import DEFAULT_MAX_STALE_DAYS


@dataclass(frozen=True)
class Source:
    name: str
    fetch: Callable[[date], dict[str, Any]]


@dataclass(frozen=True)
class Metric:
    """One scored series: extracted from the raw value, percentile-ranked, optionally inverted."""
    extract: Callable[[Any], float | None]
    invert: bool = False


@dataclass(frozen=True)
class Component:
    key: str
    group: str
    name_de: str
    description_de: str
    sources: tuple[Source, ...]
    label: Callable[[Any], str]
    value: Callable[[Any], float | None]
    metrics: tuple[Metric, ...] = field(default_factory=lambda: (Metric(_float),))
    max_stale_days: int = DEFAULT_MAX_STALE_DAYS


def _float(raw: Any) -> float | None:
    return float(raw) if isinstance(raw, (int, float)) else None


def _field(name: str) -> Callable[[Any], float | None]:
    def get(raw: Any) -> float | None:
        if isinstance(raw, dict) and isinstance(raw.get(name), (int, float)):
            return float(raw[name])
        return None
    return get


def short_share(raw: Any) -> float | None:
    """Share of short liquidations: more shorts squeezed = greed."""
    if not isinstance(raw, dict):
        return None
    long_, short = raw.get("long") or 0.0, raw.get("short") or 0.0
    total = long_ + short
    return short / total if total > 0 else None


GROUPS: list[tuple[str, str]] = [("futures", "Futures-Markt"), ("flows", "Flows und Makro")]

COMPONENTS: list[Component] = [
    Component(
        key="funding",
        group="futures",
        name_de="Funding",
        description_de="Wer zahlt, um long zu sein: Tagesmittel der Perpetual-Funding-Rate "
        "(je 8 Stunden). Hohes Funding = gehebelte Longs = Gier.",
        sources=(
            Source("OKX", derivatives.fetch_okx_funding),
            Source("Hyperliquid", derivatives.fetch_hyperliquid_funding),
            Source("Binance", derivatives.fetch_binance_funding),
        ),
        label=lambda v: fmt.percent(v, 4),
        value=_float,
    ),
    Component(
        key="oi_change",
        group="futures",
        name_de="Open-Interest-Änderung",
        description_de="24-Stunden-Änderung des offenen BTC-Futures-Interesses: "
        "frischer Hebel fließt rein (Gier) oder wird abgebaut (Angst).",
        sources=(
            Source("OKX", derivatives.fetch_okx_oi_change),
            Source("Bybit", derivatives.fetch_bybit_oi_change),
            Source("Binance", derivatives.fetch_binance_oi_change),
        ),
        label=lambda v: fmt.percent(v, 1),
        value=_float,
    ),
    Component(
        key="long_short",
        group="futures",
        name_de="Long/Short",
        description_de="Verhältnis der Konten mit Long- zu Short-Positionen. "
        "Mehr Longs = Gier.",
        sources=(
            Source("OKX", derivatives.fetch_okx_long_short),
            Source("Bybit", derivatives.fetch_bybit_long_short),
            Source("Binance", derivatives.fetch_binance_long_short),
        ),
        label=lambda v: fmt.number(v, 2),
        value=_float,
    ),
    Component(
        key="liquidations",
        group="futures",
        name_de="Liquidationen",
        description_de="Zwangsverkäufe eines UTC-Tages, Longs / Shorts in Mio. $. "
        "Werden vor allem Longs liquidiert = Angst, vor allem Shorts = Gier.",
        sources=(
            Source("CoinGlass", derivatives.fetch_coinglass_liquidations),
            Source("OKX", derivatives.fetch_okx_liquidations),
        ),
        label=lambda v: fmt.long_short_millions(v["long"], v["short"]),
        value=short_share,
        metrics=(Metric(short_share),),
    ),
    Component(
        key="rsi_vol",
        group="futures",
        name_de="RSI und Volatilität",
        description_de="Wie überdehnt der Kurs ist: Mittel aus RSI(14) und invertierter "
        "30-Tage-Volatilität. Hoher RSI bei ruhigem Markt = Gier.",
        sources=(Source("Yahoo Finance", markets.fetch_yf_rsi_vol),),
        label=lambda v: f"RSI {fmt.number(v['rsi'], 0)}",
        value=_field("rsi"),
        metrics=(Metric(_field("rsi")), Metric(_field("vol"), invert=True)),
    ),
    Component(
        key="etf_flows",
        group="flows",
        name_de="ETF-Flows",
        description_de="Netto-Zu- und -Abflüsse der US-Spot-Bitcoin-ETFs am Tag.",
        sources=(
            Source("CoinGlass", flows.fetch_coinglass_etf),
            Source("Farside", flows.fetch_farside_etf),
        ),
        label=lambda v: fmt.usd_millions(v, signed=True),
        value=_float,
        max_stale_days=4,
    ),
    Component(
        key="stablecoins",
        group="flows",
        name_de="Stablecoin-Zufluss",
        description_de="7-Tage-Änderung der gesamten Stablecoin-Marktkapitalisierung: "
        "trockenes Pulver, das in den Markt kommt.",
        sources=(Source("DefiLlama", flows.fetch_defillama_stablecoins),),
        label=lambda v: fmt.percent(v, 1),
        value=_float,
    ),
    Component(
        key="coinbase_premium",
        group="flows",
        name_de="Coinbase-Premium",
        description_de="Aufschlag von BTC-USD auf Coinbase gegenüber BTC-USDT im Ausland: "
        "US-Käufer zahlen mehr = Gier.",
        sources=(
            Source("Coinbase vs. Binance", flows.fetch_premium_vs_binance),
            Source("Coinbase vs. OKX", flows.fetch_premium_vs_okx),
        ),
        label=lambda v: fmt.percent(v, 3),
        value=_float,
    ),
    Component(
        key="vix",
        group="flows",
        name_de="VIX",
        description_de="Die Angst der Wall Street. Hoher VIX = Angst (invertiert).",
        sources=(Source("Yahoo Finance", markets.fetch_yf_vix),),
        label=lambda v: fmt.number(v, 1),
        value=_float,
        metrics=(Metric(_float, invert=True),),
        max_stale_days=4,
    ),
    Component(
        key="dxy",
        group="flows",
        name_de="DXY-Trend",
        description_de="20-Tage-Trend des Dollar-Index: ein starker Dollar entzieht Liquidität "
        "(invertiert). Angezeigt ist der Indexstand.",
        sources=(
            Source("FRED (DTWEXBGS)", markets.fetch_fred_dollar),
            Source("Yahoo Finance (DX-Y.NYB)", markets.fetch_yf_dollar),
        ),
        label=lambda v: fmt.number(v["level"], 1),
        value=_field("level"),
        metrics=(Metric(_field("change"), invert=True),),
        # FRED publishes the broad dollar index weekly with a lag of several days.
        max_stale_days=10,
    ),
]
