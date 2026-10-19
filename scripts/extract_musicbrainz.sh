#!/usr/bin/env bash
# Stream the pinned MusicBrainz core dump (CC0) and keep only the tables we need, unchanged, in data/raw/mb/.
# Run from the repo root:  bash scripts/extract_musicbrainz.sh
# Big download (multi-GB, streamed, not stored); expect 10-30 min. Safe to re-run.
set -euo pipefail
VERSION="20260930-002222"   # pinned dump version, so results are reproducible
BASE="https://data.metabrainz.org/pub/musicbrainz/data/fullexport/$VERSION"
OUT="data/raw/mb"
mkdir -p "$OUT"

# Official checksums for the exact version we use (kept for the README / checklist item 3).
curl -fsSL "$BASE/MD5SUMS" -o "$OUT/MD5SUMS"

# Only extract the members we need; tar still reads the whole stream but writes just these.
curl -fL --retry 5 --retry-delay 10 "$BASE/mbdump.tar.bz2" \
  | tar -xjf - -C "$OUT" mbdump/artist mbdump/artist_type mbdump/gender mbdump/area

cat > "$OUT/MANIFEST.txt" <<EOM
source: $BASE/mbdump.tar.bz2  (MusicBrainz core dump, CC0)
dump version: $VERSION
downloaded: $(date +%F)
kept tables: artist, artist_type, gender, area (tab-separated, no header, \\N = NULL)
EOM
echo "--- extracted:"; wc -l "$OUT"/mbdump/artist "$OUT"/mbdump/artist_type "$OUT"/mbdump/gender "$OUT"/mbdump/area
shasum -a 256 "$OUT"/mbdump/* | tee "$OUT/EXTRACTED_SHA256.txt"
