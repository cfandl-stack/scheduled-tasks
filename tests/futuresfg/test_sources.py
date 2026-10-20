from datetime import date

import numpy as np
import pandas as pd
import pytest

from futuresfg import derivatives, flows, http, markets
from futuresfg.http import date_to_ms

D1 = 1760832000000  # 2025-10-19 00:00 UTC
H = 3_600_000
DAY = 24 * H


def _iso(ms):
    return http.ms_to_date(ms)


class TestFunding:
    def test_okx_parse_and_daily_mean_per_8h(self):
        payload = {"code": "0", "msg": "", "data": [
            {"instId": "BTC-USDT-SWAP", "fundingRate": "0.0001", "realizedRate": "0.00012",
             "fundingTime": str(D1 + 16 * H), "method": "current_period"},
            {"instId": "BTC-USDT-SWAP", "fundingRate": "0.00005", "realizedRate": "0.00006",
             "fundingTime": str(D1 + 8 * H), "method": "current_period"},
            {"instId": "BTC-USDT-SWAP", "fundingRate": "0.00003", "realizedRate": "",
             "fundingTime": str(D1), "method": "current_period"},
        ]}
        points = derivatives.parse_okx_funding(payload)
        daily = derivatives.daily_funding(points)
        assert daily == {"2025-10-19": pytest.approx((0.00012 + 0.00006 + 0.00003) / 3 * 100)}

    def test_okx_error_code_raises(self):
        with pytest.raises(ValueError):
            derivatives.parse_okx_funding({"code": "51001", "msg": "Instrument ID does not exist", "data": []})

    def test_hyperliquid_hourly_scaled_to_8h(self):
        payload = [{"coin": "BTC", "fundingRate": "0.0000125", "premium": "-0.0001", "time": D1 + i * H + 76}
                   for i in range(24)]
        daily = derivatives.daily_funding(derivatives.parse_hyperliquid_funding(payload))
        assert daily["2025-10-19"] == pytest.approx(0.0000125 * 8 * 100)

    def test_hyperliquid_paginates(self, monkeypatch):
        start = date(2025, 10, 1)
        calls = []

        def fake_post(url, payload):
            calls.append(payload["startTime"])
            if len(calls) == 1:
                return [{"coin": "BTC", "fundingRate": "0.00001", "premium": "0", "time": payload["startTime"] + i * H}
                        for i in range(500)]
            return [{"coin": "BTC", "fundingRate": "0.00001", "premium": "0", "time": payload["startTime"] + i * H}
                    for i in range(10)]

        monkeypatch.setattr(http, "post_json", fake_post)
        out = derivatives.fetch_hyperliquid_funding(start)
        assert len(calls) == 2 and calls[1] == date_to_ms(start) + 499 * H + 1
        assert min(out) == "2025-10-01"

    def test_binance_parse(self):
        payload = [{"symbol": "BTCUSDT", "fundingTime": D1 + i * 8 * H, "fundingRate": "0.00010000",
                    "markPrice": "100000"} for i in range(3)]
        daily = derivatives.daily_funding(derivatives.parse_binance_funding(payload))
        assert daily["2025-10-19"] == pytest.approx(0.01)

    def test_okx_fetch_paginates_with_after(self, monkeypatch):
        start = date(2025, 10, 18)
        seen = []

        def fake_get(url, params=None, headers=None):
            seen.append(params.get("after"))
            base = D1 + DAY if not params.get("after") else int(params["after"]) - 3 * 8 * H
            rows = [{"fundingRate": "0.0001", "fundingTime": str(base + k * 8 * H)} for k in (2, 1, 0)]
            return {"code": "0", "data": rows}

        monkeypatch.setattr(http, "get_json", fake_get)
        out = derivatives.fetch_okx_funding(start)
        assert seen[:2] == [None, D1 + DAY]
        assert min(out) == "2025-10-18" and max(out) == "2025-10-20"


class TestOpenInterest:
    def test_daily_pct_change(self):
        out = derivatives.daily_pct_change({"2025-10-17": 100.0, "2025-10-18": 110.0, "2025-10-20": 99.0})
        assert out == {"2025-10-18": pytest.approx(10.0)}  # gap on 10-19 → no change for 10-20

    def test_okx_rubik(self):
        payload = {"code": "0", "msg": "", "data": [
            [str(D1), "2010000000.5", "900000000"],
            [str(D1 - DAY), "2000000000", "800000000"],
        ]}
        levels = derivatives.parse_okx_open_interest(payload)
        assert derivatives.daily_pct_change(levels) == {"2025-10-19": pytest.approx(0.500000025)}

    def test_bybit(self):
        payload = {"retCode": 0, "retMsg": "OK", "result": {
            "symbol": "BTCUSDT", "category": "linear",
            "list": [{"openInterest": "51000.5", "timestamp": str(D1)},
                     {"openInterest": "50000", "timestamp": str(D1 - DAY)}],
            "nextPageCursor": "abc"}, "time": 1}
        levels, cursor = derivatives.parse_bybit_open_interest(payload)
        assert cursor == "abc" and levels["2025-10-19"] == 51000.5

    def test_bybit_error(self):
        with pytest.raises(ValueError):
            derivatives.parse_bybit_open_interest({"retCode": 10001, "retMsg": "params error", "result": {}})

    def test_binance(self):
        payload = [{"symbol": "BTCUSDT", "sumOpenInterest": "80000", "sumOpenInterestValue": "8000000000",
                    "timestamp": D1 - DAY},
                   {"symbol": "BTCUSDT", "sumOpenInterest": "81000", "sumOpenInterestValue": "8080000000",
                    "timestamp": D1}]
        levels = derivatives.parse_binance_open_interest(payload)
        assert derivatives.daily_pct_change(levels)["2025-10-19"] == pytest.approx(1.0)


