import pandas as pd
import pytest
from conftest import FIXTURES

from ingest import build_school_ref as sr
from ingest import paths

BEFORE = FIXTURES / f"wikipedia_d1_{sr.REV_BEFORE_2024}_sample.html"
AFTER = FIXTURES / f"wikipedia_d1_{sr.REV_AFTER_2024}_sample.html"


@pytest.fixture
def d1() -> tuple[pd.DataFrame, pd.DataFrame]:
    return sr.parse_d1_list(BEFORE.read_text()), sr.parse_d1_list(AFTER.read_text())


# --- school type rules, one per priority level -------------------------------------------


def test_rule1_mlb_class_prefix():
    assert sr.classify_type("Somewhere", ["4YR JR", None, "JR"], [], []) == ("4YR", "mlb_class")
    assert sr.classify_type("Somewhere", ["JC J2"], ["4Yr"], []) == ("JC", "mlb_class")


def test_explicit_hs_or_jc_name_beats_pick_evidence():
    assert sr.classify_type("Blythewood (SC) HS", ["4YR JR"], [], []) == ("HS", "name_regex")
    assert sr.classify_type("Tyler Junior College", [], ["4Yr"], []) == ("JC", "name_regex")


def test_names_consistent():
    assert sr.names_consistent("TCU", "Texas Christian University")
    assert sr.names_consistent("LSU", "Louisiana State University")
    assert sr.names_consistent("Virginia", "University of Virginia")
    assert sr.names_consistent("Cal St Long Beach", "California State University, Long Beach")
    assert not sr.names_consistent("Blythewood (SC) HS", "University of South Carolina")
    assert not sr.names_consistent("Christopher Newport", "East Carolina University")


def test_rule1_bare_class_is_ignored():
    # bare JR/SR/SO carry no level: fall through to later rules
    assert sr.classify_type("Mystery Place", ["JR", "SR", "SO"], [], []) == ("UNKNOWN", "unknown")
    assert sr.class_level("JR") is None
    assert sr.class_level("NS") is None


def test_rule2_bbref_type_column():
    got = sr.classify_type(
        "San Jacinto", [None], ["JC"], ["San Jacinto College North (Houston, TX)"]
    )
    assert got == ("JC", "bbref_type")


def test_rule2_bbref_text():
    assert sr.classify_type("Tyler", [], [None], ["Tyler Junior College (Tyler, TX)"]) == (
        "JC",
        "bbref_text",
    )
    assert sr.bbref_text_level("Cathedral Catholic HS (San Diego, CA)") == "HS"
    assert sr.bbref_text_level("Rice University (Houston, TX)") == "4YR"
    assert sr.bbref_text_level("San Jacinto College North (Houston, TX)") is None  # not decisive


def test_rule3_name_regex():
    assert sr.classify_type("Alonso (FL) HS", [], [], []) == ("HS", "name_regex")
    assert sr.classify_type("Cypress CC", [], [], []) == ("JC", "name_regex")
    assert sr.classify_type("Abilene Christian U", [], [], []) == ("4YR", "name_regex")


def test_service_academies_and_school_of_are_not_high_schools():
    assert sr.name_level("Colorado School of Mines") is None
    assert sr.name_level("Air Force Academy") is None
    assert sr.bbref_text_level("United States Military Academy (West Point, NY)") is None
    assert sr.name_level("Home School (Orlando, FL)") == "HS"
    assert sr.name_level("IMG Academy") == "HS"


def test_rule4_unknown():
    assert sr.classify_type("Oklahoma Baptist", [], [], []) == ("UNKNOWN", "unknown")


def test_tied_evidence_falls_through():
    assert sr.classify_type("Cypress CC", ["4YR JR", "JC J1"], [], []) == ("JC", "name_regex")


# --- names and Wikipedia -----------------------------------------------------------------


