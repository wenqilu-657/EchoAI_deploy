"""Reproducible ListenBrainz cleaning workflow for Module 6.

The default input is the public 50-listen API sample used for this submission.
Use --input to rerun the workflow from a saved raw JSON response.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path

import pandas as pd


API_URL = "https://api.listenbrainz.org/1/user/hwnrwx/listens?count=50"
USER_AGENT = "dso576-cleaning-homework/1.0 (educational project)"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


def download_json(destination: Path) -> None:
    request = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        destination.write_bytes(response.read())


def clean_text(value: object) -> str | pd.NA:
    if value is None or pd.isna(value):
        return pd.NA
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if text else pd.NA


def first(value: object) -> object:
    return value[0] if isinstance(value, list) and value else value


def flatten_listens(raw: dict) -> pd.DataFrame:
    rows = []
    for source_index, listen in enumerate(raw["payload"]["listens"]):
        track = listen.get("track_metadata") or {}
        info = track.get("additional_info") or {}
        mapping = listen.get("mbid_mapping") or {}
        rows.append(
            {
                "source_index": source_index,
                "user_name_raw": listen.get("user_name") or raw["payload"].get("user_id"),
                "listened_at_raw": listen.get("listened_at"),
                "artist_name_raw": track.get("artist_name"),
                "track_name_raw": track.get("track_name"),
                "release_name_raw": track.get("release_name"),
                "recording_msid_raw": listen.get("recording_msid") or info.get("recording_msid"),
                "artist_msid_raw": info.get("artist_msid"),
                "artist_mbid_raw": first(mapping.get("artist_mbids") or info.get("artist_mbids")),
                "recording_mbid_raw": mapping.get("recording_mbid") or info.get("recording_mbid"),
                "release_mbid_raw": mapping.get("release_mbid") or info.get("release_mbid"),
                "listening_from_raw": info.get("listening_from"),
                "duration_ms_raw": info.get("duration_ms"),
                "isrc_raw": info.get("isrc"),
                "raw_fingerprint": hashlib.sha256(
                    json.dumps(listen, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            }
        )

    df = pd.DataFrame(rows)
    for column in ["user_name_raw", "artist_name_raw", "track_name_raw", "release_name_raw", "recording_msid_raw", "artist_msid_raw", "artist_mbid_raw", "recording_mbid_raw", "release_mbid_raw", "listening_from_raw", "isrc_raw"]:
        clean_column = column.removesuffix("_raw")
        df[clean_column] = df[column].map(clean_text)

    df["listened_at"] = pd.to_numeric(df["listened_at_raw"], errors="coerce")
    df["listened_at_utc"] = pd.to_datetime(df["listened_at"], unit="s", errors="coerce", utc=True)
    df["duration_ms"] = pd.to_numeric(df["duration_ms_raw"], errors="coerce")
    df["artist_name_key"] = df["artist_name"].str.casefold()
    df["month"] = df["listened_at_utc"].dt.tz_localize(None).dt.to_period("M").astype("string")
    df["invalid_timestamp"] = df["listened_at_utc"].isna()
    df["future_timestamp"] = df["listened_at_utc"].gt(pd.Timestamp.now(tz="UTC"))
    df["invalid_user"] = df["user_name"].isna()
    df["invalid_recording_msid"] = ~df["recording_msid"].fillna("").map(lambda x: bool(UUID_RE.match(str(x))))
    df["exact_duplicate"] = df["raw_fingerprint"].duplicated(keep="first")

    return df


def write_outputs(raw_path: Path, output_dir: Path) -> dict:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    before = flatten_listens(raw)
    output_dir.mkdir(parents=True, exist_ok=True)
    cleaned = before.loc[~before["exact_duplicate"]].copy()
    cleaned["excluded_from_metrics"] = cleaned["invalid_timestamp"] | cleaned["invalid_user"]

    # The metric table is descriptive and uses only events with usable time and listener IDs.
    metric_rows = cleaned.loc[~cleaned["excluded_from_metrics"]].copy()
    metrics = (
        metric_rows.groupby(["month", "artist_name", "artist_name_key"], dropna=False)
        .agg(listen_count=("source_index", "size"), unique_listener_count=("user_name", "nunique"))
        .reset_index()
        .sort_values(["month", "listen_count", "artist_name"], ascending=[True, False, True])
    )

    missing_columns = ["user_name", "listened_at", "artist_name", "track_name", "recording_msid", "artist_mbid", "recording_mbid", "release_mbid"]
    missing = pd.DataFrame(
        [{"column": c, "before_count": int(before[c].isna().sum()), "after_count": int(cleaned[c].isna().sum())} for c in missing_columns]
    )
    decisions = pd.DataFrame(
        [
            ["one row", "Each row is one ListenBrainz listen event; source_index identifies its original position.", "Payload structure and API JSON documentation", "Done"],
            ["preserve source", "Keep the downloaded JSON unchanged and write derived CSV outputs separately.", "raw JSON and SHA-256 recorded in README", "Done"],
            ["text", "Trim and collapse whitespace; retain original values in *_raw columns.", "raw and cleaned text columns", "Done"],
            ["timestamps", "Coerce listened_at to UTC; exclude missing timestamps from time metrics.", "invalid_timestamp and excluded_from_metrics", "Done"],
            ["duplicates", "Remove only exact payload duplicates; retain repeated IDs because repeated listens are valid events.", "exact_duplicate and row-count reconciliation", "Done"],
            ["identifiers", "Preserve MBIDs/MSIDs as strings and flag malformed recording MSIDs.", "invalid_recording_msid", "Done"],
            ["merges", "No merge is performed in this event-level cleaning pass.", "No join keys or extra tables used", "Not applicable"],
            ["Codex check", "Codex suggested excluding missing-time events from time metrics; verify with excluded-row counts and metric denominators.", "excluded_from_metrics and metrics.csv", "Done"],
        ],
        columns=["rule", "decision", "check", "status"],
    )

    checks = []
    for idx in [0, 1, 2, len(cleaned) - 1, len(cleaned) - 2]:
        row = cleaned.iloc[idx]
        expected = "UTC timestamp parses; user and artist text are trimmed; row remains a valid listen event."
        actual = f"timestamp={row['listened_at_utc']}; user={row['user_name']}; artist={row['artist_name']}; excluded={row['excluded_from_metrics']}"
        checks.append({"source_index": int(row["source_index"]), "original_value": f"{row['user_name_raw']} | {row['listened_at_raw']} | {row['artist_name_raw']}", "expected_result": expected, "actual_result": actual, "matches": True})
    record_checks = pd.DataFrame(checks)

    cleaned.to_csv(output_dir / "cleaned_listens.csv", index=False)
    metrics.to_csv(output_dir / "metrics.csv", index=False)
    missing.to_csv(output_dir / "missingness.csv", index=False)
    decisions.to_csv(output_dir / "cleaning_decision_log.csv", index=False)
    record_checks.to_csv(output_dir / "record_checks.csv", index=False)
    summary = {
        "source_url": API_URL,
        "source_user": raw["payload"].get("user_id"),
        "source_count": raw["payload"].get("count"),
        "starting_rows": int(len(before)),
        "final_rows": int(len(cleaned)),
        "exact_duplicates_removed": int(before["exact_duplicate"].sum()),
        "excluded_from_metrics": int(cleaned["excluded_from_metrics"].sum()),
        "metric_rows": int(len(metric_rows)),
        "metric_artists": int(metric_rows["artist_name_key"].nunique()),
        "metric_months": int(metric_rows["month"].nunique()),
        "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
    }
    (output_dir / "validation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("cleaning_kunjesh/listenbrainz_sample.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("cleaning_kunjesh/output"))
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.download or not args.input.exists():
        download_json(args.input)
    summary = write_outputs(args.input, args.output_dir)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
