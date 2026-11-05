"""FastAPI Application for Emerging Artist Discovery (v2.0 - Hybrid Curation Suite).
Translates HTTP requests into backend/analysis.py calls.
"""
import datetime
import json
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import analysis as an  # noqa: E402

app = FastAPI(title="Emerging Artist Discovery API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def rows(df):
    """DataFrame -> list of dicts: NaN -> null, dates -> 'YYYY-MM-DD'."""
    df = df.copy()
    for c in df.columns:
        if str(df[c].dtype).startswith("datetime") or str(df[c].dtype) == "object":
            try:
                if hasattr(df[c], "dt"):
                    df[c] = df[c].dt.strftime("%Y-%m-%d")
            except Exception:
                pass
    return json.loads(df.to_json(orient="records", double_precision=15))


@app.get("/api/options")
def options():
    """Available genres, countries, seed established artists, and parameter defaults."""
    return {
        "genres": an.genre_options().genre.tolist(),
        "countries": an.country_options().country.tolist(),
        "seeds": rows(an.seed_options()),
        "defaults": an.DEFAULTS,
    }


@app.get("/api/shortlist")
def shortlist(
    min_release: str = Query(an.DEFAULTS["min_release"], pattern=r"^\d{4}-\d{2}-\d{2}$"),
    min_baseline: int = Query(an.DEFAULTS["min_baseline"], ge=1, le=50),
    size_pct: float = Query(an.DEFAULTS["size_pct"], ge=0.5, le=0.99),
    growth_pct: float = Query(an.DEFAULTS["growth_pct"], ge=0.5, le=0.99),
    genre: Optional[str] = None,
    country: Optional[str] = None,
    preset: Optional[str] = None,
    seed_id: Optional[int] = None,
    velocity: Optional[str] = None,
    size_tier: Optional[str] = None,
    search: Optional[str] = None,
    scope: str = Query("emerging", pattern=r"^(emerging|all)$"),
    status: Optional[str] = Query(None, pattern=r"^(emerging|established|candidate)$"),
    sort_by: Optional[str] = Query("growth_desc", pattern=r"^(growth_desc|listeners_desc|listeners_asc|name_asc)$"),
):
    """Artists meeting discovery criteria. scope='emerging' returns the qualified shortlist; scope='all' returns the full catalog."""
    try:
        datetime.date.fromisoformat(min_release)
    except ValueError:
        raise HTTPException(422, "min_release must be a valid ISO date, YYYY-MM-DD")

    return {
        "thresholds": an.thresholds(min_baseline, size_pct, growth_pct),
        "total_artists": an.thresholds(min_baseline, size_pct, growth_pct)["n_scored"],
        "artists": rows(
            an.shortlist(
                min_release=min_release,
                min_baseline=min_baseline,
                size_pct=size_pct,
                growth_pct=growth_pct,
                genre=genre or None,
                country=country or None,
                preset=preset or None,
                seed_id=seed_id,
                velocity=velocity or None,
                size_tier=size_tier or None,
                search=search or None,
                scope=scope,
                status=status or None,
                sort_by=sort_by or "growth_desc",
            )
        ),
    }


@app.get("/api/artist/{artist_id}")
def artist(artist_id: int):
    """Detailed profile metrics for a specific artist."""
    r = rows(an.artist_profile(artist_id))
    if not r:
        raise HTTPException(404, f"Artist ID {artist_id} not found")
    return r[0]


@app.get("/api/artist/{artist_id}/trend")
def trend(artist_id: int):
    """6-month monthly listeners (Mar–Aug 2026)."""
    return rows(an.artist_trend(artist_id))


@app.get("/api/artist/{artist_id}/fans")
def fans(artist_id: int, n: int = Query(10, ge=1, le=50)):
    """Taste community: established acts co-listened to by this artist's fans."""
    return rows(an.fans_also_play(artist_id, n))


@app.get("/api/artist/{artist_id}/tracks")
def tracks(artist_id: int, n: int = Query(5, ge=1, le=50)):
    """Top recordings ranked by recent listener momentum."""
    return rows(an.top_tracks(artist_id, n))


web_dir = ROOT / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
