import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from etf_temperature import engine as eg  # noqa: E402
from etf_temperature.sources import make_demo, parse_yahoo_chart  # noqa: E402
from etf_temperature.universe import load  # noqa: E402

IDX = pd.bdate_range("2020-01-01", periods=400)


class NormalisationTest(unittest.TestCase):
    def test_prank_has_no_lookahead(self):
        s = pd.Series(np.random.default_rng(0).normal(size=400), index=IDX)
        full = eg.prank(s)
        cut = eg.prank(s.iloc[:300])
        pd.testing.assert_series_equal(full.iloc[:300], cut)

    def test_prank_needs_min_history(self):
        s = pd.Series(range(400), index=IDX, dtype=float)
        r = eg.prank(s)
        self.assertTrue(r.iloc[: eg.MIN_PERIODS - 1].isna().all())
        self.assertEqual(r.iloc[-1], 100)  # new high every day

    def test_bands(self):
        self.assertEqual(eg.band(10), "EXTREME_COLD")
        self.assertEqual(eg.band(50), "NEUTRAL")
        self.assertEqual(eg.band(85), "EXTREME_HOT")
        self.assertIsNone(eg.band(None))


class FactorTest(unittest.TestCase):
    def test_breakout_is_hot_breakdown_is_cold(self):
        rng = np.random.default_rng(3)
        flat = 100 * np.cumprod(1 + rng.normal(0, 0.005, 340))
        up = pd.Series(np.r_[flat, flat[-1] * np.cumprod(np.full(60, 1.006))], index=IDX)
        dn = pd.Series(np.r_[flat, flat[-1] * np.cumprod(np.full(60, 0.994))], index=IDX)
        self.assertGreater(eg.trend_scores(up)["trend"].iloc[-1], 85)
        self.assertLess(eg.trend_scores(dn)["trend"].iloc[-1], 15)

    def test_steady_trend_regresses_toward_middle(self):
        # Known property (temperature-model §1.1): scores are relative to the asset's own
        # history, so a perfectly constant trend stops looking unusual.
        up = pd.Series(np.exp(np.linspace(0, 0.5, 400)), index=IDX)
        self.assertLess(eg.trend_scores(up)["trend"].iloc[-1], 85)

    def test_volume_is_directional(self):
        rng = np.random.default_rng(1)
        dv = pd.Series(1e8 * np.exp(rng.normal(0, 0.1, 400)), index=IDX)
        dv.iloc[-5:] *= 5  # volume spike
        p_up = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, 400)), index=IDX)
        p_up.iloc[-5:] = p_up.iloc[-6] * np.array([1.02, 1.04, 1.06, 1.08, 1.10])
        p_dn = p_up.copy()
        p_dn.iloc[-5:] = p_up.iloc[-6] * np.array([0.98, 0.96, 0.94, 0.92, 0.90])
        up, dn = eg.volume_scores(dv, p_up), eg.volume_scores(dv, p_dn)
        self.assertGreater(up["activity"].iloc[-1], 95)
        self.assertGreater(up["volume"].iloc[-1], 90)       # heavy volume + rally = hot
        self.assertLess(dn["volume"].iloc[-1], 10)          # heavy volume + selloff = cold
        self.assertEqual(up["activity"].iloc[-1], dn["activity"].iloc[-1])  # activity has no sign

    def test_bull_share_is_exposure_weighted(self):
        core = pd.Series(1e9, index=IDX)
        bull3 = pd.Series(1e8, index=IDX) * 3      # $100M of a 3x fund
        bear1 = pd.Series(3e8, index=IDX) * 1      # $300M of a -1x fund
        out = eg.bullbear_scores(bull3, bear1, core)
        self.assertAlmostEqual(out["bull_share_raw"].iloc[-1], 0.5)

    def test_lev_check(self):
        rng = np.random.default_rng(2)
        rc = pd.Series(rng.normal(0, 0.01, 400), index=IDX)
        self.assertTrue(eg.lev_check(3 * rc, rc, 3)["pass"])
        self.assertFalse(eg.lev_check(2 * rc, rc, 3)["pass"])     # wrong leverage in metadata
        self.assertFalse(eg.lev_check(-3 * rc, rc, 3)["pass"])    # wrong direction
        noise = pd.Series(rng.normal(0, 0.01, 400), index=IDX)
        self.assertFalse(eg.lev_check(noise, rc, 3)["pass"])      # wrong family


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.u = load()
        cls.e = eg.Engine(cls.u, make_demo(cls.u, years=3)).run()

    def test_scores_bounded(self):
        for nid, rec in self.e.node.items():
            t = rec["temperature"].dropna()
            self.assertTrue(((t >= 0) & (t <= 100)).all(), nid)

    def test_no_coverage_node_has_no_temperature(self):
        self.assertNotIn("EQUITY/US/SECTOR/INFORMATION_TECHNOLOGY/SEMICONDUCTORS/MEMORY", self.e.node)

    def test_leveraged_price_never_drives_trend(self):
        # Semiconductors' price must come from a core fund, never SOXL/SOXS.
        self.assertIn(self.e.node["EQUITY/US/SECTOR/INFORMATION_TECHNOLOGY/SEMICONDUCTORS"]["lead_core"], ("SOXX", "SMH"))

    def test_us_equity_has_breadth_from_sectors(self):
        rec = self.e.node["EQUITY/US"]
        self.assertIn("breadth", rec["series"])
        self.assertEqual(len(rec["basket"]), 11)

    def test_sentiment_only_family_feeds_silver(self):
        self.assertIn("bullbear", self.e.node["PRECIOUS_METALS/SILVER"]["series"])


class YahooParseTest(unittest.TestCase):
    def test_parse(self):
        payload = {"chart": {"result": [{"timestamp": [1759708800, 1759795200],
                   "indicators": {"quote": [{"open": [1, 2], "high": [1, 2], "low": [1, 2],
                                             "close": [10.0, 11.0], "volume": [100, 200]}],
                                  "adjclose": [{"adjclose": [9.5, 10.5]}]}}]}}
        df = parse_yahoo_chart(payload)
        self.assertEqual(list(df.columns), ["open", "high", "low", "close", "adj_close", "volume"])
        self.assertEqual(df["close"].iloc[-1], 11.0)
        self.assertEqual(df["adj_close"].iloc[-1], 10.5)


if __name__ == "__main__":
    unittest.main()
