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

import pandas as pd

from . import sources
from .engine import BANDS, FACTORS, Engine, band, forward_stats, risk_appetite
from .universe import load

ROOT = Path(__file__).resolve().parents[2]
HISTORY_DAYS = 260


def _r(x, nd=1):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, nd)


def _last(s: pd.Series | None, nd=1):
    if s is None:
        return None
    s = s.dropna()
    return _r(s.iloc[-1], nd) if len(s) else None


def _ago(s: pd.Series, k: int):
    s = s.dropna()
    return _r(s.iloc[-1 - k]) if len(s) > k else None


def build_payload(u, eng: Engine, mode: str, source: str) -> dict:
    asof = eng.dates[-1]
    hist_dates = [d.strftime("%Y-%m-%d") for d in eng.dates[-HISTORY_DAYS:]]

    nodes = {}
    for nid, n in u.nodes.items():
        rec = eng.node.get(nid)
        out = {
            "name": n["name"], "level": n["level"], "parent": nid.rsplit("/", 1)[0] if "/" in nid else None,
            "mode": n.get("mode"), "scored": bool(n.get("scored")), "status": n.get("status", "ACTIVE"),
            "note": n.get("note"), "rs_benchmark": n.get("rs_benchmark"), "alias_of": n.get("alias_of"),
            "families": [f for f, ff in u.families.items() if ff["node"] == nid],
            "anchor_family": n.get("anchor_family"), "temp": None,
        }
        if rec is not None:
            t = rec["temperature"]
            last_t = _last(t)
            cov = int(rec["coverage"].iloc[-1]) if len(rec["coverage"]) else 0
            conf = "HIGH" if cov >= 4 else "MED" if cov == 3 else "LOW"
            if rec.get("tier3_only"):
                conf = "LOW"
            out.update({
                "temp": last_t, "band": band(last_t),
                "d1": _r((last_t or 0) - (_ago(t, 1) or 0)) if _ago(t, 1) is not None else None,
                "d5": _r((last_t or 0) - (_ago(t, 5) or 0)) if _ago(t, 5) is not None else None,
                "d20": _r((last_t or 0) - (_ago(t, 20) or 0)) if _ago(t, 20) is not None else None,
                "activity": _last(rec["series"].get("activity")),
                "factors": {f: _last(rec["series"].get(f)) for f in FACTORS},
                "sub": {k: _last(v, 3 if k == "bull_share_raw" else 1) for k, v in rec["sub"].items()},
                "coverage": cov, "confidence": conf,
                "lead_core": rec.get("lead_core"), "basket": rec.get("basket"),
                "hist": [_r(x, 0) for x in t.reindex(eng.dates[-HISTORY_DAYS:]).tolist()],
                "fhist": {f: [_r(x, 0) for x in rec["series"][f].reindex(eng.dates[-HISTORY_DAYS:]).tolist()]
                          for f in FACTORS if f in rec["series"]},
            })
        nodes[nid] = out

    etfs = {}
    for t, e in u.etfs.items():
        row = {k: e.get(k) for k in ("name", "issuer", "family", "role", "direction", "leverage", "tier", "verified", "note")}
        row["theme_tags"] = e.get("theme_tags", [])
        if t in eng.adj:
            p, dv = eng.adj[t].dropna(), eng.dv[t].dropna()
            row.update({
                "close": _r(eng.close[t].dropna().iloc[-1], 2),
                "r1": _r(p.pct_change(1).iloc[-1] * 100, 2), "r5": _r(p.pct_change(5).iloc[-1] * 100, 2),
                "r20": _r(p.pct_change(20).iloc[-1] * 100, 2),
                "dv20": _r(dv.tail(20).median() / 1e6, 1),
            })
        else:
            row["missing"] = True
        if t in eng.checks:
            row["check"] = eng.checks[t]
        etfs[t] = row

    fams = {fid: {**{k: f.get(k) for k in ("name", "node", "benchmark", "identity_basis", "note",
                                           "sentiment_only", "price_proxy_family")},
                  "members": [e["ticker"] for e in u.members(fid)]}
            for fid, f in u.families.items()}

    ra = risk_appetite(eng)
    risk = {
        "score": _last(ra["score"]), "d5": None,
        "hist": [_r(x, 0) for x in ra["score"].reindex(eng.dates[-HISTORY_DAYS:]).tolist()],
        "components": [{k: v for k, v in c.items() if k != "series"} | {"value": _last(c["series"])}
                       for c in ra["components"]],
    }
    if risk["score"] is not None and _ago(ra["score"], 5) is not None:
        risk["d5"] = _r(risk["score"] - _ago(ra["score"], 5))

    return {
        "meta": {
            "mode": mode, "source": source, "asof": asof.strftime("%Y-%m-%d"),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
            "n_etfs": len(u.etfs), "n_families": len(u.families), "n_nodes": len(u.nodes),
            "n_verified": sum(bool(e["verified"]) for e in u.etfs.values()),
            "missing": eng.missing, "window": 252,
            "bands": [{"max": hi, "code": c, "label": lb} for hi, c, lb in BANDS],
        },
        "dates": hist_dates, "nodes": nodes, "families": fams, "etfs": etfs, "risk": risk,
        "research": forward_stats(eng),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["demo", "yahoo", "stooq"], default="demo")
    ap.add_argument("--years", type=int, default=10)
    args = ap.parse_args(argv)

    u = load()
    if u.errors:
        raise SystemExit("universe invalid:\n" + "\n".join(u.errors))
    if args.source == "demo":
        bars = sources.make_demo(u, years=args.years)
        mode = "DEMO"
    elif args.source == "yahoo":
        bars = sources.fetch_yahoo(list(u.etfs), years=args.years)
        mode = "LIVE"
    else:
        bars = sources.fetch_stooq(list(u.etfs))
        mode = "LIVE"

    eng = Engine(u, bars).run()
    payload = build_payload(u, eng, mode, args.source)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    (ROOT / "site").mkdir(exist_ok=True)
    (ROOT / "site" / "data.js").write_text("window.ETF_TEMP=" + text + ";\n")
    snap = ROOT / "data" / "snapshots"
    snap.mkdir(parents=True, exist_ok=True)
    (snap / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    scored = [n for n in payload["nodes"].values() if n["temp"] is not None]
    print(f"{mode} asof={payload['meta']['asof']} nodes_scored={len(scored)} "
          f"size={len(text)/1e3:.0f}KB missing={len(eng.missing)}")


if __name__ == "__main__":
    main()
