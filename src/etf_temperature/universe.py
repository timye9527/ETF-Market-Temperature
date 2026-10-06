"""Load and validate the taxonomy + ETF universe.

The universe YAML stores classification only once, on the family's node.
`resolve()` derives each ETF's asset_class / region / sector / industry from
that node path, so adding an ETF never requires touching engine code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

ROLES = {
    "CORE", "ALTERNATIVE_CORE", "LEVERAGED_BULL", "LEVERAGED_BEAR",
    "INVERSE", "SATELLITE", "THEMATIC", "PROXY",
}
PRICE_ROLES = {"CORE", "ALTERNATIVE_CORE", "THEMATIC"}
SENTIMENT_ROLES = {"LEVERAGED_BULL", "LEVERAGED_BEAR", "INVERSE"}
TIERS = {1, 2, 3, "IGNORE"}
IDENTITY_BASES = {"INDEX", "SPOT_ASSET", "FUTURES_STRATEGY", "ACTIVE"}
LEVELS = {
    "ROOT", "ASSET_CLASS", "REGION", "DIMENSION", "SEGMENT",
    "SECTOR", "INDUSTRY", "SUB_INDUSTRY", "THEME",
}


@dataclass
class Universe:
    nodes: dict[str, dict]
    families: dict[str, dict]
    etfs: dict[str, dict]
    errors: list[str] = field(default_factory=list)

    def members(self, family_id: str) -> list[dict]:
        return [e for e in self.etfs.values() if e["family"] == family_id]

    def resolve(self, ticker: str) -> dict:
        """Classification of one ETF, derived from its family's node path."""
        etf = self.etfs[ticker]
        fam = self.families[etf["family"]]
        parts = fam["node"].split("/")
        out = {
            "ticker": ticker,
            "family_id": fam["id"],
            "node": fam["node"],
            "benchmark": fam.get("benchmark"),
            "asset_class": None, "region": None, "sector": None,
            "industry": None, "theme": None,
        }
        if parts[0] == "THEME":
            out["theme"] = parts[1]
            out["asset_class"] = "EQUITY"
            return out
        out["asset_class"] = parts[0]
        if parts[0] == "EQUITY" and len(parts) > 1:
            out["region"] = parts[1]
            if "SECTOR" in parts:
                i = parts.index("SECTOR")
                rest = parts[i + 1:]
                out["sector"] = rest[0] if rest else None
                out["industry"] = "/".join(rest[1:]) or None
        return out


def load(data_dir: Path = DATA_DIR) -> Universe:
    tax = yaml.safe_load((data_dir / "taxonomy.yaml").read_text())
    uni = yaml.safe_load((data_dir / "etf_universe.yaml").read_text())
    u = Universe(
        nodes={n["id"]: n for n in tax["nodes"]},
        families={f["id"]: f for f in uni["families"]},
        etfs={e["ticker"]: e for e in uni["etfs"]},
    )
    u.errors = validate(u, tax, uni)
    return u


def validate(u: Universe, tax: dict, uni: dict) -> list[str]:
    errs: list[str] = []

    def dupes(items, key):
        seen, out = set(), set()
        for it in items:
            (out if it[key] in seen else seen).add(it[key])
        return out

    for d in dupes(tax["nodes"], "id"):
        errs.append(f"duplicate node id {d}")
    for d in dupes(uni["families"], "id"):
        errs.append(f"duplicate family id {d}")
    for d in dupes(uni["etfs"], "ticker"):
        errs.append(f"duplicate ticker {d}")

    # Nodes: parent must exist; references must resolve.
    for nid, n in u.nodes.items():
        if n.get("level") not in LEVELS:
            errs.append(f"node {nid}: bad level {n.get('level')}")
        if "/" in nid and nid.rsplit("/", 1)[0] not in u.nodes:
            errs.append(f"node {nid}: parent missing")
        for ref in ("rs_benchmark", "alias_of"):
            if n.get(ref) and n[ref] not in u.nodes:
                errs.append(f"node {nid}: {ref} {n[ref]} not a node")
        if n.get("anchor_family") and n["anchor_family"] not in u.families:
            errs.append(f"node {nid}: anchor_family {n['anchor_family']} not a family")
        if n.get("scored") and not n.get("mode"):
            errs.append(f"node {nid}: scored node needs mode")

    # Families: node exists, is scorable, not an alias; has exactly one CORE.
    for fid, f in u.families.items():
        node = u.nodes.get(f["node"])
        if node is None:
            errs.append(f"family {fid}: node {f['node']} missing")
        elif node.get("alias_of") or node.get("level") == "DIMENSION":
            errs.append(f"family {fid}: cannot attach to {node['level']}/alias node")
        if f.get("identity_basis") not in IDENTITY_BASES:
            errs.append(f"family {fid}: bad identity_basis")
        roles = [e["role"] for e in u.members(fid)]
        n_core = sum(r in ("CORE", "THEMATIC") for r in roles)
        if f.get("sentiment_only"):
            proxy = u.families.get(f.get("price_proxy_family"))
            if n_core or not proxy or proxy["node"] != f["node"]:
                errs.append(f"family {fid}: sentiment_only needs 0 core and a same-node price_proxy_family")
            if not set(roles) <= SENTIMENT_ROLES:
                errs.append(f"family {fid}: sentiment_only family has non-sentiment members")
        elif n_core != 1:
            errs.append(f"family {fid}: needs exactly 1 CORE/THEMATIC member, has {n_core}")

    # ETFs: role/direction/leverage coherent.
    for t, e in u.etfs.items():
        if e.get("family") not in u.families:
            errs.append(f"{t}: family {e.get('family')} missing")
        role, d, lev = e.get("role"), e.get("direction"), e.get("leverage")
        if role not in ROLES:
            errs.append(f"{t}: bad role {role}")
        if e.get("tier") not in TIERS:
            errs.append(f"{t}: bad tier {e.get('tier')}")
        if d not in ("LONG", "SHORT"):
            errs.append(f"{t}: bad direction {d}")
        if not isinstance(lev, (int, float)) or lev <= 0:
            errs.append(f"{t}: leverage must be positive number")
            continue
        if role == "LEVERAGED_BULL" and not (d == "LONG" and lev > 1):
            errs.append(f"{t}: LEVERAGED_BULL must be LONG with leverage > 1")
        if role == "LEVERAGED_BEAR" and not (d == "SHORT" and lev > 1):
            errs.append(f"{t}: LEVERAGED_BEAR must be SHORT with leverage > 1")
        if role == "INVERSE" and not (d == "SHORT" and lev == 1):
            errs.append(f"{t}: INVERSE must be SHORT with leverage 1")
        if role in PRICE_ROLES and not (d == "LONG" and lev == 1):
            errs.append(f"{t}: {role} must be unlevered LONG")
        if not isinstance(e.get("verified"), bool):
            errs.append(f"{t}: verified flag required")
    return errs


if __name__ == "__main__":
    u = load()
    for err in u.errors:
        print("ERROR", err)
    tiers: dict = {}
    for e in u.etfs.values():
        tiers[e["tier"]] = tiers.get(e["tier"], 0) + 1
    print(f"nodes={len(u.nodes)} families={len(u.families)} etfs={len(u.etfs)} tiers={tiers}")
    print(f"verified={sum(e['verified'] for e in u.etfs.values())}/{len(u.etfs)}")
    raise SystemExit(1 if u.errors else 0)
