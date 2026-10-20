from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta

from cot.config import HOLD_WEEKS
from cot.signals import Alert


def build_cot_json(actionable: list[Alert], all_alerts: list[Alert]) -> dict:
    now = datetime.now(UTC)
    hold_until = (date.today() + timedelta(weeks=HOLD_WEEKS)).isoformat()

    buy_signals = []
    for alert in actionable:
        cd = alert.commercial_details
        td = alert.trend_details
        buy_signals.append({
            "commodity": alert.commodity.name,
            "etf": alert.commodity.leveraged_etf,
            "hold_until": hold_until,
            "commercial": {
                "current_long": cd.get("current_value"),
                "prior_52w_max": cd.get("previous_max"),
                "report_date": cd.get("current_date"),
            },
            "trend": {
                "latest_close": td.get("latest_close"),
                "sma50": td.get("sma_50"),
                "sma200": td.get("sma_200"),
            },
        })

    full_status = [
        {
            "commodity": a.commodity.name,
            "commercial_signal": a.commercial_signal,
            "trend_signal": a.trend_signal,
            "combined": a.combined_signal,
        }
        for a in all_alerts
    ]

    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "report_date": date.today().isoformat(),
        "signal_count": len(actionable),
        "buy_signals": buy_signals,
        "full_status": full_status,
    }


def write_cot_json(
    actionable: list[Alert],
    all_alerts: list[Alert],
    path: str = "dashboard/data/cot.json",
) -> None:
    data = build_cot_json(actionable, all_alerts)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
