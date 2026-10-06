"""Run the pipeline and write the website data file.

    python3 -m etf_temperature.build --source demo     # synthetic data, labelled DEMO
    python3 -m etf_temperature.build --source yahoo    # real EOD data (needs network)

Outputs:
    site/data.js                          window.ETF_TEMP = {...}  (the site reads this)
    data/snapshots/latest.json            same payload, for diffing / reproducibility
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import engine as v1
from . import sources
from .engine import risk_appetite
from .engine_v2 import ACTIONS, BANDS, FACTORS, WEIGHTS, EngineV2, band, forward_stats, reference_action
from .select import TOP_N, restrict, select
from .universe import load

ROOT = Path(__file__).resolve().parents[2]
HISTORY_DAYS = 260
CLASS_LABEL = {
    "CYCLICAL": "周期型", "STRUCTURAL_GROWTH": "结构成长", "DEFENSIVE": "防御型", "SECULAR_DECLINE": "结构衰退",
    "INSTRUMENT": "工具型", "MACRO": "宏观资产", "BROAD_MARKET": "宽基",
}


def _r(x, nd=1):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, nd)


def _last(s, nd=1):
    if s is None:
        return None
    s = pd.Series(s).dropna()
    return _r(s.iloc[-1], nd) if len(s) else None


def _ago(s, k):
    s = pd.Series(s).dropna()
    return _r(s.iloc[-1 - k]) if len(s) > k else None


def _delta(s, k):
    a, b = _last(s), _ago(s, k)
    return None if a is None or b is None else _r(a - b)


def trend_state(slope_day, r2):
    if slope_day is None or r2 is None:
        return None, None
    ann = math.exp(slope_day * 252) - 1
    if ann > 0.20 and r2 > 0.5:
        st = "STRONG_UP"
    elif ann > 0.05:
        st = "UP"
    elif ann < -0.20 and r2 > 0.5:
        st = "STRONG_DOWN"
    elif ann < -0.05:
        st = "DOWN"
    else:
        st = "FLAT"
    return st, round(ann * 100, 1)


def load_overrides() -> dict:
    p = ROOT / "data" / "eligibility.yaml"
    if not p.exists():
        return {}
    doc = yaml.safe_load(p.read_text()) or {}
    return {r["node"]: r for r in (doc.get("reviewed") or [])}


def build_payload(u, sel, eng: EngineV2, short: v1.Engine, mode: str, source: str) -> dict:
    dates = eng.dates
    tail = dates[-HISTORY_DAYS:]
    overrides = load_overrides()
    nodes, classes = {}, {}
    for nid, n in u.nodes.items():
        out = {
            "name": n["name"], "level": n["level"], "parent": nid.rsplit("/", 1)[0] if "/" in nid else None,
            "mode": n.get("mode"), "scored": bool(n.get("scored")), "status": n.get("status", "ACTIVE"),
            "note": n.get("note"), "rs_benchmark": n.get("rs_benchmark"), "alias_of": n.get("alias_of"),
            "families": [f for f, ff in u.families.items() if ff["node"] == nid],
            "anchor_family": n.get("anchor_family"), "temp": None,
        }
        rec = eng.node.get(nid)
        if rec is None:
            nodes[nid] = out
            continue
        t = rec["temp"]
        tl = _last(t)
        st, ann = trend_state(_last(rec["slope252"], 6), _last(rec["r2_252"], 3))
        el = eng.eligibility(nid)
        ov = overrides.get(nid)
        final = ov["class"] if ov else el["auto_class"]
        classes[nid] = final
        b = band(tl)
        stats = eng.band_stats(nid)
        act = reference_action(final, b, rec["checklist"]["confirmed"], _last(rec["f"]["accel"]))
        key = {"EXTREME_COLD": "EXTREME_COLD", "COLD": "COLD", "HOT": "HOT", "EXTREME_HOT": "EXTREME_HOT"}.get(b)
        if act not in ("NA", "HOLD") and key and stats[key]["episodes"] < 3:
            act = "THIN"  # too few independent episodes to say anything
        sh = short.node.get(nid)
        out.update({
            "temp": tl, "band": b, "d1": _delta(t, 1), "d5": _delta(t, 5), "d20": _delta(t, 20),
            "temp_short": _last(sh["temperature"]) if sh else None,
            "trend": {"state": st, "ann": ann, "r2": _last(rec["r2_252"], 2)},
            "factors": {k: _last(rec["f"].get(k)) for k in FACTORS},
            "sub": {
                "z252": _last(rec["z252"], 2), "rsi_w": _last(rec["rsi_w"]), "acc20": _last(rec["acc20"], 2),
                "activity": _last(rec["activity"]), "volume_dir": _last(rec["volume_dir"]),
                "above50": _last(rec.get("above50")), "hl_net": _last(rec.get("hl_net")),
                "rs_z": _last(rec.get("rs_z"), 2),
            },
            "lev": {g: {k: _last(v, 3 if k == "share_raw" else 1) for k, v in d.items()} for g, d in rec["lev"].items()},
            "checklist": rec["checklist"],
            "eligibility": {**el, "final_class": final, "reviewed": bool(ov), "review_reason": (ov or {}).get("reason")},
            "action": act, "band_stats": stats,
            "backfilled_until": rec["backfilled_until"].strftime("%Y-%m-%d") if rec["backfilled_until"] is not None else None,
            "lead_core": rec["lead_core"], "basket": rec.get("basket"),
            "hist": [_r(x, 0) for x in pd.Series(t).reindex(tail).tolist()],
            "hist_short": [_r(x, 0) for x in sh["temperature"].reindex(tail).tolist()] if sh else None,
            "fhist": {k: [_r(x, 0) for x in pd.Series(v).reindex(tail).tolist()] for k, v in rec["f"].items()},
        })
        nodes[nid] = out

    tab = sel.table.set_index("ticker")
    etfs = {}
    for tk, e in u.etfs.items():
        row = {k: e.get(k) for k in ("name", "issuer", "family", "role", "direction", "leverage", "verified", "note")}
        r = tab.loc[tk]
        row.update({"bucket": r["bucket"], "rank": int(r["rank"]), "adv": _r(r["adv"] / 1e6, 1),
                    "selected": bool(r["selected"]), "reason": r["reason"] if r["selected"] else None})
        if tk in eng.adj and eng.adj[tk].notna().any():
            p = eng.adj[tk].dropna()
            row.update({"close": _r(eng.close[tk].dropna().iloc[-1], 2), "r5": _r((p.iloc[-1] / p.iloc[-6] - 1) * 100, 2) if len(p) > 6 else None,
                        "r20": _r((p.iloc[-1] / p.iloc[-21] - 1) * 100, 2) if len(p) > 21 else None,
                        "since": p.index[0].strftime("%Y-%m-%d")})
        else:
            row["missing"] = True
        if tk in eng.checks:
            row["check"] = eng.checks[tk]
        etfs[tk] = row

    stocks = {}
    for tk, s in u.stocks.items():
        row = {"node": s["node"], "name": s.get("name"), "listing": s.get("listing", "US")}
        if tk in eng.adj and eng.adj[tk].notna().sum() > 60:
            p = eng.adj[tk].dropna()
            row.update({"r20": _r((p.iloc[-1] / p.iloc[-21] - 1) * 100, 1),
                        "above50": bool(p.iloc[-1] > p.tail(50).mean())})
        stocks[tk] = row

    fams = {fid: {**{k: f.get(k) for k in ("name", "node", "benchmark", "identity_basis", "note", "sentiment_only",
                                           "price_proxy_family", "underlying_stock")},
                  "members": [e["ticker"] for e in u.members(fid)], "backfill": f.get("backfill")}
            for fid, f in u.families.items()}

    ra = risk_appetite(short)
    risk = {"score": _last(ra["score"]), "d5": _delta(ra["score"], 5),
            "hist": [_r(x, 0) for x in ra["score"].reindex(tail).tolist()],
            "components": [{k: v for k, v in c.items() if k != "series"} | {"value": _last(c["series"])}
                           for c in ra["components"]]}

    return {
        "meta": {
            "mode": mode, "source": source, "asof": dates[-1].strftime("%Y-%m-%d"), "version": "v2",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
            "n_etfs": len(sel.table), "n_selected": len(sel.selected), "n_families": len(u.families),
            "n_nodes": len(u.nodes), "n_stocks": len(u.stocks), "top_n": TOP_N,
            "n_verified": sum(bool(e["verified"]) for e in u.etfs.values()), "missing": eng.missing,
            "weights": WEIGHTS, "bands": [{"max": hi, "code": c, "label": lb} for hi, c, lb in BANDS],
            "classes": CLASS_LABEL, "actions": ACTIONS | {"THIN": "样本不足"},
        },
        "dates": [d.strftime("%Y-%m-%d") for d in tail], "nodes": nodes, "families": fams,
        "etfs": etfs, "stocks": stocks, "risk": risk, "research": forward_stats(eng, classes=classes),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["demo", "yahoo"], default="demo")
    ap.add_argument("--years", type=int, default=10)
    args = ap.parse_args(argv)

    u = load()
    if u.errors:
        raise SystemExit("universe invalid:\n" + "\n".join(u.errors))
    tickers = list(u.etfs) + list(u.stocks)
    if args.source == "demo":
        bars, mode = sources.make_demo(u, years=args.years), "DEMO"
    else:
        bars, mode = sources.fetch_yahoo(tickers, years=args.years), "LIVE"

    sel = select(u, bars)
    view = restrict(u, sel.selected)
    eng = EngineV2(view, bars).run()
    short = v1.Engine(view, {t: b for t, b in bars.items() if t in view.etfs}).run()
    payload = build_payload(view, sel, eng, short, mode, args.source)
    # The pool page lists every candidate, selected or not.
    payload["pool"] = sel.table.assign(adv=lambda d: (d["adv"] / 1e6).round(1)).to_dict(orient="records")

    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    (ROOT / "site").mkdir(exist_ok=True)
    (ROOT / "site" / "data.js").write_text("window.ETF_TEMP=" + text + ";\n")
    snap = ROOT / "data" / "snapshots"
    snap.mkdir(parents=True, exist_ok=True)
    (snap / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    scored = [n for n in payload["nodes"].values() if n["temp"] is not None]
    print(f"{mode} asof={payload['meta']['asof']} selected={len(sel.selected)}/{len(u.etfs)} "
          f"nodes_scored={len(scored)} size={len(text)/1e3:.0f}KB missing={len(eng.missing)}")


if __name__ == "__main__":
    main()
