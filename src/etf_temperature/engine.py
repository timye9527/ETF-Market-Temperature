"""Temperature engine: bars → family factors → node temperatures (docs/temperature-model.md).

All normalisation uses trailing windows only (no look-ahead).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

WINDOW = 252          # percentile look-back
MIN_PERIODS = 126     # no score with less history than this
FACTORS = ["trend", "volume", "bullbear", "rs", "breadth"]
BANDS = [  # MASTER_PROMPT §16 thresholds; to be calibrated (D-008 / Q6)
    (15, "EXTREME_COLD", "极冷"), (35, "COLD", "冷"), (45, "COOL", "偏冷"),
    (55, "NEUTRAL", "中性"), (65, "WARM", "偏暖"), (85, "HOT", "热"), (101, "EXTREME_HOT", "极热"),
]
# Leveraged/inverse members pass the automatic consistency check when their daily
# returns behave like (direction × leverage) × the family's core return.
LEV_BETA_TOL = 0.15
LEV_MIN_R2 = 0.85


def band(t: float | None):
    if t is None:
        return None
    for hi, code, _ in BANDS:
        if t < hi:
            return code
    return BANDS[-1][1]


def prank(s: pd.Series, window: int = WINDOW) -> pd.Series:
    """Trailing percentile (0–100) of today's value within its own last `window` days."""
    return s.rolling(window, min_periods=MIN_PERIODS).rank(pct=True) * 100


def _mean(frames: list[pd.Series]) -> pd.Series:
    return pd.concat(frames, axis=1).mean(axis=1, skipna=False)


def trend_scores(p: pd.Series) -> dict[str, pd.Series]:
    a1 = _mean([prank(p / p.rolling(w).mean() - 1) for w in (20, 50, 200)])
    a2 = _mean([prank(p.pct_change(k)) for k in (5, 20, 60)])
    lo, hi = p.rolling(252, min_periods=MIN_PERIODS).min(), p.rolling(252, min_periods=MIN_PERIODS).max()
    a3 = ((p - lo) / (hi - lo).replace(0, np.nan) * 100)
    return {"ma_position": a1, "momentum": a2, "range_52w": a3, "trend": _mean([a1, a2, a3])}


def volume_scores(dv: pd.Series, p: pd.Series) -> dict[str, pd.Series]:
    dv5 = dv.rolling(5).mean()
    activity = prank(dv5)
    # Continuous direction in [-1, 1]: the 5-day move scaled by its own typical size,
    # so a flat week reads near 0 instead of flipping between ±1 (D-008).
    r5 = p.pct_change(5)
    direction = (r5 / r5.rolling(WINDOW, min_periods=MIN_PERIODS).std()).clip(-1, 1)
    ldv = np.log(dv.replace(0, np.nan))
    z = (np.log(dv5) - ldv.rolling(60).mean()) / ldv.rolling(60).std()
    return {"activity": activity, "volume_z": z, "volume": 50 + 0.5 * activity * direction}


def bullbear_scores(bull: pd.Series | None, bear: pd.Series | None, core_dv: pd.Series) -> dict[str, pd.Series]:
    core5 = core_dv.rolling(5).mean()
    out: dict[str, pd.Series] = {}
    parts = []
    if bull is not None:
        out["speculative_appetite"] = prank(bull.rolling(5).mean() / core5)
        parts.append(out["speculative_appetite"])
    if bear is not None:
        out["hedging_demand"] = prank(bear.rolling(5).mean() / core5)
        parts.append(100 - out["hedging_demand"])
    if bull is not None and bear is not None:
        b5, s5 = bull.rolling(5).mean(), bear.rolling(5).mean()
        out["bull_share_raw"] = b5 / (b5 + s5)
        out["bull_share"] = prank(out["bull_share_raw"])
        parts.append(out["bull_share"])
    if parts:
        out["bullbear"] = _mean(parts)
    return out


def rs_scores(p: pd.Series, bench: pd.Series) -> dict[str, pd.Series]:
    rs = p / bench
    d1 = _mean([prank(rs.pct_change(20)), prank(rs.pct_change(60))])
    d2 = prank(rs / rs.rolling(50).mean() - 1)
    return {"rs_momentum": d1, "rs_trend": d2, "rs": _mean([d1, d2])}


