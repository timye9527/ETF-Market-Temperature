"""Liquidity selection: Top N per bucket, plus coverage and pair completion (framework-v2 §5)."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .universe import SENTIMENT_ROLES, Universe

TOP_N = 20
ADV_DAYS = 60
COVERAGE_MIN_ADV = 10e6  # a node keeps its best core only if it trades at least this much
LEVERAGE_MIN_ADV = 5e6   # leveraged/inverse members join their covered node above this


@dataclass
class Selection:
    selected: set[str]
    table: pd.DataFrame  # ticker, bucket, adv, rank, reason


def adv(bars: dict[str, pd.DataFrame], days: int = ADV_DAYS) -> dict[str, float]:
    out = {}
    for t, df in bars.items():
        dv = (df["close"] * df["volume"]).dropna().tail(days)
        out[t] = float(dv.median()) if len(dv) else 0.0
    return out


def select(u: Universe, bars: dict[str, pd.DataFrame], top_n: int = TOP_N) -> Selection:
    liq = adv({t: b for t, b in bars.items() if t in u.etfs})
    rows = [{"ticker": t, "bucket": u.bucket(t), "adv": liq.get(t, 0.0)} for t in u.etfs]
    df = pd.DataFrame(rows)
    df["available"] = df["ticker"].isin(liq.keys()) & (df["adv"] > 0)
    df["rank"] = df.groupby("bucket")["adv"].rank(ascending=False, method="first").astype(int)
    reason = {t: "TOP_N" for t in df.loc[df["available"] & (df["rank"] <= top_n), "ticker"]}

    # Coverage: every node keeps its most liquid price member.
    price_roles = ("CORE", "THEMATIC")
    best: dict[str, tuple[float, str]] = {}
    for t, e in u.etfs.items():
        if e["role"] not in price_roles or liq.get(t, 0) < COVERAGE_MIN_ADV:
            continue
        node = u.families[e["family"]]["node"]
        if liq[t] > best.get(node, (0, ""))[0]:
            best[node] = (liq[t], t)
    for _, t in best.values():
        reason.setdefault(t, "COVERAGE")

    # Leverage block (framework-v2 §1.6): every liquid leveraged/inverse member of a covered node joins,
    # so a node's bull/bear reading does not depend on the bucket-wide Top N.
    covered = {u.families[u.etfs[t]["family"]]["node"] for t in reason}
    for t, e in u.etfs.items():
        if e["role"] in SENTIMENT_ROLES and liq.get(t, 0) >= LEVERAGE_MIN_ADV \
                and u.families[e["family"]]["node"] in covered:
            reason.setdefault(t, "LEVERAGE_BLOCK")

    # A selected leveraged member brings its family's price member and its opposite side.
    for t in list(reason):
        e = u.etfs[t]
        if e["role"] not in SENTIMENT_ROLES:
            continue
        for m in u.members(e["family"]):
            if m["ticker"] in liq and liq[m["ticker"]] > 0 and m["ticker"] not in reason:
                if m["role"] in price_roles or (m["role"] in SENTIMENT_ROLES and m["direction"] != e["direction"]):
                    reason[m["ticker"]] = "PAIR"
    # Families whose price member is selected keep their liquid alternative cores (attention only).
    for t in list(reason):
        e = u.etfs[t]
        if e["role"] in price_roles:
            for m in u.members(e["family"]):
                if m["role"] == "ALTERNATIVE_CORE" and liq.get(m["ticker"], 0) >= COVERAGE_MIN_ADV:
                    reason.setdefault(m["ticker"], "ALT_CORE")

    df["reason"] = df["ticker"].map(reason)
    df["selected"] = df["reason"].notna()
    return Selection(selected=set(reason), table=df.sort_values(["bucket", "rank"]).reset_index(drop=True))


def restrict(u: Universe, selected: set[str]) -> Universe:
    """A Universe view holding only the selected ETFs (families/nodes unchanged)."""
    v = Universe(nodes=u.nodes, families=u.families,
                 etfs={t: e for t, e in u.etfs.items() if t in selected}, stocks=u.stocks)
    return v
