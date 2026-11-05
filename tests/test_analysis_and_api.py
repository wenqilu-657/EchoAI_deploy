"""
Automated unit & integration test suite for EchoAI Emerging Artist Discovery.
Run with: python -m unittest discover tests
"""

import unittest
from fastapi.testclient import TestClient
import backend.analysis as an
from api.app import app


class TestAnalysisBackend(unittest.TestCase):
    def test_thresholds(self):
        t = an.thresholds()
        self.assertIn("recent_cutoff", t)
        self.assertIn("growth_cutoff", t)
        self.assertIn("n_scored", t)
        self.assertGreater(t["n_scored"], 0)
        self.assertGreater(t["recent_cutoff"], 0)

    def test_shortlist_structure_and_sorting(self):
        df = an.shortlist()
        self.assertGreater(len(df), 0, "Default shortlist should have qualified artists")
        self.assertTrue(df.growth.is_monotonic_decreasing, "Shortlist must be sorted by growth DESC")
        
        required_cols = [
            "artist_id", "artist_mbid", "name", "country", "first_release_date",
            "baseline", "recent", "net_listeners", "growth", "momentum_score",
            "stickiness", "retention_months", "track_dependency", "soundalike_name"
        ]
        for col in required_cols:
            self.assertIn(col, df.columns, f"Missing required column: {col}")

    def test_artist_profile(self):
        df = an.shortlist()
        top_id = int(df.iloc[0].artist_id)
        prof = an.artist_profile(top_id)
        self.assertEqual(len(prof), 1)
        row = prof.iloc[0]
        self.assertGreater(row.recent, 0)
        self.assertGreaterEqual(row.stickiness, 1.0)
        self.assertGreaterEqual(row.retention_months, 1.0)
        self.assertTrue(0.0 <= row.track_dependency <= 1.0)

    def test_artist_trend(self):
        df = an.shortlist()
        top_id = int(df.iloc[0].artist_id)
        trend = an.artist_trend(top_id)
        self.assertEqual(len(trend), 6, "Must contain exactly 6 monthly data points (Mar-Aug 2026)")
        self.assertEqual(list(trend.month), [202603, 202604, 202605, 202606, 202607, 202608])

    def test_fans_also_play(self):
        df = an.shortlist()
        top_id = int(df.iloc[0].artist_id)
        fans = an.fans_also_play(top_id, n=5)
        if len(fans) > 0:
            self.assertTrue((fans.artist_id != top_id).all())
            self.assertTrue(fans.share_of_fans.between(0, 1).all())

    def test_seed_options(self):
        seeds = an.seed_options()
        self.assertGreater(len(seeds), 0)
        self.assertIn("BTS", seeds.name.values)


class TestFastAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_root_serves_html(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        self.assertIn("EchoAI", res.text)
        self.assertIn("Editorial Summary", res.text)
        self.assertIn("Data & Cleaning", res.text)

    def test_api_options(self):
        res = self.client.get("/api/options")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("genres", data)
        self.assertIn("countries", data)
        self.assertIn("seeds", data)
        self.assertIn("defaults", data)
        self.assertIn("Unknown", data["countries"])

    def test_api_shortlist_defaults(self):
        res = self.client.get("/api/shortlist")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("thresholds", data)
        self.assertIn("artists", data)
        self.assertGreater(len(data["artists"]), 0)

    def test_api_shortlist_seed_filter(self):
        # BTS artist_id = 1025840
        res = self.client.get("/api/shortlist?seed_id=1025840")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        for artist in data["artists"]:
            self.assertEqual(artist["soundalike_id"], 1025840)

    def test_api_artist_endpoints(self):
        res_list = self.client.get("/api/shortlist")
        top_id = res_list.json()["artists"][0]["artist_id"]

        # Profile
        res_prof = self.client.get(f"/api/artist/{top_id}")
        self.assertEqual(res_prof.status_code, 200)
        self.assertEqual(res_prof.json()["artist_id"], top_id)
        self.assertIn("stickiness", res_prof.json())
        self.assertIn("retention_months", res_prof.json())

        # Trend
        res_trend = self.client.get(f"/api/artist/{top_id}/trend")
        self.assertEqual(res_trend.status_code, 200)
        self.assertEqual(len(res_trend.json()), 6)

        # Fans
        res_fans = self.client.get(f"/api/artist/{top_id}/fans?n=5")
        self.assertEqual(res_fans.status_code, 200)
        self.assertIsInstance(res_fans.json(), list)

        # Tracks
        res_tracks = self.client.get(f"/api/artist/{top_id}/tracks?n=5")
        self.assertEqual(res_tracks.status_code, 200)
        self.assertIsInstance(res_tracks.json(), list)


if __name__ == "__main__":
    unittest.main()
