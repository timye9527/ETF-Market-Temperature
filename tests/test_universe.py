import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from etf_temperature.universe import SENTIMENT_ROLES, load  # noqa: E402


class UniverseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.u = load()

    def test_no_validation_errors(self):
        self.assertEqual(self.u.errors, [])

    def test_every_bucket_is_populated(self):
        from etf_temperature.universe import BUCKETS
        seen = {self.u.bucket(t) for t in self.u.etfs}
        self.assertEqual(seen, set(BUCKETS))

    def test_single_stock_leverage_maps_to_stock_node(self):
        fam = self.u.families[self.u.etfs["NVDL"]["family"]]
        self.assertEqual(fam["node"], self.u.stocks["NVDA"]["node"])
        self.assertEqual(self.u.bucket("NVDL"), "LEVERAGED_SINGLE_STOCK")

    def test_memory_family_is_complete(self):
        roles = {e["ticker"]: e["role"] for e in self.u.members("MEMORY_DRAM")}
        self.assertEqual(roles, {"DRAM": "CORE", "DRAL": "LEVERAGED_BULL", "RAM": "LEVERAGED_BULL", "RAMZ": "LEVERAGED_BEAR"})

    def test_leveraged_pairs_share_family_benchmark(self):
        # A bull/bear member must sit in a family that also has a core price member,
        # otherwise its sentiment has no underlying to attach to.
        for t, e in self.u.etfs.items():
            if e["role"] in SENTIMENT_ROLES:
                fam = self.u.families[e["family"]]
                if fam.get("identity_basis") == "SINGLE_STOCK":
                    self.assertIn(fam["underlying_stock"], self.u.stocks, t)
                    continue
                if fam.get("sentiment_only"):
                    fam = self.u.families[fam["price_proxy_family"]]
                roles = {m["role"] for m in self.u.members(fam["id"])}
                self.assertTrue(roles & {"CORE", "THEMATIC"}, f"{t} has no price member")

    def test_resolve_semiconductor(self):
        r = self.u.resolve("SOXL")
        self.assertEqual(r["asset_class"], "EQUITY")
        self.assertEqual(r["region"], "US")
        self.assertEqual(r["sector"], "INFORMATION_TECHNOLOGY")
        self.assertEqual(r["industry"], "SEMICONDUCTORS")

    def test_resolve_theme_not_in_sector_tree(self):
        r = self.u.resolve("CIBR")
        self.assertEqual(r["theme"], "CYBERSECURITY")
        self.assertIsNone(r["sector"])

    def test_gold_miner_leverage_not_in_gold(self):
        # NUGT/DUST track the miners index, not the gold price.
        self.assertEqual(self.u.etfs["NUGT"]["family"], "GOLD_MINERS")
        self.assertEqual(self.u.resolve("NUGT")["asset_class"], "EQUITY")

    def test_smh_and_soxx_are_separate_families_same_node(self):
        f1 = self.u.etfs["SOXX"]["family"]
        f2 = self.u.etfs["SMH"]["family"]
        self.assertNotEqual(f1, f2)
        self.assertEqual(self.u.families[f1]["node"], self.u.families[f2]["node"])

    def test_no_coverage_node_has_no_family_v1(self):
        no_cov = {nid for nid, n in self.u.nodes.items() if n.get("status") == "NO_COVERAGE"}
        attached = {f["node"] for f in self.u.families.values()}
        self.assertFalse(no_cov & attached)


if __name__ == "__main__":
    unittest.main()
