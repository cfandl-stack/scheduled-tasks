import pytest

from futuresfg import formatting as fmt
from futuresfg.components import COMPONENTS

LABELS = {c.key: c.label for c in COMPONENTS}


@pytest.mark.parametrize("key, raw, expected", [
    ("funding", 0.0049, "+0,0049 %"),
    ("oi_change", 0.7, "+0,7 %"),
    ("long_short", 1.78, "1,78"),
    ("liquidations", {"long": 195.2e6, "short": 53.4e6}, "195 / 53 Mio. $"),
    ("liquidations", {"long": 2.34e6, "short": 0.5e6}, "2,3 / 0,5 Mio. $"),
    ("rsi_vol", {"rsi": 45.2, "vol": 40.0}, "RSI 45"),
    ("etf_flows", -151.0e6, "−151 Mio. $"),
    ("etf_flows", 1234.5e6, "+1.234 Mio. $"),
    ("stablecoins", -0.2, "−0,2 %"),
    ("coinbase_premium", -0.111, "−0,111 %"),
    ("vix", 16.94, "16,9"),
    ("dxy", {"level": 121.62, "change": 0.3}, "121,6"),
])
def test_component_labels(key, raw, expected):
    assert LABELS[key](raw) == expected


def test_number_edge_cases():
    assert fmt.number(-0.0001, 1, signed=True) == "0,0"
    assert fmt.number(1234567.891, 2) == "1.234.567,89"
    assert fmt.percent(0.0, 1) == "0,0 %"