def test_school_key():
    assert sr.school_key("Cal St Long Beach") == "cal state long beach"
    assert sr.school_key("St. John's") == "saint johns"
    assert sr.school_key("Mount St. Mary's") == "mount saint marys"
    assert sr.school_key("Texas A&M") == "texas a and m"
    assert sr.school_key("University of Texas at Arlington") == sr.school_key(
        "University of Texas - Arlington"
    )
    assert "virginia" in sr.key_variants("University of Virginia")


def test_school_key_expansions():
    assert sr.school_key("SUNY Stony Brook") == "stony brook"
    assert sr.school_key("UNC Charlotte") == sr.school_key("North Carolina-Charlotte")


def test_pool_key_merges_spelling_variants_only():
    assert sr.pool_key("Arizona ") == sr.pool_key("Arizona")
    assert sr.pool_key("Cal State-Long Beach") == sr.pool_key("Cal State Long Beach")
    assert sr.pool_key("Concordia (MN)") != sr.pool_key("Concordia (NE)")


def test_strip_location():
    assert sr.strip_location("Louisiana State University (Baton Rouge, LA)") == (
        "Louisiana State University"
    )
    assert sr.location_state("Louisiana State University (Baton Rouge, LA)") == "LA"


def test_parse_d1_list(d1):
    _, after = d1
    tcu = after.set_index("wiki_school").loc["Texas Christian University"]
    assert tcu["aliases"] == ["TCU"] and tcu["state"] == "TX" and tcu["conference"] == "Big 12"
    assert after.set_index("wiki_school").loc["Georgetown University", "state"] == "DC"
    assert not after["conference"].str.contains(r"\[").any()  # footnotes stripped


def test_derive_moves(d1):
    moves = sr.derive_moves(*d1).set_index("wiki_school")
    assert moves.loc["University of Texas at Austin"].tolist() == ["Big 12", "Southeastern"]
    assert moves.loc["Oregon State University"].tolist() == ["Pac-12", "Independent"]
    assert "Vanderbilt University" not in moves.index


def picks_frame(rows: list[tuple]) -> pd.DataFrame:
    cols = ["school_name", "school_school_class", "school_state"]
    df = pd.DataFrame(rows, columns=cols)
    df["draft_year"] = 2018
    df["pick_number"] = range(1, len(df) + 1)
    return df


@pytest.fixture
def schools(d1) -> pd.DataFrame:
    before, after = d1
    picks = picks_frame(
        [
            ("TCU", "4YR JR", "TX"),
            ("Texas Christian", "4YR SR", "TX"),
            ("LSU", "4YR JR", None),
            ("Texas", "4YR JR", "TX"),
            ("Miami", "4YR JR", "FL"),
            ("Oklahoma Baptist", None, None),
            ("Some College", "4YR SR", "KS"),
            ("Cypress CC", None, None),
            ("Alonso (FL) HS", None, None),
            ("Georgetown", "4YR JR", "DC"),
            ("Vanderbilt ", None, None),  # no evidence of its own; pooled with "Vanderbilt"
            ("Vanderbilt", "4YR JR", "TN"),
            ("Miami (OH)", "4YR SR", None),  # state tag: not the University of Miami
        ]
    )
    return sr.build_schools(picks, None, after, sr.derive_moves(before, after)).set_index(
        "school_name_raw"
    )


def test_build_aliases_and_conferences(schools):
    assert "Alonso (FL) HS" not in schools.index  # high schools are not listed
    assert (
        schools.loc["TCU", "school_canonical"] == schools.loc["Texas Christian", "school_canonical"]
    )
    assert schools.loc["LSU", "school_canonical"] == "Louisiana State University"
    assert schools.loc["Texas", ["conference_pre2024", "conference_2024"]].tolist() == [
        "Big 12",
        "Southeastern",
    ]
    assert schools.loc["Miami", "school_canonical"] == "University of Miami"  # state resolves
    assert schools.loc["Georgetown", "division"] == "D1"
    assert schools.loc["Vanderbilt ", "type_source"] == "mlb_class"
    assert schools.loc["Vanderbilt ", "conference_2024"] == "Southeastern"
    assert schools.loc["Miami (OH)", "state"] == "OH"
    assert schools.loc["Miami (OH)", "school_canonical"] != "University of Miami"
    assert (schools.loc[schools["division"] == "D1", "conf_source"] == "wikipedia").all()