class TestLongShort:
    def test_okx(self):
        payload = {"code": "0", "msg": "", "data": [[str(D1), "1.78"], [str(D1 - DAY), "1.5"]]}
        assert derivatives.parse_okx_long_short(payload) == {"2025-10-19": 1.78, "2025-10-18": 1.5}

    def test_bybit(self):
        payload = {"retCode": 0, "retMsg": "OK", "result": {"list": [
            {"symbol": "BTCUSDT", "buyRatio": "0.64", "sellRatio": "0.36", "timestamp": str(D1)}]}}
        assert derivatives.parse_bybit_long_short(payload)["2025-10-19"] == pytest.approx(0.64 / 0.36)

    def test_binance(self):
        payload = [{"symbol": "BTCUSDT", "longShortRatio": "1.7800", "longAccount": "0.6403",
                    "shortAccount": "0.3597", "timestamp": D1}]
        assert derivatives.parse_binance_long_short(payload) == {"2025-10-19": 1.78}


class TestLiquidations:
    def test_coinglass(self):
        payload = {"code": "0", "msg": "success", "data": [
            {"time": D1, "aggregated_long_liquidation_usd": 195e6, "aggregated_short_liquidation_usd": 53e6}]}
        assert derivatives.parse_coinglass_liquidations(payload) == {"2025-10-19": {"long": 195e6, "short": 53e6}}

    def test_coinglass_without_key_raises(self, monkeypatch):
        monkeypatch.delenv("COINGLASS_API_KEY", raising=False)
        with pytest.raises(RuntimeError):
            derivatives.fetch_coinglass_liquidations(date(2025, 1, 1))

    def test_okx_orders_sides_and_notional(self):
        payload = {"code": "0", "msg": "", "data": [{
            "instFamily": "BTC-USDT", "instId": "BTC-USDT-SWAP", "instType": "SWAP", "uly": "BTC-USDT",
            "totalLoss": "0",
            "details": [
                {"bkLoss": "0", "bkPx": "100000", "ccy": "", "posSide": "long", "side": "sell", "sz": "50",
                 "ts": str(D1 + H)},
                {"bkLoss": "0", "bkPx": "110000", "ccy": "", "posSide": "short", "side": "buy", "sz": "10",
                 "ts": str(D1 + 2 * H)},
                {"bkLoss": "0", "bkPx": "100000", "ccy": "", "posSide": "net", "side": "sell", "sz": "1",
                 "ts": str(D1 + 3 * H)},
            ]}]}
        orders = derivatives.parse_okx_liquidations(payload)
        assert [o[1] for o in orders] == ["long", "short", "long"]
        assert orders[0][2] == pytest.approx(50 * 0.01 * 100000)
        days = derivatives.bucket_liquidations(orders, D1)
        assert days["2025-10-19"] == {"long": pytest.approx(51000.0), "short": pytest.approx(11000.0)}

    def test_okx_partial_oldest_day_dropped(self, monkeypatch):
        details = [{"bkPx": "100000", "posSide": "long", "side": "sell", "sz": "1", "ts": str(D1 + k * 6 * H)}
                   for k in range(7, -1, -1)]  # 2025-10-19 00:00 .. 2025-10-20 18:00, newest first

        def fake_get(url, params=None, headers=None):
            if params.get("after"):
                return {"code": "0", "data": []}
            return {"code": "0", "data": [{"details": details[:6]}]}  # oldest returned: 10-19 12:00

        monkeypatch.setattr(http, "get_json", fake_get)
        out = derivatives.fetch_okx_liquidations(date(2025, 10, 1))
        assert list(out) == ["2025-10-20"]


