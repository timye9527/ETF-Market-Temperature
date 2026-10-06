"""Temperature engine V2 (docs/framework-v2.md).

Temperature measures how far a node sits from ITS OWN TREND, not how high its price is:
a steady uptrend reads "strong trend, neutral temperature"; only acceleration beyond the
trend (or a collapse through it) reads hot (or cold). Trend state is reported separately.

Every sub-indicator is turned into a percentile of the node's own last 5 years (min 1 year).
All windows are trailing; nothing looks ahead.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .universe import SENTIMENT_ROLES, Universe

YEAR = 252
WIN5 = 5 * YEAR
MIN_HIST = YEAR
SMOOTH = 3
WEIGHTS = {"stretch": 0.30, "accel": 0.20, "crowding": 0.20, "breadth": 0.15, "rs": 0.15}
FACTORS = list(WEIGHTS)
BANDS = [  # framework-v2 §1.3 — by construction each band has a fixed historical frequency
    (5, "EXTREME_COLD", "极冷"), (20, "COLD", "冷"), (40, "COOL", "偏冷"), (60, "NEUTRAL", "中性"),
    (80, "WARM", "偏暖"), (95, "HOT", "热"), (101, "EXTREME_HOT", "极热"),
]
LEV_BETA_TOL, LEV_MIN_R2 = 0.15, 0.85
GROWTH = {"SOFTWARE", "NASDAQ100", "INFORMATION_TECHNOLOGY", "CLOUD", "CYBERSECURITY", "AI_INFRASTRUCTURE",
          "DATA_CENTERS", "GROWTH", "MOMENTUM", "ROBOTICS", "DISRUPTIVE_INNOVATION", "COMMUNICATION_SERVICES"}
DEFENSIVE = {"CONSUMER_STAPLES", "UTILITIES", "HEALTH_CARE", "LOW_VOLATILITY", "DIVIDEND", "QUALITY",
             "INSURANCE", "MEDICAL_DEVICES"}
CYCLICAL = {"SEMICONDUCTORS", "MEMORY", "EQUIPMENT", "ENERGY", "OIL_GAS_EP", "OIL_SERVICES", "MATERIALS",
            "METALS_MINING", "COPPER_MINERS", "GOLD_MINERS", "JUNIOR_GOLD_MINERS", "HOMEBUILDERS", "TRANSPORTATION",
            "AIRLINES", "BANKS", "REGIONAL_BANKS", "FINANCIALS", "INDUSTRIALS", "CAPITAL_MARKETS",
            "CONSUMER_DISCRETIONARY", "RETAIL", "BIOTECHNOLOGY", "URANIUM_NUCLEAR", "LITHIUM_BATTERY",
            "CLEAN_ENERGY", "AEROSPACE_DEFENSE", "REAL_ESTATE", "SMALL_CAP", "CHINA_INTERNET"}
MACRO_TOPS = {"BOND", "CASH_LIKE", "CURRENCY", "PRECIOUS_METALS", "CRYPTO", "COMMODITY"}


def band(t):
    if t is None or (isinstance(t, float) and math.isnan(t)):
        return None
    for hi, code, _ in BANDS:
        if t < hi:
            return code
    return BANDS[-1][1]


def pct5(s: pd.Series) -> pd.Series:
    """Percentile (0–100) of today's value within its own trailing 5 years."""
    return s.rolling(WIN5, min_periods=MIN_HIST).rank(pct=True) * 100


def mean_of(series: list[pd.Series], weights: list[float] | None = None) -> pd.Series:
    df = pd.concat(series, axis=1)
    if weights is None:
        return df.mean(axis=1)
    # Skip missing inputs and re-normalise the remaining weights (a young fund has no
    # acceleration reading yet; that must not blank the whole composite).
    w = pd.DataFrame(np.tile(weights, (len(df), 1)), index=df.index).where(df.notna().to_numpy())
    return pd.Series((df.fillna(0).to_numpy() * w.fillna(0).to_numpy()).sum(axis=1), index=df.index) \
        / w.sum(axis=1).replace(0, np.nan)


