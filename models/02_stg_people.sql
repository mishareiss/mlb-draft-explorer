-- stg_people
-- Grain: one row per MLB person id.
-- Purpose: birth date and MLB debut date, typed as dates.
create or replace view stg_people as
with src as (
    select
        cast(id as bigint)                  as person_id,
        try_cast(birth_date as date)        as birth_date,
        try_cast(mlb_debut_date as date)    as mlb_debut_date
    from raw_people
)
select *
from src
qualify row_number() over (partition by person_id order by mlb_debut_date nulls last) = 1
