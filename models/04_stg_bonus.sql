-- stg_bonus
-- Grain: one row per draft pick (draft_year, pick_number).
-- Purpose: the Baseball-Reference fields accepted for each pick (2012-2017), the signing
-- bonus with its source, and slot value.
--
-- Baseball-Reference rows join on (draft_year, overall_pick = pick_number). A joined row is
-- accepted when its name matches the MLB name, or when it shares last name and first
-- initial (nicknames: Mike/Michael, Jake/Jacob; ~60 rows, reviewed by hand).
-- bonus_backfill withholds values on every name mismatch, so accepted values are read from
-- bbref_draft directly and bonus_backfill supplies only the match flags.
--
-- Bonus:
--   2012-2016  Baseball-Reference bonus.
--   2017+      MLB signing_bonus_usd, with 0 treated as missing (placeholders, mostly
--              rounds 35-40). In 2017 a missing MLB value falls back to Baseball-Reference.
--   $125,000 is a real bonus, not a placeholder: it is the CBA limit for picks after round
--   10 before any excess counts against the bonus pool, so many late picks sign for it.
-- Slot value: MLB pick_value with 0 treated as missing.
create or replace view stg_bonus as
with bbref as (
    select
        bf.draft_year,
        bf.pick_number,
        bb.signed       as bbref_signed,
        bb.bonus_usd    as bbref_bonus_usd,
        bb.from_type    as bbref_from_type
    from raw_bonus_backfill as bf
    join raw_bbref_draft as bb
        on bb.draft_year = bf.draft_year and bb.overall_pick = bf.pick_number
    where bf.bbref_matched
      and (not coalesce(bf.name_mismatch, false) or coalesce(bf.same_last_name_initial, false))
),

picks as (
    select
        p.draft_year,
        p.pick_number,
        nullif(p.mlb_bonus_usd_raw, 0)      as mlb_bonus_usd,
        nullif(p.pick_value_raw, 0)         as slot_value_usd,
        b.bbref_signed,
        cast(b.bbref_bonus_usd as double)   as bbref_bonus_usd,
        b.bbref_from_type
    from stg_picks as p
    left join bbref as b using (draft_year, pick_number)
),

chosen as (
    select
        *,
        case
            when draft_year <= 2016 and bbref_bonus_usd is not null then 'bbref'
            when draft_year >= 2017 and mlb_bonus_usd is not null then 'mlb'
            when draft_year = 2017 and bbref_bonus_usd is not null then 'bbref'
        end as bonus_source
    from picks
),

bonus as (
    select
        draft_year,
        pick_number,
        bbref_signed,
        bbref_from_type,
        case bonus_source
            when 'mlb' then mlb_bonus_usd
            when 'bbref' then bbref_bonus_usd
        end as bonus_usd,
        bonus_source,
        slot_value_usd
    from chosen
)

select
    *,
    bonus_usd / slot_value_usd as bonus_vs_slot,
    case
        when bonus_usd / slot_value_usd < 0.95 then 'under slot'
        when bonus_usd / slot_value_usd <= 1.05 then 'at slot'
        when bonus_usd / slot_value_usd > 1.05 then 'over slot'
    end as bonus_vs_slot_band
from bonus
