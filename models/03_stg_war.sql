-- stg_war
-- Grain: one row per MLBAM id (mlb_ID) with any Baseball-Reference WAR season.
-- Purpose: career WAR through the 2026 season = batting WAR + pitching WAR. Both tables
-- carry a `WAR` column per player-season-stint; pitchers' hitting is in war_bat, so the
-- sum is Baseball-Reference's total WAR. mlb_ID is null only on pre-1950 rows.
create or replace view stg_war as
with seasons as (
    select cast(mlb_ID as bigint) as mlb_id, cast(WAR as double) as war, 'bat' as kind
    from raw_war_bat
    where mlb_ID is not null and year_ID <= 2026
    union all
    select cast(mlb_ID as bigint), cast(WAR as double), 'pitch'
    from raw_war_pitch
    where mlb_ID is not null and year_ID <= 2026
)
select
    mlb_id,
    coalesce(sum(war) filter (where kind = 'bat'), 0.0)     as war_bat,
    coalesce(sum(war) filter (where kind = 'pitch'), 0.0)   as war_pitch,
    round(coalesce(sum(war), 0.0), 2)                       as career_war
from seasons
group by mlb_id
