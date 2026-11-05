# Emerging Artist Discovery (EchoAI Domain Model)

Defines canonical concepts and terminology for identifying high-momentum upcoming musical acts from ListenBrainz scrobbles and MusicBrainz metadata for editorial playlist curation.

## Core Concepts

**Emerging Artist**:
An active musical act with an established baseline audience (active in $\ge 2$ baseline months) whose recent audience remains below mainstream scale, evaluated using a Multi-Factor Momentum Score that balances relative growth percentage with absolute net listener gains.
_Avoid_: Upcoming artist, breakout star, small act

**Momentum Score**:
A composite scoring index combining relative growth velocity (`growth`) with absolute audience expansion (`net_listeners`), weighted to reward sustainable breakout trajectory over low-denominator percentage inflation.
_Avoid_: Popularity index, trend score, viral rank

**Net Listeners Gained (`net_listeners`)**:
The absolute increase in average monthly distinct listeners between baseline and recent periods: `recent - baseline`.
_Avoid_: Listener delta, raw gain, growth count

**Baseline Listeners**:
The arithmetic mean of monthly distinct human listeners scrobbling the artist over the first three calendar months (March–May 2026). Requires listening activity in at least two of the three months.
_Avoid_: Prior listeners, old audience, historic listeners

**Recent Listeners**:
The arithmetic mean of monthly distinct human listeners scrobbling the artist over the last three calendar months (June–August 2026).
_Avoid_: Current streams, active plays, new audience

**Growth Velocity**:
The proportional rate of listener change between recent and baseline listening periods: `(recent - baseline) / baseline`.
_Avoid_: Percentage increase, stream growth, popularity delta

**Listener Stickiness Ratio**:
The ratio of total scrobbles to distinct listeners for an artist (`listens / listeners`), measuring repeat listening intensity and superfan devotion.
_Avoid_: Plays per user, replay rate, engagement depth

**Track Dependency (Top Track Share)**:
The proportion of an artist's total listeners accounted for by their single most popular recording: `top_track_listeners / total_artist_listeners`. A high value ($\ge 90\%$) indicates a single-track viral anomaly; lower values indicate broad catalog discovery.
_Avoid_: Track concentration, one-hit ratio, viral bias

**Audience Retention**:
The average number of distinct calendar months in the 6-month window during which an artist's listeners active in the baseline period returned to scrobble the artist (`avg_months_active`).
_Avoid_: Churn rate, repeat audience, loyalty score

**Taste Community**:
A cluster of established mainstream artists whose listeners exhibit significant co-listening overlap with the target emerging artist.
_Avoid_: Genre bucket, demographic segment, target demographic

**Fan Overlap (`share_of_fans`)**:
The proportion of an emerging artist's distinct non-bot listeners who also scrobbled a given established benchmark artist during the observation window.
_Avoid_: Shared affinity, correlation, mutual fanbase

**Catalogued Debut**:
The earliest release group date recorded for an artist in the MusicBrainz database.
_Avoid_: Artist debut, release year, birth date

**Debut Discrepancy (AUDIT-01)**:
An occurrence where an artist logs active scrobbles in ListenBrainz months before their earliest catalogued release date in MusicBrainz.
_Avoid_: Bad date, future release, missing album

**Bot Account**:
A pseudonymous scrobbler account logging more than 500 scrobbles on any single UTC calendar day, excluded to protect small-artist metrics from automated distortion.
_Avoid_: Spammer, fake user, heavy streamer