def regression(logp: pd.Series, w: int) -> dict[str, pd.Series]:
    """Rolling OLS of log price on time. Returns residual z, slope (per day) and R²."""
    t = pd.Series(np.arange(len(logp), dtype=float), index=logp.index).where(logp.notna())
    r = lambda x: x.rolling(w, min_periods=w)
    mt, ml = r(t).mean(), r(logp).mean()
    vt = r(t * t).mean() - mt * mt
    cov = r(t * logp).mean() - mt * ml
    vl = r(logp * logp).mean() - ml * ml
    slope = cov / vt
    resid = logp - (ml + slope * (t - mt))
    ssr = (vl - slope * slope * vt).clip(lower=1e-12) * w / (w - 2)
    return {"z": resid / np.sqrt(ssr), "slope": slope, "r2": (slope * slope * vt / vl).clip(0, 1)}


def weekly_rsi(p: pd.Series, n: int = 14) -> pd.Series:
    wk = p.dropna().resample("W-FRI").last()
    d = wk.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    return rsi.reindex(p.index, method="ffill")


def lev_check(r_member: pd.Series, r_base: pd.Series, expected: float) -> dict:
    df = pd.concat([r_member, r_base], axis=1).dropna().tail(YEAR)
    if len(df) < 40:
        return {"beta": None, "r2": None, "pass": False, "n": len(df), "expected": expected}
    x, y = df.iloc[:, 1].to_numpy(), df.iloc[:, 0].to_numpy()
    beta = float(np.cov(x, y)[0, 1] / np.var(x, ddof=1))
    r2 = float(np.corrcoef(x, y)[0, 1] ** 2)
    ok = abs(beta - expected) <= LEV_BETA_TOL * abs(expected) and r2 >= LEV_MIN_R2
    return {"beta": round(beta, 2), "r2": round(r2, 3), "pass": bool(ok), "n": len(df), "expected": expected}


def drawdown_cycles(p: pd.Series, depth: float = 0.20, recover_days: int = 3 * YEAR) -> tuple[int, int]:
    """(number of ≥depth drawdowns, how many recovered to the prior peak within recover_days)."""
    p = p.dropna()
    peak, peak_i, trough_hit, n, rec = p.iloc[0], 0, False, 0, 0
    vals = p.to_numpy()
    for i, v in enumerate(vals):
        if v >= peak:
            if trough_hit:
                rec += int(i - peak_i <= recover_days)
                trough_hit = False
            peak, peak_i = v, i
        elif not trough_hit and v <= peak * (1 - depth):
            trough_hit, n = True, n + 1
    return n, rec


def episodes(mask: pd.Series, gap: int = 60) -> list:
    """Dates where mask turns on, at least `gap` days after the previous episode start."""
    out, last = [], None
    idx = mask.index
    on = mask.fillna(False).to_numpy()
    for i in range(1, len(on)):
        if on[i] and not on[i - 1] and (last is None or i - last >= gap):
            out.append(idx[i])
            last = i
    return out


