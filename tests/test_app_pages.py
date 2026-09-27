"""Smoke-run each Streamlit page on the 40-row fixture (no network, no full data file)."""

import json
import time
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from app_fixture import make_outcomes
from streamlit.testing.v1 import AppTest

from lib import metrics
from lib.data import PRESETS, to_query_params
from lib.tabs import TABS, _player_line
from quality.checks import build_report
from transform import slot_model

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
PAGES = ["Explorer.py", "pages/1_Data_Quality.py", "pages/2_About.py"]


@pytest.fixture(scope="session")
def fixture_files(tmp_path_factory):
    folder = tmp_path_factory.mktemp("app_data")
    df = make_outcomes()
    df.to_parquet(folder / "draft_outcomes.parquet", index=False)
    curve, _ = slot_model.fit_all(df)
    curve.to_parquet(folder / "slot_expectation.parquet", index=False)
    report = build_report(df, expected_rows=len(df))
    (folder / "quality_report.json").write_text(json.dumps(report, default=str))
    return folder


@pytest.fixture(autouse=True)
def use_fixture(fixture_files, monkeypatch):
    monkeypatch.setenv("DRAFT_OUTCOMES_PATH", str(fixture_files / "draft_outcomes.parquet"))
    monkeypatch.setenv("SLOT_EXPECTATION_PATH", str(fixture_files / "slot_expectation.parquet"))
    monkeypatch.setenv("QUALITY_REPORT_PATH", str(fixture_files / "quality_report.json"))


def app(page: str = "Explorer.py", **params: str | list[str]) -> AppTest:
    at = AppTest.from_file(str(APP / page), default_timeout=30)
    for key, value in params.items():
        at.query_params[key] = value
    return at


def run(page: str = "Explorer.py", **params: str | list[str]) -> AppTest:
    return app(page, **params).run()


def headings(at: AppTest) -> list[str]:
    return [h.value for h in at.subheader]


def match_count(at: AppTest) -> str:
    return next(m.value for m in at.sidebar.markdown if m.value.endswith("picks match**"))


@pytest.mark.parametrize("page", PAGES)
def test_page_runs(page):
    at = run(page)
    assert not at.exception
    assert at.title


@pytest.mark.parametrize("tab", TABS)
@pytest.mark.parametrize("preset", [None, *PRESETS])
def test_every_tab_renders(tab, preset):
    params = to_query_params(PRESETS[preset]) if preset else {}
    at = run(**params, tab=tab)
    assert not at.exception
    # a preset with no fixture rows shows the empty state, one with too few the info note
    if not at.warning and not at.info:
        assert headings(at), f"{tab} has no takeaway heading"


def test_explorer_default_overview():
    at = run()
    assert match_count(at) == "**40 picks match**"
    assert at.title[0].value == "MLB Draft Explorer"
    assert at.expander[0].label == "How to read this"
    assert len(headings(at)) == 2  # the tiles and the outcome distribution
    tiles = " ".join(m.value for m in at.markdown if "class='tile'" in m.value)
    for label in ["Players", "Signed", "Reached the majors", "vs. draft slot", "Became a regular"]:
        assert label in tiles
    assert "26 signed players, drafted 2012–2019 (40 picks, 2012–2025)." in " ".join(
        m.value for m in at.markdown
    )
    assert not at.warning


def test_explorer_filter_matching_nothing_shows_empty_state():
    at = run()
    at.multiselect(key="f_school_types").set_value(["High school"]).run()
    at.multiselect(key="f_conferences").set_value(["Southeastern"]).run()
    assert not at.exception
    assert "No picks match" in at.warning[0].value
    assert not headings(at)


def test_explorer_too_few_outcome_rows():
    at = run()
    at.slider(key="f_years").set_value((2020, 2025)).run()
    assert not at.exception
    assert "no outcomes to show" in at.info[0].value


def test_explorer_school_options_narrow_by_conference():
    at = run()
    at.multiselect(key="f_conferences").set_value(["Southeastern"]).run()
    assert at.multiselect(key="f_schools").options == ["Alpha U"]


def test_explorer_pick_range_slider():
    at = run()
    assert at.slider(key="f_picks").value == (1, 1238)
    at.slider(key="f_picks").set_value((1, 10)).run()
    assert match_count(at) == "**20 picks match**"


def test_explorer_reset_restores_defaults():
    at = run()
    at.multiselect(key="f_positions").set_value(["RHP"]).run()
    assert match_count(at) == "**10 picks match**"
    at.sidebar.button[0].click().run()
    assert match_count(at) == "**40 picks match**"


def test_url_query_params_load_filters():
    at = run(position=["RHP"], pick="1-20", unsigned="1", tab="Rankings")
    assert not at.exception
    assert at.multiselect(key="f_positions").value == ["RHP"]
    assert at.slider(key="f_picks").value == (1, 20)
    assert at.toggle(key="f_unsigned").value is True
    assert at.session_state["tab"] == "Rankings"
    # and the URL keeps mirroring the filters
    assert at.query_params["position"] == ["RHP"]


def test_filters_are_mirrored_to_the_url():
    at = run()
    at.multiselect(key="f_school_types").set_value(["High school"]).run()
    assert at.query_params["school_type"] == ["High school"]
    assert "position" not in at.query_params


def test_preset_query_matches_preset_chip():
    at = run(**to_query_params(PRESETS["SEC college arms"]))
    assert at.session_state["preset"] == "SEC college arms"


def test_round_range_disables_vs_slot_metrics():
    at = run(tab="Rankings")
    slot_labels = {metrics.METRICS[m].label for m in metrics.VS_SLOT_METRICS}
    assert slot_labels <= set(at.selectbox(key="rk_metric").options)
    at.selectbox(key="rk_by").set_value("Round range").run()
    assert not at.exception
    assert not slot_labels & set(at.selectbox(key="rk_metric").options)
    assert any("off for Round range" in c.value for c in at.caption)


def test_data_quality_lists_every_check():
    at = run("pages/1_Data_Quality.py")
    assert len(at.expander) == len(build_report(make_outcomes(), 40)["checks"])
    assert len(headings(at)) == 6  # five takeaway headings, then Known limitations
    assert headings(at)[0].startswith("17 of 19 checks pass") or "checks pass" in headings(at)[0]
    assert headings(at)[-1] == "Known limitations"


def test_cold_start_on_real_data_under_3_seconds(monkeypatch):
    real = ROOT / "data" / "processed"
    if not (real / "draft_outcomes.parquet").exists():
        pytest.skip("no processed data")
    monkeypatch.setenv("DRAFT_OUTCOMES_PATH", str(real / "draft_outcomes.parquet"))
    monkeypatch.setenv("SLOT_EXPECTATION_PATH", str(real / "slot_expectation.parquet"))
    st.cache_data.clear()
    start = time.perf_counter()
    at = run()
    elapsed = time.perf_counter() - start
    assert not at.exception
    assert elapsed < 3.0, f"cold start took {elapsed:.2f}s"


def test_player_line_bonus_wording():
    row = {"player_name": "A B", "draft_year": 2015, "pick_number": 3, "career_war": 1.2}
    assert "signed for $1.5M" in _player_line(pd.Series({**row, "bonus_usd": 1_500_000.0}))
    unknown = _player_line(pd.Series({**row, "bonus_usd": float("nan")}))
    assert "bonus unknown" in unknown and "signed for" not in unknown
