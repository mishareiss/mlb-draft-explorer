"""Smoke-run each Streamlit page on the 40-row fixture (no network, no full data file)."""

import json
from pathlib import Path

import pytest
from app_fixture import make_outcomes
from streamlit.testing.v1 import AppTest

from quality.checks import build_report

APP = Path(__file__).resolve().parents[1] / "app"
PAGES = ["Explorer.py", "pages/1_Data_Quality.py", "pages/2_About.py"]


@pytest.fixture(scope="session")
def fixture_files(tmp_path_factory):
    folder = tmp_path_factory.mktemp("app_data")
    df = make_outcomes()
    df.to_parquet(folder / "draft_outcomes.parquet", index=False)
    report = build_report(df, expected_rows=len(df))
    (folder / "quality_report.json").write_text(json.dumps(report, default=str))
    return folder


@pytest.fixture(autouse=True)
def use_fixture(fixture_files, monkeypatch):
    monkeypatch.setenv("DRAFT_OUTCOMES_PATH", str(fixture_files / "draft_outcomes.parquet"))
    monkeypatch.setenv("QUALITY_REPORT_PATH", str(fixture_files / "quality_report.json"))


def run(page: str) -> AppTest:
    return AppTest.from_file(str(APP / page), default_timeout=30).run()


@pytest.mark.parametrize("page", PAGES)
def test_page_runs(page):
    at = run(page)
    assert not at.exception
    assert at.title


def test_explorer_default_panels():
    at = run("Explorer.py")
    assert at.sidebar.markdown[-1].value == "**40 picks match**"
    assert [m.label for m in at.metric][:3] == ["Picks", "Signed", "Reached MLB"]
    takeaways = [m.value for m in at.markdown if m.value.startswith("**Takeaway")]
    assert len(takeaways) == 6
    assert not at.warning


def test_explorer_filter_matching_nothing_shows_empty_state():
    at = run("Explorer.py")
    at.multiselect(key="f_school_types").set_value(["High school"]).run()
    at.multiselect(key="f_conferences").set_value(["Southeastern"]).run()
    assert not at.exception
    assert "No picks match" in at.warning[0].value
    assert not at.metric


def test_explorer_too_few_outcome_rows_hides_outcome_panels():
    at = run("Explorer.py")
    at.slider(key="f_years").set_value((2020, 2025)).run()
    assert not at.exception
    assert "outcome panels are hidden" in at.info[0].value
    assert "Outcomes use 2012–2019 classes" in at.caption[0].value


def test_explorer_school_options_narrow_by_conference():
    at = run("Explorer.py")
    at.multiselect(key="f_conferences").set_value(["Southeastern"]).run()
    assert at.multiselect(key="f_schools").options == ["Alpha U"]


def test_explorer_reset_restores_defaults():
    at = run("Explorer.py")
    at.multiselect(key="f_positions").set_value(["RHP"]).run()
    assert at.sidebar.markdown[-1].value == "**10 picks match**"
    at.sidebar.button[0].click().run()
    assert at.sidebar.markdown[-1].value == "**40 picks match**"


def test_data_quality_lists_every_check():
    at = run("pages/1_Data_Quality.py")
    assert len(at.expander) == len(build_report(make_outcomes(), 40)["checks"])
