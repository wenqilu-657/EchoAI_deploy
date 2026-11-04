# ADR 0001: Multi-Factor Emerging Artist Definition & Baseline Activity Gate

## Context
In the Phase 2 specification, an artist qualified as "emerging" based purely on a 3-month baseline listener average (`(Mar+Apr+May)/3 >= 5`) and 90th percentile percentage growth (`(recent - baseline) / baseline >= 0.2807`). During Module 9 audits (AUDIT-02), we found that 53 of 1,131 artists qualified via debut spikes with zero scrobbles in early baseline months (e.g. 0, 0, 15 listeners in March–May), artificially inflating growth to +1000%+ and crowding out genuine steady risers.

## Decision
We define an **Emerging Artist** using a **Multi-Factor Momentum Score** that balances relative growth percentage with absolute net listener gains (`net_listeners = recent - baseline`), and enforces an active listening gate requiring listeners in at least two of the three baseline months. Furthermore, we compute **Stickiness Ratio** (`listens / listeners`), **Track Dependency** (`top_track_share`), and **Audience Retention** to distinguish high-devotion catalog artists from one-hit viral anomalies.

## Consequences
- Artists with two zero-listener baseline months are categorized as "Fresh Debuts" rather than ranked as high-growth emerging acts.
- Growth metrics reflect sustainable momentum rather than small-denominator mathematical artifacts.
- Playlist curators gain actionable insights into repeat listening intensity and catalog depth.
