"""練習用ブックの数式（手順シート・関数ドリル）が、表計算ソフトで正しい答えを出すかを検証する。

LibreOffice が入っていない環境ではスキップする。
"""
import shutil
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

from src.training.ab_generator import generate, write_outputs
from src.training.formulas import STEPS, formula_for
from src.training.scoring import score
from src.training.workbook import build_workbook

sys.path.insert(0, str(Path(__file__).parent))
from formula_check import drill_results, export_submission, fill_model_answers, recalc  # noqa: E402

needs_soffice = pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice が必要")


def test_steps_sheet_shows_formulas_as_text(tmp_path):
    write_outputs(generate(seed=1, level=1), tmp_path / "ab", tmp_path / "key")
    xlsx = build_workbook(tmp_path / "ab", tmp_path / "wb.xlsx")
    ws = load_workbook(xlsx)["手順"]
    shown = {ws.cell(row=i, column=6).value for i in range(2, len(STEPS) + 2)}
    assert shown == {formula_for(s, 2) for s in STEPS}
    assert all(ws.cell(row=i, column=6).data_type == "s" for i in range(2, len(STEPS) + 2))


def test_guide_document_contains_every_formula():
    doc = (Path(__file__).resolve().parents[1] / "docs" / "04_spreadsheet_formula_guide.md").read_text(encoding="utf-8")
    for s in STEPS:
        assert formula_for(s, 2) in doc, s.header


@needs_soffice
@pytest.mark.parametrize("seed,level", [(42, 1), (42, 3), (7, 3)])
def test_model_formulas_compute_a_perfect_submission(tmp_path, seed, level):
    write_outputs(generate(seed=seed, level=level), tmp_path / "ab", tmp_path / "key")
    blank = build_workbook(tmp_path / "ab", tmp_path / "blank" / "wb.xlsx")
    solved = tmp_path / "solved" / "wb.xlsx"
    solved.parent.mkdir()
    shutil.copy(blank, solved)
    fill_model_answers(solved)
    calculated = recalc(solved, tmp_path / "calc")

    assert drill_results(calculated) == ["○"] * len(drill_results(calculated))
    submission = tmp_path / "submission.xlsx"
    shutil.copy(blank, submission)
    export_submission(calculated, submission)
    r = score(submission, submission, tmp_path / "key")
    assert r.passed and r.diff_recall == 1.0 and not r.noise and not r.false_merges and not r.missed_matches
