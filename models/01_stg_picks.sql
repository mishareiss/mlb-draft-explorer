-- stg_picks
-- Grain: one row per draft pick (draft_year, pick_number).
-- Purpose: select and type the draft-payload columns the model uses. MLB bonus and slot
-- value keep their raw form here; 04_stg_bonus applies the bonus rules.
create or replace view stg_picks as
with src as (
    select * from raw_draft_picks
)
select
    cast(draft_year as integer)                       as draft_year,
    cast(pick_number as integer)                      as pick_number,
    cast(pick_round as varchar)                       as round_label,
    -- supplemental labels ('CB-A', '1C', 'PPI', ...) have no round number
    try_cast(pick_round as integer)                   as round_number,
    team_name,
    cast(person_id as bigint)                         as person_id,
    person_full_name                                  as player_name,
    school_name                                       as school_name_raw,
    -- '4YR JR' -> '4YR'; bare 'JR'/'SR'/'SO'/'NS' carry no level
    case
        when upper(split_part(trim(school_school_class), ' ', 1)) in ('HS', '4YR', 'JC')
            then upper(split_part(trim(school_school_class), ' ', 1))
    end                                               as school_class_level,
    person_primary_position_abbreviation              as position,
    person_pitch_hand_code                            as pitch_hand,
    cast(signing_bonus_usd as double)                 as mlb_bonus_usd_raw,
    try_cast(pick_value as double)                    as pick_value_raw
from src
