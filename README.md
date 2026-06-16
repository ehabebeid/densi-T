# Densi-T

Densi-T explores the relationship between transit service and neighborhood density across the MBTA network, using publicly available schedule, Census, and jobs data.

**Service vs. density** plots every station by how often trains run at peak against the density of residents and jobs within the station area. The idea is that denser neighborhoods generally warrant more frequent service, and frequent service tends to attract density over time. But not every station fits that pattern. Stations above the trendline are relatively dense for their service level; stations below are relatively underdeveloped. A residuals table at the bottom ranks the biggest mismatches in each direction.

**Density change** shows which station areas have added or lost population and jobs since 2010, ranked by absolute change. This view is less about service and more about where growth has and hasn't happened around transit.

Both views let you choose the density metric — combined population and jobs, population only, or jobs only. Rapid Transit and Commuter Rail are shown separately. No bus stop view for now.

## How it works

**Station areas** are straight-line buffers around each station — 0.25, 0.5, or 1 mile radius, selectable in the sidebar. No network routing, just crow-flies distance.

**Service frequency** is the highest directional trips-per-hour across AM peak (7–9am), midday (10am–2pm), and PM peak (4–6pm), drawn from MBTA GTFS schedule data (March 2026). For each period, the busiest direction is used.

**Density** is residents plus jobs per acre within the station buffer. Population comes from Census ACS 5-year estimates (block groups) for 2024, and from the 2010 decennial Census (blocks) for the historic comparison; jobs come from LEHD LODES 2023 and 2011. Population and jobs are area-weighted when a census unit straddles a buffer boundary — a block that's 40% inside the buffer contributes 40% of its count, rather than all-or-nothing.

Downtown (broadly defined) and Back Bay stations can be filtered out since they can be outliers both in frequency and density.

## Limitations

**Frequency only.** Service is captured by frequency only, as opposed to also measuring capacity, ridership, speed, or reliability.

**No nearby-station adjustment.** A station that seems underserved might sit right next to one with better frequency. This analysis doesn't account for that.

**Crow-flies buffers.** Station areas are circles, not walkshed polygons. This will overcount the density of station areas that have poor street network accessibility.

**Density uses full circle area.** Density is divided by the total buffer area, including any water, parks, or other gaps. A waterfront station might look less dense as a result.

**Fixed service snapshot.** Service levels are from March 2026 GTFS and don't reflect historic schedules. When comparing against 2010 density data, you're looking at current service, not what was running back then. The feed may also include some temporary diversions.

**Density skews toward commutes.** Population plus jobs per acre is a reasonable proxy for overall economic activity, but it doesn't properly weigh all types of trip-generating amenities.

**Data vintage mismatch.** The "recent" numbers combine 2024 Census population estimates with 2023 LODES jobs data because that's what is most recently available. The historic comparison uses 2010 decennial population and 2011 LODES jobs data, because of issues with 2010 data.