class EngineV2:
    def __init__(self, u: Universe, bars: dict[str, pd.DataFrame]):
        self.u = u
        names = [t for t in list(u.etfs) + list(u.stocks) if t in bars]
        self.missing = sorted((set(u.etfs) | set(u.stocks)) - set(names))
        panel = lambda col: pd.DataFrame({t: bars[t][col] for t in names}).sort_index()
        # Foreign listings trade on other calendars; align them to the US calendar by carrying forward.
        us_days = pd.DataFrame({t: bars[t]["close"] for t in names if t in u.etfs}).index
        self.adj = panel("adj_close").reindex(us_days).ffill(limit=3)
        self.close = panel("close").reindex(us_days)
        self.vol = panel("volume").reindex(us_days)
        self.dv = self.close * self.vol
        self.ret = np.log(self.adj).diff()
        self.dates = self.adj.index
        self.fam: dict[str, dict] = {}
        self.node: dict[str, dict] = {}
        self.checks: dict[str, dict] = {}

    # ── families ───────────────────────────────────────────────
    def _price_member(self, fid):
        for e in self.u.members(fid):
            if e["role"] in ("CORE", "THEMATIC") and e["ticker"] in self.adj:
                return e["ticker"]
        return None

    def _family_price(self, fid: str):
        """Core price, spliced onto a holdings-weighted synthetic history when the fund is young."""
        f = self.u.families[fid]
        core = self._price_member(fid)
        if core is None:
            return None, None, None
        p = self.adj[core]
        first = p.first_valid_index()
        bf = f.get("backfill")
        if not bf or first is None:
            return p, core, None
        cols = [t for t in bf if t in self.ret]
        if not cols:
            return p, core, None
        w = pd.Series({t: bf[t] for t in cols})
        r = self.ret[cols].fillna(0) @ (w / w.sum())
        if first <= r.index[0] or not (r.loc[:first] != 0).any():
            return p, core, None  # the fund has the full history already
        synth = np.exp(r.cumsum())
        synth = synth / synth.loc[first] * p.loc[first]
        return p.combine_first(synth.where(synth.index < first)), core, first

    def run_families(self):
        for fid, f in self.u.families.items():
            members = [e for e in self.u.members(fid) if e["ticker"] in self.adj]
            if not members:
                continue
            m: dict = {"members": [e["ticker"] for e in members]}
            if not f.get("sentiment_only"):
                p, core, bf_until = self._family_price(fid)
                if p is None:
                    continue
                attn = [e["ticker"] for e in members if e["role"] in ("CORE", "ALTERNATIVE_CORE", "THEMATIC")]
                m.update(self._price_metrics(p))
                m.update({"core": core, "price": p, "backfilled_until": bf_until,
                          "dv": self.dv[attn].sum(axis=1, min_count=1)})
                m["weight"] = math.sqrt(float(m["dv"].tail(60).median() or 0) or 0)
                m.update(self._volume_metrics(m["dv"], p))
                base_ret, base_dv = self.ret[core], self.dv[core]
            elif f.get("identity_basis") == "SINGLE_STOCK":
                stk = f["underlying_stock"]
                if stk not in self.adj:
                    continue
                base_ret, base_dv = self.ret[stk], self.dv[stk]
            else:
                proxy_core = self._price_member(f["price_proxy_family"])
                if proxy_core is None:
                    continue
                base_ret, base_dv = self.ret[proxy_core], self.dv[proxy_core]
            lev = self._leverage(members, base_ret, base_dv)
            if lev:
                m["lev"] = lev
                m["lev_group"] = "single" if f.get("identity_basis") == "SINGLE_STOCK" else "index"
            self.fam[fid] = m

    def _price_metrics(self, p: pd.Series) -> dict:
        lp = np.log(p)
        g6, g12 = regression(lp, 126), regression(lp, YEAR)
        sd = lp.diff().rolling(YEAR, min_periods=60).std()
        acc = {k: (lp.diff(k) - g12["slope"] * k) / (sd * math.sqrt(k)) for k in (20, 60)}
        rsi = weekly_rsi(p)
        out = {
            "z126": g6["z"], "z252": g12["z"], "slope252": g12["slope"], "r2_252": g12["r2"],
            "acc20": acc[20], "acc60": acc[60], "rsi_w": rsi,
            "stretch": mean_of([pct5(g6["z"]), pct5(g12["z"]), pct5(rsi)]),
            "accel": mean_of([pct5(acc[20]), pct5(acc[60])]),
        }
        out["p_z252"], out["p_acc"] = pct5(g12["z"]), out["accel"]
        return out

    def _volume_metrics(self, dv: pd.Series, p: pd.Series) -> dict:
        ratio = np.log(dv.rolling(20, min_periods=10).mean() / dv.rolling(YEAR, min_periods=60).median())
        activity = pct5(ratio)
        r20 = np.log(p).diff(20)
        direction = (r20 / r20.rolling(YEAR, min_periods=60).std()).clip(-1, 1)
        return {"activity": activity, "volume_dir": 50 + 0.5 * activity * direction}

    def _leverage(self, members, base_ret, base_dv) -> dict | None:
        bull = bear = None
        for e in members:
            if e["role"] not in SENTIMENT_ROLES:
                continue
            sign = 1 if e["direction"] == "LONG" else -1
            self.checks[e["ticker"]] = lev_check(self.ret[e["ticker"]], base_ret, sign * e["leverage"])
            if not (e.get("verified") or self.checks[e["ticker"]]["pass"]):
                continue
            x = self.dv[e["ticker"]] * e["leverage"]  # NaN before the fund existed, never 0
            if sign > 0:
                bull = x if bull is None else bull.add(x, fill_value=0)
            else:
                bear = x if bear is None else bear.add(x, fill_value=0)
        if bull is None and bear is None:
            return None
        b20 = base_dv.rolling(20, min_periods=10).sum()
        out, parts = {}, []
        if bull is not None:
            out["spec"] = pct5(bull.rolling(20, min_periods=10).sum() / b20)
            parts.append(out["spec"])
        if bear is not None:
            out["hedge"] = pct5(bear.rolling(20, min_periods=10).sum() / b20)
            parts.append(100 - out["hedge"])
        if bull is not None and bear is not None:
            s = bull.rolling(20, min_periods=10).sum()
            out["share_raw"] = s / (s + bear.rolling(20, min_periods=10).sum())
            out["share"] = pct5(out["share_raw"])
            parts.append(out["share"])
        out["score"] = mean_of(parts)
        return out

    # ── nodes ──────────────────────────────────────────────────
    def _families_on(self, nid):
        direct = [fid for fid, f in self.u.families.items() if f["node"] == nid and fid in self.fam]
        price = [f for f in direct if "price" in self.fam[f]]
        if not price:
            anchor = self.u.nodes[nid].get("anchor_family")
            if anchor in self.fam and "price" in self.fam[anchor]:
                price = [anchor]
                direct = direct + [anchor] + [
                    f for f, ff in self.u.families.items() if ff["node"] == self.u.families[anchor]["node"]
                    and f in self.fam and f != anchor and "lev" in self.fam[f]]
        return direct, price

    def _children(self, nid):
        b = self.u.nodes[nid].get("breadth_basket")
        if isinstance(b, list):
            return b
        if isinstance(b, str):
            return [c for c in self.u.nodes if c.rsplit("/", 1)[0] == b and self.u.nodes[c].get("scored")]
        kids = []
        for c, n in self.u.nodes.items():
            parent = c.rsplit("/", 1)[0] if "/" in c else None
            if parent == nid and n.get("scored"):
                kids.append(c)
            elif parent and parent.rsplit("/", 1)[0] == nid and not self.u.nodes[parent].get("scored") \
                    and self.u.nodes[parent]["level"] == "DIMENSION" and n.get("scored"):
                kids.append(c)
        return kids

    def run_nodes(self):
        for nid, n in self.u.nodes.items():
            if not n.get("scored") or n.get("status") == "NO_COVERAGE":
                continue
            fids, pf = self._families_on(nid)
            if not pf:
                continue
            w = np.array([self.fam[f]["weight"] for f in pf]) + 1e-9
            w = w / w.sum()
            lead = pf[int(np.argmax(w))]
            L = self.fam[lead]
            agg = lambda k: pd.Series(mean_of([self.fam[f][k] for f in pf], list(w)), index=self.dates)
            rec = {"families": fids, "lead": lead, "lead_core": L["core"], "price": L["price"],
                   "backfilled_until": L["backfilled_until"], "slope252": L["slope252"], "r2_252": L["r2_252"],
                   "rsi_w": L["rsi_w"], "z252": L["z252"], "acc20": L["acc20"],
                   "f": {"stretch": agg("stretch"), "accel": agg("accel")},
                   "volume_dir": agg("volume_dir"), "activity": agg("activity"), "p_z252": agg("p_z252")}
            groups = {}
            for f in fids:
                lev = self.fam[f].get("lev")
                if lev:
                    groups.setdefault(self.fam[f]["lev_group"], []).append(lev)
            rec["lev"] = {g: {k: mean_of([x[k] for x in ls if k in x]) for k in ("score", "spec", "hedge", "share", "share_raw")
                              if any(k in x for x in ls)} for g, ls in groups.items()}
            lev_score = mean_of([v["score"] for v in rec["lev"].values()]) if rec["lev"] else None
            rec["lev_score"] = lev_score
            rec["f"]["crowding"] = mean_of([rec["volume_dir"]] + ([lev_score] if lev_score is not None else []))
            rec["volume_dir"] = pd.Series(rec["volume_dir"], index=self.dates)
            self.node[nid] = rec

        for nid, rec in self.node.items():
            n = self.u.nodes[nid]
            bench = n.get("rs_benchmark")
            if bench in self.node:
                lr = np.log(rec["price"] / self.node[bench]["price"])
                rec["rs_z"] = regression(lr, 126)["z"]
                rec["f"]["rs"] = mean_of([pct5(rec["rs_z"]), pct5(regression(lr, YEAR)["z"])])
                rec["rs_trend"] = regression(lr, 5 * YEAR)["slope"] * YEAR
            members = [self.node[c]["price"].rename(c) for c in self._children(nid) if c in self.node]
            stocks = [self.adj[t].rename(t) for t, s in self.u.stocks.items()
                      if t in self.adj and (s["node"] == nid or s["node"].startswith(nid + "/"))]
            basket = members + stocks
            if len(basket) >= 5:
                px = pd.concat(basket, axis=1)
                valid = px.notna()
                above = ((px > px.rolling(50).mean()) & valid).sum(axis=1) / valid.sum(axis=1) * 100
                hi = ((px >= px.rolling(20).max()) & valid).sum(axis=1) / valid.sum(axis=1)
                lo = ((px <= px.rolling(20).min()) & valid).sum(axis=1) / valid.sum(axis=1)
                rec["above50"], rec["hl_net"] = above, (hi - lo + 1) * 50
                rec["f"]["breadth"] = mean_of([pct5(above), pct5(rec["hl_net"])])
                rec["basket"] = [s.name for s in basket]

            comp = mean_of([rec["f"][k] for k in FACTORS if k in rec["f"]],
                           [WEIGHTS[k] for k in FACTORS if k in rec["f"]])
            comp = pd.Series(comp, index=self.dates)
            rec["composite"] = comp
            temp = pct5(comp).rolling(SMOOTH, min_periods=1).mean()
            rec["temp"] = temp.where(comp.notna())
            self._checklist(rec)

    def _checklist(self, rec):
        def last(s):
            s = s.dropna() if s is not None else None
            return None if s is None or not len(s) else float(s.iloc[-1])
        items = [
            ("偏离趋势（252 日）", rec["p_z252"], 95, 5),
            ("周线 RSI", rec["rsi_w"], 70, 30),
            ("动量加速", rec["f"]["accel"], 90, 10),
            ("带方向成交额", rec["volume_dir"], 90, 10),
            ("杠杆情绪", rec.get("lev_score"), 90, 10),
            ("广度：站上 50 日线", rec.get("above50"), 85, 15),
        ]
        hot = pd.Series(0, index=self.dates, dtype=float)
        cold = pd.Series(0, index=self.dates, dtype=float)
        out = []
        for name, s, h, c in items:
            if s is None:
                out.append({"name": name, "value": None, "hot": None, "cold": None})
                continue
            s = pd.Series(s, index=self.dates)
            hot += (s >= h).astype(float)
            cold += (s <= c).astype(float)
            v = last(s)
            out.append({"name": name, "value": None if v is None else round(v, 1), "hot_at": h, "cold_at": c,
                        "hot": v is not None and v >= h, "cold": v is not None and v <= c})
        t = rec["temp"]
        conf_hot = ((t >= 95) & (hot >= 3)).astype(int).rolling(3).sum() == 3
        conf_cold = ((t <= 5) & (cold >= 3)).astype(int).rolling(3).sum() == 3
        rec["checklist"] = {"items": out, "hot_count": int(hot.iloc[-1]), "cold_count": int(cold.iloc[-1]),
                            "confirmed": "HOT" if conf_hot.iloc[-1] else "COLD" if conf_cold.iloc[-1] else None}
        rec["confirmed_hot"], rec["confirmed_cold"] = conf_hot, conf_cold

    # ── eligibility (auto suggestion; Owner reviews) ───────────
    def eligibility(self, nid: str) -> dict:
        rec, n = self.node[nid], self.u.nodes[nid]
        parts = nid.split("/")
        p = rec["price"].dropna().tail(10 * YEAR)
        years = len(p) / YEAR
        cagr = (p.iloc[-1] / p.iloc[0]) ** (1 / years) - 1 if years > 1 else None
        dd_n, dd_rec = drawdown_cycles(p)
        t = rec["temp"]
        fwd = np.log(rec["price"].shift(-120) / rec["price"])
        cold_eps = [d for d in episodes(t < 20) if pd.notna(fwd.get(d))]
        hot_eps = [d for d in episodes(t > 80) if pd.notna(fwd.get(d))]
        med = lambda ds: float(np.median([fwd[d] for d in ds]) * 100) if ds else None
        mc, mh = med(cold_eps), med(hot_eps)
        rs_tr = rec.get("rs_trend")
        rs_slope = float(rs_tr.dropna().iloc[-1]) * 100 if rs_tr is not None and rs_tr.notna().any() else None
        fam = self.u.families[rec["lead"]]
        instrument = fam.get("identity_basis") == "FUTURES_STRATEGY" or n.get("mode") == "REFERENCE" or parts[0] == "VOLATILITY"
        tests = {
            "T1": {"pass": cagr is not None and cagr > 0, "value": None if cagr is None else round(cagr * 100, 1),
                   "label": "长期回报为正", "detail": f"{min(years, 10):.1f} 年年化"},
            "T2": {"pass": dd_rec >= 2, "value": f"{dd_rec}/{dd_n}", "label": "有周期（≥2 次大跌后 3 年内收复）"},
            "T3": {"pass": len(cold_eps) >= 3 and len(hot_eps) >= 3 and mc is not None and mh is not None and mc > mh,
                   "value": {"cold_n": len(cold_eps), "hot_n": len(hot_eps),
                             "cold_med120": None if mc is None else round(mc, 1),
                             "hot_med120": None if mh is None else round(mh, 1)},
                   "label": "冷之后好过热之后（120 日中位数）"},
            # Lagging the index is not value destruction (2021–26 mega-cap tech beat almost every
            # sector by >5%/yr). Fail only on severe lag AND an absolute return below cash.
            "T4": {"pass": rs_slope is None or rs_slope > -10 or (cagr is not None and cagr >= 0.03),
                   "value": None if rs_slope is None else round(rs_slope, 1),
                   "label": "未在严重跑输的同时绝对回报低于现金（5 年相对 < −10%/年 且 年化 < 3%）"},
            "T5": {"pass": not instrument, "label": "不是期货展期/波动率工具"},
        }
        if not tests["T5"]["pass"]:
            cls = "INSTRUMENT"
        elif parts[0] in MACRO_TOPS:
            cls = "MACRO"
        elif not tests["T1"]["pass"] or not tests["T4"]["pass"]:
            cls = "SECULAR_DECLINE"
        elif parts[-1] in DEFENSIVE:
            cls = "DEFENSIVE"
        elif parts[-1] in GROWTH:
            cls = "STRUCTURAL_GROWTH"
        elif parts[-1] in CYCLICAL:
            cls = "CYCLICAL"          # industry prior; T2 shows whether the data agrees
        elif parts[0] == "EQUITY" and (len(parts) <= 2 or parts[2] in ("BROAD", "STYLE")):
            cls = "BROAD_MARKET"
        else:
            cls = "CYCLICAL" if tests["T2"]["pass"] else "STRUCTURAL_GROWTH"
        return {"auto_class": cls, "tests": tests}

    def band_stats(self, nid: str) -> dict:
        rec = self.node[nid]
        t, p = rec["temp"], rec["price"]
        out = {}
        for code, mask in (("EXTREME_COLD", t < 5), ("COLD", t < 20), ("HOT", t >= 80), ("EXTREME_HOT", t >= 95)):
            ds = episodes(mask)
            row = {"episodes": len(ds)}
            for h in (60, 120):
                f = [float(np.log(p.shift(-h)[d] / p[d]) * 100) for d in ds if pd.notna(p.shift(-h).get(d))]
                row[f"n{h}"] = len(f)
                row[f"med{h}"] = round(float(np.median(f)), 1) if f else None
                row[f"worst{h}"] = round(float(np.min(f)), 1) if f else None
                row[f"best{h}"] = round(float(np.max(f)), 1) if f else None
            out[code] = row
        return out

    def run(self):
        self.run_families()
        self.run_nodes()
        return self