def breadth_scores(prices: pd.DataFrame) -> dict[str, pd.Series]:
    e1 = (prices > prices.rolling(20).mean()).mean(axis=1) * 100
    e2 = (prices > prices.rolling(50).mean()).mean(axis=1) * 100
    e3 = (prices.pct_change(20) > 0).mean(axis=1) * 100
    hi = (prices >= prices.rolling(20).max()).mean(axis=1)
    lo = (prices <= prices.rolling(20).min()).mean(axis=1)
    e4 = (hi - lo + 1) / 2 * 100
    valid = prices.notna().all(axis=1) & (prices.notna().cumsum() >= 50).all(axis=1)
    out = {"above_ma20": e1, "above_ma50": e2, "positive_20d": e3, "new_highs_net": e4}
    out = {k: v.where(valid) for k, v in out.items()}
    out["breadth"] = _mean(list(out.values()))
    return out


def lev_check(r_member: pd.Series, r_core: pd.Series, expected: float) -> dict:
    df = pd.concat([r_member, r_core], axis=1).dropna().tail(WINDOW)
    if len(df) < 60:
        return {"beta": None, "r2": None, "pass": False, "n": len(df)}
    x, y = df.iloc[:, 1].to_numpy(), df.iloc[:, 0].to_numpy()
    beta = float(np.cov(x, y)[0, 1] / np.var(x, ddof=1))
    r2 = float(np.corrcoef(x, y)[0, 1] ** 2)
    ok = abs(beta - expected) <= LEV_BETA_TOL * abs(expected) and r2 >= LEV_MIN_R2
    return {"beta": round(beta, 2), "r2": round(r2, 3), "pass": bool(ok), "n": len(df), "expected": expected}


class Engine:
    def __init__(self, universe, bars: dict[str, pd.DataFrame]):
        self.u = universe
        tickers = [t for t in universe.etfs if t in bars]
        self.missing = sorted(set(universe.etfs) - set(tickers))
        panel = lambda col: pd.DataFrame({t: bars[t][col] for t in tickers}).sort_index()
        self.adj, self.close, self.vol = panel("adj_close"), panel("close"), panel("volume")
        self.dv = (self.close * self.vol)
        self.dates = self.adj.index
        self.fam: dict[str, dict] = {}
        self.node: dict[str, dict] = {}
        self.checks: dict[str, dict] = {}

    # ── families ──
    def _core(self, fid: str) -> str | None:
        for e in self.u.members(fid):
            if e["role"] in ("CORE", "THEMATIC") and e["ticker"] in self.adj:
                return e["ticker"]
        return None

    def _sentiment_usable(self, e: dict) -> bool:
        """D-013: manually verified, or passes the automatic leverage consistency check."""
        return bool(e.get("verified")) or self.checks.get(e["ticker"], {}).get("pass", False)

    def run_families(self):
        rets = self.adj.pct_change()
        for fid, f in self.u.families.items():
            price_fid = f.get("price_proxy_family", fid) if f.get("sentiment_only") else fid
            core = self._core(price_fid)
            if core is None:
                continue
            members = [e for e in self.u.members(fid) if e["ticker"] in self.adj]
            p = self.adj[core]
            m: dict = {"core": core, "price": p}
            if not f.get("sentiment_only"):
                alt = [e["ticker"] for e in members if e["role"] in ("CORE", "ALTERNATIVE_CORE", "THEMATIC")]
                dv = self.dv[alt].sum(axis=1, min_count=1)
                m.update(trend_scores(p))
                m.update(volume_scores(dv, p))
                m["weight"] = math.sqrt(float(dv.tail(60).mean() or 0))
                m["tier3_only"] = all(e["tier"] == 3 for e in members if e["ticker"] == core)
            bull = bear = None
            for e in members:
                if e["role"] not in ("LEVERAGED_BULL", "LEVERAGED_BEAR", "INVERSE"):
                    continue
                sign = 1 if e["direction"] == "LONG" else -1
                self.checks[e["ticker"]] = lev_check(rets[e["ticker"]], rets[core], sign * e["leverage"])
                if not self._sentiment_usable(e):
                    continue
                exposure = self.dv[e["ticker"]] * e["leverage"]
                if sign > 0:
                    bull = exposure if bull is None else bull.add(exposure, fill_value=0)
                else:
                    bear = exposure if bear is None else bear.add(exposure, fill_value=0)
            if bull is not None or bear is not None:
                core_dv = self.dv[core]
                m["bb"] = bullbear_scores(bull, bear, core_dv)
            self.fam[fid] = m

    # ── nodes ──
    def _node_families(self, nid: str) -> list[str]:
        n = self.u.nodes[nid]
        direct = [fid for fid, f in self.u.families.items() if f["node"] == nid and fid in self.fam]
        if direct:
            return direct
        if n.get("anchor_family") in self.fam:
            return [n["anchor_family"]]
        return []

    def _basket(self, nid: str) -> list[str]:
        b = self.u.nodes[nid].get("breadth_basket")
        if not b:
            return []
        if isinstance(b, str):
            b = [c for c in self.u.nodes if c.rsplit("/", 1)[0] == b and self.u.nodes[c].get("scored")]
        return [c for c in b if c in self.node and self.node[c].get("price") is not None]

    def run_nodes(self):
        # Pass 1: price-based factors per node from its own families.
        for nid, n in self.u.nodes.items():
            if not n.get("scored") or n.get("status") == "NO_COVERAGE":
                continue
            fids = self._node_families(nid)
            price_fids = [f for f in fids if "trend" in self.fam[f]]
            if not price_fids and not any("bb" in self.fam[f] for f in fids):
                continue
            rec: dict = {"families": fids, "series": {}, "sub": {}}
            if price_fids:
                w = np.array([self.fam[f]["weight"] for f in price_fids]) + 1e-9
                w = w / w.sum()
                lead = price_fids[int(np.argmax(w))]
                rec["price"] = self.fam[lead]["price"]
                rec["lead_core"] = self.fam[lead]["core"]
                rec["tier3_only"] = all(self.fam[f]["tier3_only"] for f in price_fids)
                for key in ("trend", "ma_position", "momentum", "range_52w", "volume", "activity", "volume_z"):
                    s = sum(self.fam[f][key] * wi for f, wi in zip(price_fids, w))
                    (rec["series"] if key in ("trend", "volume", "activity") else rec["sub"])[key] = s
            # Direct families include any sentiment-only family on this node.
            bbs = [self.fam[f]["bb"] for f in fids if "bb" in self.fam[f]]
            if bbs:
                rec["series"]["bullbear"] = _mean([b["bullbear"] for b in bbs])
                for k in ("bull_share", "bull_share_raw", "speculative_appetite", "hedging_demand"):
                    vals = [b[k] for b in bbs if k in b]
                    if vals:
                        rec["sub"][k] = _mean(vals)
            self.node[nid] = rec
        # Pass 2: relative strength and breadth need other nodes' prices.
        for nid, rec in self.node.items():
            n = self.u.nodes[nid]
            bench = n.get("rs_benchmark")
            if rec.get("price") is not None and bench in self.node and self.node[bench].get("price") is not None:
                r = rs_scores(rec["price"], self.node[bench]["price"])
                rec["series"]["rs"] = r.pop("rs")
                rec["sub"].update(r)
            basket = self._basket(nid)
            if len(basket) >= 5:
                b = breadth_scores(pd.DataFrame({c: self.node[c]["price"] for c in basket}))
                rec["series"]["breadth"] = b.pop("breadth")
                rec["sub"].update(b)
                rec["basket"] = basket
        # Pass 3: temperature.
        for rec in self.node.values():
            fs = [rec["series"][f] for f in FACTORS if f in rec["series"]]
            rec["temperature"] = pd.concat(fs, axis=1).mean(axis=1, skipna=True)
            rec["coverage"] = pd.concat(fs, axis=1).notna().sum(axis=1)

    def run(self):
        self.run_families()
        self.run_nodes()
        return self