def test_build_unknowns_flagged(schools):
    unk = schools.loc["Some College"]
    assert unk["division"] == "UNKNOWN" and unk["conference_2024"] == "" and unk["needs_review"]
    other = schools.loc["Oklahoma Baptist"]
    assert other["school_type"] == "OTHER" and other["type_source"] == "unknown"
    assert schools.loc["Cypress CC", "division"] == "JUCO"


def test_manual_rows_survive_rerun(tmp_path, schools):
    path = tmp_path / "schools.csv"
    generated = schools.reset_index()
    edited = generated.copy()
    i = edited.index[edited["school_name_raw"] == "Oklahoma Baptist"][0]
    edited.loc[i, ["school_type", "division", "type_source", "needs_review"]] = [
        "4YR",
        "NAIA",
        "manual",
        False,
    ]
    sr.write_schools(edited, path)

    merged = sr.merge_manual(generated, path)
    sr.write_schools(merged, path)
    row = sr.read_schools(path).set_index("school_name_raw").loc["Oklahoma Baptist"]
    assert row[["division", "type_source"]].tolist() == ["NAIA", "manual"]
    assert not row["needs_review"]
    assert len(merged) == len(generated)


def test_csv_round_trip_keeps_raw_whitespace(tmp_path, schools):
    df = schools.reset_index()
    df.loc[0, "school_name_raw"] = "Virginia "
    sr.write_schools(df, tmp_path / "s.csv")
    assert "Virginia " in sr.read_schools(tmp_path / "s.csv")["school_name_raw"].tolist()


# --- contract on the committed reference/schools.csv -------------------------------------


@pytest.fixture(scope="module")
def committed() -> pd.DataFrame:
    if not sr.SCHOOLS_CSV.exists():
        pytest.skip("reference/schools.csv not generated yet")
    return sr.read_schools(sr.SCHOOLS_CSV)


def test_contract_columns_and_unique(committed):
    assert committed.columns.tolist() == sr.COLUMNS
    assert committed["school_name_raw"].is_unique


def test_contract_enums(committed):
    assert set(committed["school_type"]) <= sr.SCHOOL_TYPES
    assert set(committed["division"]) <= sr.DIVISIONS


def test_contract_d1_rows_have_both_conferences(committed):
    d1 = committed[committed["division"] == "D1"]
    assert len(d1) > 0
    assert (d1["conference_pre2024"] != "").all() and (d1["conference_2024"] != "").all()
    non_d1 = committed[committed["division"] != "D1"]
    assert (non_d1["conference_2024"] == "").all()


def test_contract_unknown_division_needs_review(committed):
    auto = committed[committed["type_source"] != "manual"]
    assert auto.loc[auto["division"] == "UNKNOWN", "needs_review"].all()


def test_contract_raw_names_exist_in_draft_data(committed):
    picks_path = paths.INTERIM / "draft_picks.parquet"
    if not picks_path.exists():
        pytest.skip("draft_picks.parquet not present (run make pull)")
    names = set(pd.read_parquet(picks_path, columns=["school_name"])["school_name"].dropna())
    assert set(committed["school_name_raw"]) <= names


def test_contract_moves_file(committed):
    moves = pd.read_csv(sr.MOVES_CSV, comment="#", dtype=str)
    assert moves.columns.tolist() == ["wiki_school", "conference_pre2024", "conference_2024"]
    assert (moves["conference_pre2024"] != moves["conference_2024"]).all()