ACTIONS = {
    "TRIM": "参考减仓", "NO_ADD": "不新增", "NO_CHASE": "不追高", "HOLD": "观望",
    "START_BUY": "开始分批", "ADD_BUY": "加大分批", "WAIT": "等待企稳", "NA": "不适用",
}


def reference_action(cls: str, b: str | None, confirmed: str | None, accel_pct: float | None) -> str:
    if cls in ("INSTRUMENT", "MACRO", "DEFENSIVE") or b is None:
        return "NA"
    growthy = cls in ("STRUCTURAL_GROWTH", "BROAD_MARKET")
    if b == "EXTREME_HOT":
        if confirmed == "HOT":
            return "NO_CHASE" if growthy else "TRIM"
        return "NO_CHASE" if growthy else "NO_ADD"
    if b == "HOT":
        return "NO_CHASE" if growthy else "NO_ADD"
    if cls == "SECULAR_DECLINE":
        return "HOLD"
    if b == "EXTREME_COLD":
        if accel_pct is not None and accel_pct <= 10:
            return "WAIT"
        return "ADD_BUY" if confirmed == "COLD" and not growthy else "START_BUY"
    if b == "COLD":
        return "START_BUY"
    return "HOLD"


def forward_stats(engine: EngineV2, horizons=(20, 60, 120), classes: dict | None = None) -> dict:
    rows = []
    for nid, rec in engine.node.items():
        if engine.u.nodes[nid].get("mode") != "DIRECTIONAL":
            continue
        p = rec["price"]
        d = {"t": rec["temp"], "node": nid, "cls": (classes or {}).get(nid)}
        for h in horizons:
            d[f"f{h}"] = (p.shift(-h) / p - 1) * 100
        rows.append(pd.DataFrame(d).dropna(subset=["t"]))
    df = pd.concat(rows)
    edges = [0, 5, 20, 40, 60, 80, 95, 100.01]
    df["bucket"] = pd.cut(df["t"], edges, right=False)

    def table(g_all):
        out = []
        for b, g in g_all.groupby("bucket", observed=False):
            row = {"lo": int(b.left), "hi": min(int(b.right), 100), "days": int(len(g))}
            for h in horizons:
                x = g[f"f{h}"].dropna()
                row[f"f{h}"] = None if len(x) < 30 else {
                    "n": int(len(x)), "mean": round(float(x.mean()), 2), "median": round(float(x.median()), 2),
                    "hit": round(float((x > 0).mean() * 100), 1)}
            out.append(row)
        return out

    by_class = {c: table(g) for c, g in df.groupby("cls") if c}
    return {"horizons": list(horizons), "n_nodes": int(df["node"].nunique()),
            "start": df.index.min().strftime("%Y-%m-%d"), "end": df.index.max().strftime("%Y-%m-%d"),
            "all": table(df), "by_class": by_class}
