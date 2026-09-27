-- int_final_draft
-- Grain: one row per draft pick (draft_year, pick_number).
-- Purpose: flag each person's final draft and decide whether the pick signed.
--
-- is_final_draft: the row with the latest draft_year for that person_id. Outcomes are
-- credited only on this row, so a player drafted twice counts once.
-- signed:
--   - false on a non-final row: the player went back to school and was drafted again;
--   - otherwise true if Baseball-Reference marks the pick signed (2012-2017, accepted rows
--     only), or the bonus is above 0, or the player has an MLB debut; else false.
create or replace view int_final_draft as
with ranked as (
    select
        p.draft_year,
        p.pick_number,
        p.person_id,
        row_number() over (
            partition by p.person_id order by p.draft_year desc, p.pick_number desc
        ) = 1 as is_final_draft
    from stg_picks as p
)

select
    r.draft_year,
    r.pick_number,
    r.is_final_draft,
    r.is_final_draft and (
        coalesce(b.bbref_signed, false)
        or coalesce(b.bonus_usd > 0, false)
        or ppl.mlb_debut_date is not null
    ) as signed
from ranked as r
left join stg_bonus as b using (draft_year, pick_number)
left join stg_people as ppl on ppl.person_id = r.person_id
