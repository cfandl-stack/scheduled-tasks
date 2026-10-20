from urllib.parse import urlencode

BASE_URL = "http://openinsider.com/screener"

WINDOW_DAYS = 14
MAX_ROWS = 1000

MIN_VALUE_USD = 100_000
MIN_DELTA_OWN_PCT = 10.0
CLUSTER_MIN_INSIDERS = 2

OFFICER_ROLES = ("CEO", "CFO", "COO", "Pres", "Dir", "10%")

OUTPUT_PATH = "dashboard/data/insider.json"

REQUEST_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


def screener_params(window_days: int = WINDOW_DAYS, max_rows: int = MAX_ROWS) -> dict[str, str]:
    # Full parameter set as emitted by the openinsider screener form.
    return {
        "s": "", "o": "", "pl": "", "ph": "", "ll": "", "lh": "",
        "fd": str(window_days), "fdr": "", "td": "0", "tdr": "",
        "fdlyl": "", "fdlyh": "", "daysago": "",
        "xp": "1",
        "vl": "", "vh": "", "ocl": "", "och": "",
        "sic1": "-1", "sicl": "100", "sich": "9999",
        "grp": "0",
        "nfl": "", "nfh": "", "nil": "", "nih": "", "nol": "", "noh": "",
        "v2l": "", "v2h": "", "oc2l": "", "oc2h": "",
        "sortcol": "0", "cnt": str(max_rows), "page": "1",
    }


def screener_url(window_days: int = WINDOW_DAYS, max_rows: int = MAX_ROWS) -> str:
    return f"{BASE_URL}?{urlencode(screener_params(window_days, max_rows))}"