# ───────────────────────── SIGNAL layer: risk appetite ─────────────────────────
# Interpretation, kept separate from temperature (D-001, D-007).
RISK_PAIRS = [
    ("HYG", "IEF", "高收益债 vs 中期国债", "信用风险偏好"),
    ("SPHB", "USMV", "高 Beta vs 低波动", "股票风格偏好"),
    ("IWM", "SPY", "小盘 vs 大盘", "小盘风险偏好"),
    ("XLY", "XLP", "可选消费 vs 必选消费", "消费周期偏好"),
    ("SPY", "TLT", "股票 vs 长债", "股债偏好"),
    ("SOXX", "SPY", "半导体 vs 大盘", "高 Beta 科技偏好"),
]


def risk_appetite(engine: Engine) -> dict:
    comps, series = [], []
    for a, b, label, meaning in RISK_PAIRS:
        if a not in engine.adj or b not in engine.adj:
            continue
        ratio = engine.adj[a] / engine.adj[b]
        s = _mean([prank(ratio.pct_change(20)), prank(ratio / ratio.rolling(50).mean() - 1)])
        series.append(s)
        comps.append({"pair": f"{a}/{b}", "label": label, "meaning": meaning, "series": s})
    if "VIXY" in engine.dv and "UVXY" in engine.dv:
        fear = prank((engine.dv["VIXY"] + engine.dv["UVXY"] * 1.5).rolling(5).mean() / engine.dv["SPY"].rolling(5).mean())
        s = 100 - fear
        series.append(s)
        comps.append({"pair": "VIX ETP 成交", "label": "波动率对冲成交（反向）", "meaning": "恐慌对冲需求越低越偏 Risk-on", "series": s})
    total = pd.concat(series, axis=1).mean(axis=1)
    return {"score": total, "components": comps}
