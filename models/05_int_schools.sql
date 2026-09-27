-- int_schools
-- Grain: one row per draft pick (draft_year, pick_number).
-- Purpose: school type, display school name, division and conference for each pick.
--
-- school_type, first rule that fires:
--   1. High school, if any of the Task 2 HS rules match the pick:
--        - the raw name matches the HS name regex (ingest/build_school_ref.py NAME_RULES).
--          DuckDB's regex engine has no lookarounds, so service academies ('Naval Academy')
--          and 'School of ...' are removed before matching instead;
--        - the MLB school class has the level prefix 'HS' ('HS SR');
--        - the accepted Baseball-Reference row has from_type 'HS'.
--      Exception: the placeholder 'No School' (players signed out of Cuba or independent
--      ball, e.g. Kumar Rocker 2022) is not a high school.
--   2. reference/schools.csv: 4YR -> 4-year college, JC -> Junior college, OTHER -> Unknown.
--   3. Unknown.
--
-- Conference (D1 only): schools.csv holds two alignments. `conference_pre2024` is the
-- spring-2024 alignment and `conference_2024` the spring-2025 one (after the July 2024
-- moves). Draftees play the spring before the draft, so draft years <= 2024 use
-- conference_pre2024 and 2025 uses conference_2024. Earlier realignments are not modeled:
-- years before 2024 also get the spring-2024 alignment.
create or replace view int_schools as
with picks as (
    select
        p.draft_year,
        p.pick_number,
        p.school_name_raw,
        trim(p.school_name_raw) = 'No School'                   as is_placeholder,
        regexp_matches(
            regexp_replace(
                regexp_replace(p.school_name_raw, '(Military|Naval|Air Force|Coast Guard) Academy', '', 'g'),
                '\bSchool of', '', 'g'
            ),
            '\bHS\b|High School|Academy|\bPrep\b|Secondary|\bSS\b|Colegio|\bSchool\b'
        )                                                       as hs_by_name,
        p.school_class_level = 'HS'                             as hs_by_class,
        upper(b.bbref_from_type) = 'HS'                         as hs_by_bbref
    from stg_picks as p
    left join stg_bonus as b using (draft_year, pick_number)
),

typed as (
    select
        p.*,
        s.school_canonical,
        nullif(s.division, '')                                  as division,
        case
            when not p.is_placeholder
                 and (coalesce(p.hs_by_name, false)
                      or coalesce(p.hs_by_class, false)
                      or coalesce(p.hs_by_bbref, false))
                then 'High school'
            when s.school_type = '4YR' then '4-year college'
            when s.school_type = 'JC' then 'Junior college'
            else 'Unknown'
        end                                                     as school_type,
        nullif(case when p.draft_year <= 2024 then s.conference_pre2024 else s.conference_2024 end, '')
                                                                as d1_conference
    from picks as p
    left join ref_schools as s on s.school_name_raw = p.school_name_raw
)

select
    draft_year,
    pick_number,
    school_type,
    case
        when school_type = 'High school' then school_name_raw
        else coalesce(school_canonical, school_name_raw)
    end                                                         as school,
    case when school_type <> 'High school' then division end    as division,
    case when school_type = '4-year college' and division = 'D1' then d1_conference end
                                                                as conference,
    case
        when school_type = '4-year college' and division = 'D1' and d1_conference is not null
            then d1_conference
        when school_type = '4-year college' then 'Other 4-year'
        when school_type = 'Junior college' then 'Junior college'
        when school_type = 'High school' then 'High school'
        else 'Unknown'
    end                                                         as conference_group
from typed
