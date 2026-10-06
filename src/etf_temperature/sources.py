"""Daily OHLCV sources.

Every source returns one DataFrame per ticker, indexed by date, with columns:
    open, high, low, close (unadjusted), adj_close, volume (shares)
`close` must be unadjusted: dollar volume = close * volume (DECISIONS D-002).
"""
from __future__ import annotations

import io
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

COLUMNS = ["open", "high", "low", "close", "adj_close", "volume"]


def parse_yahoo_chart(payload: dict) -> pd.DataFrame:
    """Parse Yahoo's v8 chart JSON (unofficial; research prototype only, see data-requirements.md)."""
    res = payload["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    idx = pd.to_datetime(
        [datetime.fromtimestamp(t, tz=timezone.utc).date() for t in res["timestamp"]]
    )
    df = pd.DataFrame(
        {"open": q["open"], "high": q["high"], "low": q["low"],
         "close": q["close"], "adj_close": adj, "volume": q["volume"]},
        index=idx,
    )
    df.index.name = "date"
    df = df[~df.index.duplicated(keep="last")].dropna(subset=["close"])
    return df[COLUMNS].astype(float)


def parse_stooq_csv(text: str) -> pd.DataFrame:
    """Stooq daily CSV. Stooq prices are split-adjusted only; used as a cross-check source."""
    df = pd.read_csv(io.StringIO(text), parse_dates=["Date"]).set_index("Date")
    df.index.name = "date"
    df = df.rename(columns=str.lower)
    df["adj_close"] = df["close"]
    return df[COLUMNS].astype(float)


def fetch_yahoo(tickers, years: int = 5, pause: float = 0.4) -> dict[str, pd.DataFrame]:
    import requests

    out, s = {}, requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (etf-market-temperature research prototype)"
    failed = []
    for t in tickers:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
        err = None
        for attempt in range(3):
            try:
                host = ("query1", "query2")[attempt % 2]
                r = s.get(url.replace("query1", host), params={"range": f"{years}y", "interval": "1d",
                          "events": "div,splits", "includeAdjustedClose": "true"}, timeout=30)
                r.raise_for_status()
                out[t] = parse_yahoo_chart(r.json())
                err = None
                break
            except Exception as exc:  # one bad ticker must not sink the run; engine reports it as missing
                err = exc
                time.sleep(2 * (attempt + 1))
        if err is not None:
            failed.append(f"{t}: {err}")
        time.sleep(pause)
    _drop_unfinished_session(out)
    if len(failed) > 0.2 * len(tickers):
        raise RuntimeError("too many tickers failed:\n" + "\n".join(failed))
    for f in failed:
        print("WARN", f)
    return out


def _drop_unfinished_session(bars: dict[str, pd.DataFrame], now=None) -> None:
    """Remove today's bar while the US session is still open: its partial volume
    would read as a collapse in dollar volume."""
    from zoneinfo import ZoneInfo

    now = now or datetime.now(ZoneInfo("America/New_York"))
    if now.hour * 60 + now.minute >= 16 * 60 + 15:
        return
    today = pd.Timestamp(now.date())
    for t, df in bars.items():
        if len(df) and df.index[-1] == today:
            bars[t] = df.iloc[:-1]


def fetch_stooq(tickers, pause: float = 0.4) -> dict[str, pd.DataFrame]:
    import requests

    out = {}
    for t in tickers:
        r = requests.get("https://stooq.com/q/d/l/", params={"s": f"{t.lower()}.us", "i": "d"}, timeout=30)
        r.raise_for_status()
        out[t] = parse_stooq_csv(r.text)
        time.sleep(pause)
    return out


# ───────────────────────── Demo data ─────────────────────────
# Synthetic but structurally faithful: a market factor, per-node factors, leveraged
# members derived from their core's daily return, and dollar volume that reacts to
# moves. It exists so the engine and site can be built and tested without market
# data access. Every output built from it is labelled DEMO.

def _node_chain(node: str) -> list[str]:
    parts = node.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]


