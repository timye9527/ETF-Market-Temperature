import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from etf_temperature import engine_v2 as v2  # noqa: E402
from etf_temperature.select import restrict, select  # noqa: E402
from etf_temperature.sources import make_demo  # noqa: E402
from etf_temperature.universe import load  # noqa: E402

IDX = pd.bdate_range("2015-01-01", periods=1600)


class TrendRelativeTest(unittest.TestCase):
    def test_steady_trend_is_not_hot(self):
        # The Owner's objection: a strong, steady uptrend must not read "ever hotter".
        rng = np.random.default_rng(0)
        p = pd.Series(np.exp(np.cumsum(0.0012 + rng.normal(0, 0.008, 1600))), index=IDX)
        z = v2.regression(np.log(p), 252)["z"].dropna()
        self.assertLess(abs(z.tail(250).mean()), 0.6)
        stretch = v2.mean_of([v2.pct5(v2.regression(np.log(p), w)["z"]) for w in (126, 252)])
        self.assertTrue(30 < stretch.tail(250).mean() < 70)

    def test_acceleration_beyond_trend_is_hot(self):
        rng = np.random.default_rng(1)
        r = 0.0008 + rng.normal(0, 0.008, 1600)
        r[-30:] += 0.012  # parabolic last six weeks
        p = pd.Series(np.exp(np.cumsum(r)), index=IDX)
        self.assertGreater(v2.pct5(v2.regression(np.log(p), 252)["z"]).iloc[-1], 95)

    def test_regression_matches_numpy_polyfit(self):
        rng = np.random.default_rng(2)
        lp = pd.Series(np.cumsum(rng.normal(0, 0.01, 400)), index=IDX[:400])
        g = v2.regression(lp, 126)
        y = lp.iloc[-126:].to_numpy()
        slope, icpt = np.polyfit(np.arange(126), y, 1)
        self.assertAlmostEqual(g["slope"].iloc[-1], slope, places=8)
        resid = y - (icpt + slope * np.arange(126))
        self.assertAlmostEqual(g["z"].iloc[-1], resid[-1] / np.sqrt((resid ** 2).sum() / 124), places=6)

    def test_bands_have_fixed_meaning(self):
        self.assertEqual(v2.band(3), "EXTREME_COLD")
        self.assertEqual(v2.band(50), "NEUTRAL")
        self.assertEqual(v2.band(96), "EXTREME_HOT")


class ActionTest(unittest.TestCase):
    def test_cyclical_confirmed_extreme_hot_trims(self):
        self.assertEqual(v2.reference_action("CYCLICAL", "EXTREME_HOT", "HOT", 95), "TRIM")

    def test_growth_never_trims(self):
        self.assertEqual(v2.reference_action("STRUCTURAL_GROWTH", "EXTREME_HOT", "HOT", 95), "NO_CHASE")

    def test_falling_knife_waits(self):
        self.assertEqual(v2.reference_action("CYCLICAL", "EXTREME_COLD", "COLD", 3), "WAIT")

    def test_value_trap_never_buys(self):
        self.assertEqual(v2.reference_action("SECULAR_DECLINE", "COLD", None, 30), "HOLD")
        self.assertEqual(v2.reference_action("INSTRUMENT", "COLD", None, 30), "NA")


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.u = load()
        cls.bars = make_demo(cls.u, years=6)
        cls.sel = select(cls.u, cls.bars)
        cls.e = v2.EngineV2(restrict(cls.u, cls.sel.selected), cls.bars).run()

    def test_temperatures_bounded(self):
        for nid, rec in self.e.node.items():
            t = rec["temp"].dropna()
            self.assertTrue(((t >= 0) & (t <= 100)).all(), nid)

    def test_leverage_is_its_own_block(self):
        lev = self.e.node["EQUITY/US/SECTOR/INFORMATION_TECHNOLOGY/SEMICONDUCTORS"]["lev"]
        self.assertEqual(set(lev), {"index", "single"})  # SOXL/SOXS and NVDL/AMDL… kept apart

    def test_memory_node_scored(self):
        self.assertIn("EQUITY/US/SECTOR/INFORMATION_TECHNOLOGY/SEMICONDUCTORS/MEMORY", self.e.node)

    def test_eligibility_has_all_tests(self):
        el = self.e.eligibility("EQUITY/US/SECTOR/ENERGY")
        self.assertEqual(set(el["tests"]), {"T1", "T2", "T3", "T4", "T5"})
        self.assertEqual(el["auto_class"] if el["tests"]["T1"]["pass"] and el["tests"]["T4"]["pass"] else "CYCLICAL", "CYCLICAL")


class SelectionTest(unittest.TestCase):
    def test_top_n_and_leverage_block(self):
        u = load()
        idx = pd.bdate_range("2026-01-01", periods=80)
        rng = np.random.default_rng(3)
        bars = {}
        for i, t in enumerate(u.etfs):
            dv = 1e9 / (i + 1)  # earlier tickers are more liquid
            px = pd.Series(50 * np.exp(np.cumsum(rng.normal(0, 0.01, 80))), index=idx)
            bars[t] = pd.DataFrame({"close": px, "adj_close": px, "volume": dv / px, "open": px, "high": px, "low": px})
        s = select(u, bars, top_n=3)
        tab = s.table.set_index("ticker")
        top = tab[tab["reason"] == "TOP_N"].groupby("bucket").size()
        self.assertTrue((top <= 3).all())
        self.assertIn("SOXS", s.selected)  # pair/leverage block keeps both sides of a covered node


class BackfillTest(unittest.TestCase):
    def test_young_fund_is_spliced_onto_constituents(self):
        u = load()
        bars = make_demo(u, years=3)
        for col in ("close", "adj_close", "volume"):
            bars["DRAM"].loc[: "2026-04-01", col] = np.nan
        e = v2.EngineV2(restrict(u, set(u.etfs)), bars)
        p, core, first = e._family_price("MEMORY_DRAM")
        self.assertEqual(core, "DRAM")
        self.assertEqual(first, pd.Timestamp("2026-04-02"))
        self.assertTrue(p.loc[:"2026-04-01"].notna().all())
        self.assertAlmostEqual(p.loc[first], bars["DRAM"]["adj_close"].loc[first])


if __name__ == "__main__":
    unittest.main()
