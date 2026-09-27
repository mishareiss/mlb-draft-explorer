-- draft_outcomes
-- Grain: one row per draft pick (draft_year, pick_number), 2012-2025.
-- Purpose: the analysis table the dashboard reads: identifiers, player and school
-- dimensions, bonus, signed/final-draft flags and MLB outcomes.
--
-- Age at draft is measured to the first day of that year's draft (reference/draft_dates.csv).
-- `age_at_draft` is completed years plus the fraction since the last birthday, truncated
-- to 1 decimal (18.97 -> 18.9), so `age_band` always equals its whole part.
-- Outcomes (reached_mlb, years_to_debut, career_war) are filled only on final-draft rows and
-- are null on earlier drafts of the same person. A final-draft player who never debuted has
-- career_war 0.0. outcome_eligible limits outcome views to classes with time to develop.
create or replace table draft_outcomes as
with base as (
    select
        p.*,
        d.draft_start_date,
        ppl.birth_date,
        ppl.mlb_debut_date,
        b.bonus_usd,
        b.bonus_source,
        b.slot_value_usd,
        b.bonus_vs_slot,
        b.bonus_vs_slot_band,
        s.school_type,
        s.school,
        s.division,
        s.conference,
        s.conference_group,
        f.is_final_draft,
        f.signed,
        w.career_war as war_total
    from stg_picks as p
    left join ref_draft_dates as d using (draft_year)
    left join stg_people as ppl on ppl.person_id = p.person_id
    left join stg_bonus as b using (draft_year, pick_number)
    left join int_schools as s using (draft_year, pick_number)
    left join int_final_draft as f using (draft_year, pick_number)
    left join stg_war as w on w.mlb_id = p.person_id
),

age as (
    select *, date_sub('year', birth_date, draft_start_date) as age_years
    from base
),

dims as (
    select
        *,
        -- completed years + days since the last birthday, truncated like a stated age
        floor(10 * (
            age_years
            + date_diff('day', birth_date + to_years(age_years), draft_start_date) / 365.25
        )) / 10 as age_at_draft
    from age
)

select
    -- identifiers
    draft_year,
    pick_number,
    round_label,
    round_number,
    team_name,
    person_id,
    player_name,
    school_name_raw,

    -- player
    birth_date,
    draft_start_date,
    age_at_draft,
    case
        when age_years <= 18 then '≤18'
        when age_years <= 22 then cast(age_years as varchar)
        when age_years >= 23 then '23+'
    end                                                     as age_band,
    position,
    pitch_hand,
    case
        when position = 'P' and pitch_hand = 'R' then 'RHP'
        when position = 'P' and pitch_hand = 'L' then 'LHP'
        when position = 'C' then 'C'
        when position in ('1B', '3B') then '1B/3B'
        when position in ('2B', 'SS') then '2B/SS'
        when position in ('LF', 'CF', 'RF', 'OF') then 'OF'
        else 'Other'
    end                                                     as position_group,

    -- slot and round
    case
        when pick_number <= 10 then '1–10'
        when pick_number <= 30 then '11–30'
        when pick_number <= 100 then '31–100'
        when pick_number <= 300 then '101–300'
        else '301+'
    end                                                     as slot_band,
    case
        when round_number between 1 and 5 then '1–5'
        when round_number between 6 and 10 then '6–10'
        when round_number between 11 and 20 then '11–20'
        when round_number >= 21 then '21+'
        else 'Supplemental'
    end                                                     as round_band,

    -- school
    school_type,
    school,
    division,
    conference,
    conference_group,

    -- bonus
    bonus_usd,
    bonus_source,
    case
        when not signed then 'Unsigned'
        when bonus_usd is null then 'Unknown'
        when bonus_usd < 100000 then '<$100k'
        when bonus_usd < 500000 then '$100k–$500k'
        when bonus_usd < 1000000 then '$500k–$1M'
        when bonus_usd < 3000000 then '$1M–$3M'
        else '$3M+'
    end                                                     as bonus_band,
    slot_value_usd,
    bonus_vs_slot,
    bonus_vs_slot_band,

    -- signing and outcomes
    is_final_draft,
    signed,
    mlb_debut_date,
    case when is_final_draft then mlb_debut_date is not null end
                                                            as reached_mlb,
    case when is_final_draft then
        round(date_diff('day', draft_start_date, mlb_debut_date) / 365.25, 1)
    end                                                     as years_to_debut,
    case
        when not is_final_draft then null
        when mlb_debut_date is null then 0.0
        else war_total  -- null if a debuted player has no WAR row (checked in quality)
    end                                                     as career_war,
    draft_year between 2012 and 2019 and is_final_draft     as outcome_eligible
from dims
order by draft_year, pick_number
