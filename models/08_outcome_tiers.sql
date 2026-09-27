-- draft_outcomes (+ outcome tiers)
-- Grain: unchanged, one row per draft pick. Rebuilds draft_outcomes from 07 with three columns
-- appended, so 07 stays about joins and dimensions and the tier cutoffs live in one place.
--
-- outcome_tier buckets every 2012-2019 pick (not just final drafts) by what the pick produced:
-- a non-final or unsigned pick produced nothing for the drafting team. Null for 2020+ classes.
-- Career WAR accumulates with time, so older classes look better: a 2018-2019 draftee has had
-- fewer seasons to reach 5 or 15 WAR, and those classes' tiers are lenient (understated).
-- became_regular (5+ WAR) is set only on outcome_eligible rows, like reached_mlb's use there.
create or replace table draft_outcomes as
with tiered as (
    select
        *,
        case
            when draft_year not between 2012 and 2019 then null
            when not is_final_draft or not signed then 0  -- Didn't sign
            when not reached_mlb then 1                   -- Never reached MLB
            when career_war is null then null             -- no WAR row: flagged by quality
            when career_war < 1 then 2                    -- Cup of coffee
            when career_war < 5 then 3                    -- Role player
            when career_war < 15 then 4                   -- Regular
            else 5                                        -- Star
        end as outcome_tier_order
    from draft_outcomes
)

select
    * exclude (outcome_tier_order),
    [
        'Didn''t sign', 'Never reached MLB', 'Cup of coffee', 'Role player', 'Regular', 'Star'
    ][outcome_tier_order + 1]                                as outcome_tier,
    outcome_tier_order,
    case when outcome_eligible then career_war >= 5 end      as became_regular
from tiered
order by draft_year, pick_number
