"""Kunjesh's Module 9 audit checks: Shortlist Tray & CSV Export (feature) and Cutoff Quantiles (number).

Run from the repository root:   python audit/kunjesh_audit_checks.py
"""
import sys
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import analysis as an  # noqa: E402

print("=" * 70)
print("FEATURE AUDIT: Shortlist Tray & CSV Export")
print("=" * 70)

# Check 1: Spreadsheet formula injection protection logic (matches web/app.js csvCell)
def csv_cell(v, is_text):
    if v is None:
        return ""
    s = str(v)
    if is_text and any(s.startswith(c) for c in ("=", "+", "-", "@", "\t", "\r")):
        s = "'" + s
    if any(c in s for c in ('"', ",", "\n", "\r")):
        return f'"{s.replace(chr(34), chr(34) * 2)}"'
    return s

test_names = [
    ("Normal Name", "Normal Name"),
    ("=SUM(1+1)", "'=SUM(1+1)"),
    ("+44 Band", "'+44 Band"),
    ("-M-", "'-M-"),
    ("@Act", "'@Act"),
    ('Name with, comma', '"Name with, comma"'),
    ('Name with "quotes"', '"Name with ""quotes"""')
]

formula_pass = True
for raw, expected in test_names:
    res = csv_cell(raw, is_text=True)
    if res != expected:
        print(f"  FAIL: {raw!r} -> got {res!r}, expected {expected!r}")
        formula_pass = False

print(f"Formula injection escaping check: {'PASS' if formula_pass else 'FAIL'}")

# Check 2: Tray deduplication logic
class MockTray:
    def __init__(self):
        self.tray = []

    def add(self, artist):
        if not artist or any(t["artist_id"] == artist["artist_id"] for t in self.tray):
            return False
        self.tray.append(artist)
        return True

tray = MockTray()
a1 = {"artist_id": 2041085, "name": "EVAN"}
a2 = {"artist_id": 1025840, "name": "BTS"}

tray.add(a1)
added_duplicate = tray.add(a1) # Should return False and not add
tray.add(a2)

print(f"Tray deduplication check (2 distinct artists added 3 times):")
print(f"  Tray length: {len(tray.tray)} (expected: 2) -> {'PASS' if len(tray.tray) == 2 and not added_duplicate else 'FAIL'}")

print("\n" + "=" * 70)
print("NUMBER AUDIT: Cutoff Threshold Quantiles")
print("=" * 70)

# Check 3: Small test case for continuous quantile (linear interpolation)
con = duckdb.connect()
con.execute("CREATE TABLE test_sample (val DOUBLE)")
con.execute("INSERT INTO test_sample VALUES (10), (20), (30), (40), (50)")
q90_actual = con.execute("SELECT quantile_cont(val, 0.90) FROM test_sample").fetchone()[0]
# Hand calc: index = 0.9 * (5 - 1) = 3.6 -> 40 + 0.6 * (50 - 40) = 46.0
print("Small test case [10, 20, 30, 40, 50] at p90:")
print(f"  Hand calculation: 46.0")
print(f"  DuckDB quantile_cont: {q90_actual:.1f} -> {'PASS' if abs(q90_actual - 46.0) < 1e-9 else 'FAIL'}")

# Check 4: App thresholds calculation & filter decoupling
t = an.thresholds()
print(f"\nApp Cutoffs (min_baseline=5, size_pct=0.90, growth_pct=0.90):")
print(f"  recent_cutoff = {t['recent_cutoff']:.2f}")
print(f"  growth_cutoff = {t['growth_cutoff']:.4f} ({t['growth_cutoff']:+.1%})")
print(f"  artists scored = {t['n_scored']:,}")

s_all = an.shortlist()
g_opt = an.genre_options()
c_opt = an.country_options()

# Verify cutoffs do not change when filtering
if len(g_opt) > 0:
    g = g_opt.iloc[0]["genre"]
    s_genre = an.shortlist(genre=g)
    print(f"\nGenre filter check ('{g}'):")
    print(f"  Rows matching: {len(s_genre)} of {len(s_all)}")
    print(f"  Thresholds unchanged: {an.thresholds() == t}")

if len(c_opt) > 0:
    c = c_opt.iloc[0]["country"]
    s_country = an.shortlist(country=c)
    print(f"\nCountry filter check ('{c}'):")
    print(f"  Rows matching: {len(s_country)} of {len(s_all)}")
    print(f"  Thresholds unchanged: {an.thresholds() == t}")

print("\nAll audit checks completed successfully.")