# Rough annualised drift / vol per top-level bucket, chosen for plausibility only.
_PROFILE = {
    "EQUITY": (0.08, 0.17), "THEME": (0.06, 0.30), "BOND": (0.02, 0.07),
    "CASH_LIKE": (0.045, 0.003), "PRECIOUS_METALS": (0.09, 0.16),
    "COMMODITY": (0.03, 0.25), "CURRENCY": (0.0, 0.07), "CRYPTO": (0.25, 0.55),
    "VOLATILITY": (-0.45, 0.70),
}
_BASE_DV = {1: 2.0e9, 2: 2.5e8, 3: 3.0e7}


def make_demo(universe, end: str = "2026-10-05", years: int = 5, seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=end, periods=252 * years)
    n = len(dates)
    market = rng.normal(0.0003, 0.010, n)
    # Slow regime wave so temperatures move through hot and cold spells.
    regime = 0.0009 * np.sin(np.linspace(0, 9 * np.pi, n) + 0.6)

    shocks: dict[str, np.ndarray] = {}

    def node_shock(path: str) -> np.ndarray:
        if path not in shocks:
            phase = rng.uniform(0, 2 * np.pi)
            wave = 0.0012 * np.sin(np.linspace(0, rng.uniform(4, 14) * np.pi, n) + phase)
            shocks[path] = rng.normal(0, 0.006, n) + wave
        return shocks[path]

    core_returns: dict[str, np.ndarray] = {}
    for fid, fam in universe.families.items():
        top = fam["node"].split("/")[0]
        mu, vol = _PROFILE.get(top, (0.05, 0.2))
        beta = {"EQUITY": 1.0, "THEME": 1.3, "CRYPTO": 1.2, "BOND": -0.15,
                "PRECIOUS_METALS": -0.1, "VOLATILITY": -4.0, "CURRENCY": -0.2}.get(top, 0.3)
        r = beta * (market + regime) + mu / 252
        for p in _node_chain(fam["node"]):
            r = r + node_shock(p) * (vol / 0.17) * 0.5
        r = r + rng.normal(0, vol / np.sqrt(252) * 0.35, n)
        if top == "CASH_LIKE":
            r = np.full(n, mu / 252) + rng.normal(0, 0.00005, n)
        core_returns[fid] = np.clip(r, -0.25, 0.25)

    out: dict[str, pd.DataFrame] = {}
    for t, e in universe.etfs.items():
        fam = universe.families[e["family"]]
        base_fid = fam.get("price_proxy_family", fam["id"]) if fam.get("sentiment_only") else fam["id"]
        r_core = core_returns[base_fid]
        sign = 1 if e["direction"] == "LONG" else -1
        r = sign * e["leverage"] * r_core
        if e["role"] == "ALTERNATIVE_CORE":
            r = r + rng.normal(0, 0.0002, n)
        r = np.clip(r, -0.9, 0.9)
        close = 50 * np.exp(rng.uniform(-0.5, 1.5)) * np.cumprod(1 + r)

        # Attention: dollar volume rises with |move|, and leveraged sides respond to trend.
        absr = np.abs(r_core) / (np.std(r_core) + 1e-9)
        trend20 = pd.Series(r_core).rolling(20, min_periods=1).sum().to_numpy()
        z = trend20 / (np.std(trend20) + 1e-9)
        tier = e["tier"] if e["tier"] in _BASE_DV else 3
        base = _BASE_DV[tier] * (1.6 if e["role"] in ("LEVERAGED_BULL", "LEVERAGED_BEAR") else 1.0)
        growth = np.linspace(0.75, 1.25, n)
        mood = 1.0
        if e["direction"] == "LONG" and e["leverage"] > 1:
            mood = np.exp(0.35 * z)
        elif e["direction"] == "SHORT":
            mood = np.exp(-0.30 * z)
        dv = base * growth * mood * (1 + 0.45 * absr) * np.exp(rng.normal(0, 0.25, n))
        vol_shares = np.maximum(dv / close, 1.0).round()

        hi = close * (1 + np.abs(rng.normal(0, 0.006, n)))
        lo = close * (1 - np.abs(rng.normal(0, 0.006, n)))
        op = np.r_[close[0], close[:-1]]
        out[t] = pd.DataFrame(
            {"open": op, "high": np.maximum.reduce([hi, close, op]),
             "low": np.minimum.reduce([lo, close, op]), "close": close,
             "adj_close": close, "volume": vol_shares},
            index=pd.DatetimeIndex(dates, name="date"),
        )
    return out