class TestEtf:
    FARSIDE = """
    <html><body><table class="etf">
      <thead>
        <tr><th></th><th>Blackrock</th><th>Fidelity</th><th></th></tr>
        <tr><th>Date</th><th>IBIT</th><th>FBTC</th><th>Total</th></tr>
        <tr><th>Fee</th><th>0.25%</th><th>0.25%</th><th></th></tr>
      </thead>
      <tbody>
        <tr><td>16 Oct 2025</td><td>100.0</td><td>(20.5)</td><td>1,079.5</td></tr>
        <tr><td>17 Oct 2025</td><td>(100.0)</td><td>(51.0)</td><td><span>(151.0)</span></td></tr>
        <tr><td>20 Oct 2025</td><td>-</td><td>-</td><td>-</td></tr>
        <tr><td>Total</td><td>60,000</td><td>12,000</td><td>72,000</td></tr>
        <tr><td>Average</td><td>1</td><td>1</td><td>1</td></tr>
      </tbody>
    </table></body></html>
    """

    def test_farside(self):
        assert flows.parse_farside(self.FARSIDE) == {
            "2025-10-16": pytest.approx(1079.5e6), "2025-10-17": pytest.approx(-151e6)}

    def test_farside_numbers(self):
        assert flows.parse_farside_number("(12.3)") == -12.3
        assert flows.parse_farside_number("0.0") == 0.0
        assert flows.parse_farside_number("-") is None

    def test_farside_blocked_page_has_no_data(self, monkeypatch):
        monkeypatch.setattr(http, "get_text", lambda *a, **k: "<html>Just a moment...</html>")
        with pytest.raises(ValueError):
            flows.fetch_farside_etf(date(2025, 1, 1))

    def test_coinglass(self):
        payload = {"code": "0", "msg": "success", "data": [
            {"timestamp": D1, "flow_usd": -151000000, "price_usd": 100000, "etf_flows": []}]}
        assert flows.parse_coinglass_etf(payload) == {"2025-10-19": -151e6}


class TestStablecoins:
    def test_defillama_7d_change(self, monkeypatch):
        payload = [{"date": str((D1 - (7 - i) * DAY) // 1000),
                    "totalCirculating": {"peggedUSD": 1.0},
                    "totalCirculatingUSD": {"peggedUSD": 300e9 + i * 1e9, "peggedEUR": 1e8}}
                   for i in range(8)]
        assert flows.parse_defillama_stablecoins(payload)["2025-10-19"] == 307e9
        monkeypatch.setattr(http, "get_json", lambda *a, **k: payload)
        out = flows.fetch_defillama_stablecoins(date(2025, 1, 1))
        assert out == {"2025-10-19": pytest.approx(7 / 300 * 100)}


class TestCoinbasePremium:
    def test_parsers_and_premium(self):
        cb = flows.parse_coinbase_candles([[D1 // 1000, 99000, 101000, 100000, 99889.0, 1234.5],
                                           [(D1 - DAY) // 1000, 1, 2, 1, 50000.0, 1]])
        bn = flows.parse_binance_klines([[D1, "100000", "101000", "99000", "100000.00", "1",
                                          D1 + DAY - 1, "1", 1, "1", "1", "0"]])
        okx = flows.parse_okx_candles({"code": "0", "data": [
            [str(D1), "100000", "101000", "99000", "100000", "1", "1", "1", "1"]]})
        assert bn == okx == {"2025-10-19": 100000.0}
        assert flows.premium(cb, bn) == {"2025-10-19": pytest.approx(-0.111)}

    def test_coinbase_error_payload(self):
        with pytest.raises(ValueError):
            flows.parse_coinbase_candles({"message": "granularity too small for the requested time range"})

    def test_coinbase_chunks_of_300_days(self, monkeypatch):
        calls = []

        def fake_get(url, params=None, headers=None):
            calls.append(params)
            return [[D1 // 1000, 1, 2, 1, 100.0, 1]]

        monkeypatch.setattr(http, "get_json", fake_get)
        flows.fetch_coinbase_closes(date.today().replace(year=date.today().year - 1))
        assert len(calls) == 2 and calls[0]["granularity"] == 86400


class TestMarkets:
    def test_fred_csv(self):
        text = "observation_date,DTWEXBGS\n2025-10-16,121.5\n2025-10-17,.\n2025-10-20,121.6\n"
        s = markets.parse_fred_csv(text)
        assert list(s.values) == [121.5, 121.6]

    def test_dollar_change_over_20_observations(self):
        idx = pd.bdate_range("2025-01-01", periods=25)
        levels = pd.Series(np.linspace(100, 124, 25), index=idx)
        out = markets.dollar_from_levels(levels, date(2025, 1, 1))
        first = min(out)
        assert first == idx[20].date().isoformat()
        assert out[first]["change"] == pytest.approx(20.0)
        assert out[first]["level"] == pytest.approx(120.0)

    def test_rsi_extremes(self):
        up = pd.Series(np.arange(1, 40, dtype=float), index=pd.date_range("2025-01-01", periods=39))
        assert markets.rsi(up).iloc[-1] == pytest.approx(100.0)
        down = up[::-1].copy()
        down.index = up.index
        assert markets.rsi(down).iloc[-1] == pytest.approx(0.0)

    def test_rsi_vol_from_close(self):
        rng = np.random.default_rng(1)
        close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 120))),
                          index=pd.date_range("2025-01-01", periods=120))
        out = markets.rsi_vol_from_close(close, date(2025, 1, 1))
        assert min(out) == "2025-01-31"  # 30 returns needed for the volatility
        v = out[max(out)]
        assert 0 <= v["rsi"] <= 100 and 10 < v["vol"] < 80
