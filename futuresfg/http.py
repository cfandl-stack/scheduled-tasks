import logging
from datetime import UTC, date, datetime
from typing import Any

import requests

from futuresfg.config import HTTP_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)


def _request(method: str, url: str, headers: dict | None = None, **kwargs) -> requests.Response:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}
    hdrs.update(headers or {})
    resp = requests.request(method, url, headers=hdrs, timeout=HTTP_TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp


def get_json(url: str, params: dict | None = None, headers: dict | None = None) -> Any:
    return _request("GET", url, headers=headers, params=params).json()


def post_json(url: str, payload: dict) -> Any:
    return _request("POST", url, json=payload).json()


def get_text(url: str, params: dict | None = None, headers: dict | None = None) -> str:
    return _request("GET", url, headers=headers, params=params).text


def ms_to_date(ms: int | float | str) -> str:
    return datetime.fromtimestamp(int(float(ms)) / 1000, tz=UTC).date().isoformat()


def date_to_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000)


def require(data: dict, what: str) -> dict:
    if not data:
        raise ValueError(f"No {what} data")
    return data
