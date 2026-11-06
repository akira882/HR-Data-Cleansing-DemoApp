"""トレーニング教材（合成データ生成器・採点）のテスト。"""
import csv
import shutil
from pathlib import Path

import pandas as pd
import pytest

from src.training.ab_generator import DIFF_ITEMS, DIRT_PLAN, generate, write_outputs
from src.training.scoring import score


@pytest.fixture(scope="module", params=[1, 2, 3])
def generated(request, tmp_path_factory):
    base = tmp_path_factory.mktemp(f"lv{request.param}")
    manifest = write_outputs(generate(seed=42, level=request.param), base / "ab", base / "key")
    return base, manifest


def test_same_seed_produces_identical_files(tmp_path):
    m1 = write_outputs(generate(seed=7, level=3), tmp_path / "1" / "ab", tmp_path / "1" / "key")
    m2 = write_outputs(generate(seed=7, level=3), tmp_path / "2" / "ab", tmp_path / "2" / "key")
    assert m1["files"] == m2["files"]


def test_different_seed_produces_different_data(tmp_path):
    m1 = write_outputs(generate(seed=1, level=2), tmp_path / "1" / "ab", tmp_path / "1" / "key")
    m2 = write_outputs(generate(seed=2, level=2), tmp_path / "2" / "ab", tmp_path / "2" / "key")
    assert m1["files"]["system_b_users.csv"] != m2["files"]["system_b_users.csv"]


def test_files_are_readable_with_declared_encodings(generated):
    base, manifest = generated
    a = pd.read_csv(base / "ab" / "system_a_employees.csv", encoding="cp932", dtype=str, keep_default_na=False)
    b = pd.read_csv(base / "ab" / "system_b_users.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    assert len(a) == manifest["a_records"] and len(b) == manifest["b_records"]
    assert a["社員番号"].is_unique and b["ユーザーID"].is_unique
    assert a["社員番号"].str.fullmatch(r"\d{6}").all()


def test_population_is_about_1000_in_scope_employees(generated):
    base, _ = generated
    a = pd.read_csv(base / "ab" / "system_a_employees.csv", encoding="cp932", dtype=str, keep_default_na=False)
    assert 990 <= a["在籍区分"].isin(["1", "2"]).sum() <= 1010


def test_answer_key_is_consistent_with_outputs(generated):
    base, _ = generated
    a_ids = set(pd.read_csv(base / "ab" / "system_a_employees.csv", encoding="cp932", dtype=str)["社員番号"])
    b_ids = set(pd.read_csv(base / "ab" / "system_b_users.csv", encoding="utf-8-sig", dtype=str)["ユーザーID"])
    with (base / "key" / "expected_matches.csv").open(encoding="utf-8-sig") as f:
        matches = list(csv.DictReader(f))
    assert all(m["a_emp_id"] in a_ids and m["b_user_id"] in b_ids for m in matches)
    assert len({m["b_user_id"] for m in matches}) == len(matches)  # Bの1ユーザーは高々1人に結合
    with (base / "key" / "expected_diffs.csv").open(encoding="utf-8-sig") as f:
        diffs = list(csv.DictReader(f))
    assert diffs and all(d["item"] in DIFF_ITEMS for d in diffs)
    with (base / "key" / "answer_key.csv").open(encoding="utf-8-sig") as f:
        assert {r["dirt_type"] for r in csv.DictReader(f)} <= set(DIRT_PLAN)


def test_level3_plants_at_least_15_dirt_types(tmp_path):
    data = generate(seed=42, level=3)
    types = {a["dirt_type"] for a in data.answer_key if a["category"] != "S"}
    assert len(types) >= 15


def test_perfect_submission_passes_with_zero_noise(generated, tmp_path):
    base, _ = generated
    shutil.copy(base / "key" / "expected_matches.csv", tmp_path / "matches.csv")
    shutil.copy(base / "key" / "expected_diffs.csv", tmp_path / "diffs.csv")
    r = score(tmp_path / "matches.csv", tmp_path / "diffs.csv", base / "key")
    assert r.passed and r.diff_recall == 1.0 and not r.noise and not r.false_merges


def test_name_only_matching_is_caught_as_false_merge(tmp_path):
    base = tmp_path
    write_outputs(generate(seed=42, level=3), base / "ab", base / "key")
    with (base / "key" / "expected_matches.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    # 正しい結合のうち1組の相手を入れ替える（別人との結合）
    rows[0]["b_user_id"], rows[1]["b_user_id"] = rows[1]["b_user_id"], rows[0]["b_user_id"]
    pd.DataFrame(rows).to_csv(base / "matches.csv", index=False)
    shutil.copy(base / "key" / "expected_diffs.csv", base / "diffs.csv")
    r = score(base / "matches.csv", base / "diffs.csv", base / "key")
    assert len(r.false_merges) == 2 and not r.passed


def test_starter_solution_does_not_pass(tmp_path, monkeypatch):
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("starter", root / "learning" / "starter_recon.py")
    starter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(starter)
    write_outputs(generate(seed=42, level=2), tmp_path / "ab", tmp_path / "key")
    monkeypatch.setattr(starter, "DATA", tmp_path / "ab")
    monkeypatch.setattr(starter, "OUT", tmp_path / "out")
    starter.main()
    r = score(tmp_path / "out" / "matches.csv", tmp_path / "out" / "diffs.csv", tmp_path / "key")
    assert not r.passed and len(r.noise) > 0


def test_workbook_keeps_text_and_scores_from_sheets(tmp_path):
    from openpyxl import load_workbook

    from src.training.workbook import build_workbook

    write_outputs(generate(seed=42, level=2), tmp_path / "ab", tmp_path / "key")
    xlsx = build_workbook(tmp_path / "ab", tmp_path / "ab" / "training_workbook.xlsx")
    wb = load_workbook(xlsx)
    assert {"README", "A_raw", "B_raw", "org_raw", "A_work", "B_work", "map_dept", "map_type",
            "matches", "diffs"} <= set(wb.sheetnames)
    assert wb["A_raw"].protection.sheet
    first_id = wb["A_raw"]["A2"].value
    assert isinstance(first_id, str) and first_id.startswith("0") and len(first_id) == 6

    # 学習者が模範解答をシートに書き込んだ想定
    for sheet, src in (("matches", "expected_matches.csv"), ("diffs", "expected_diffs.csv")):
        with (tmp_path / "key" / src).open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        ws = wb[sheet]
        header = [c.value for c in ws[1]]
        for i, row in enumerate(rows, start=2):
            for j, h in enumerate(header, start=1):
                ws.cell(row=i, column=j, value=row.get(h, "") if h != "cause" else row["category"])
    wb.save(xlsx)
    r = score(xlsx, xlsx, tmp_path / "key")
    assert r.passed and not r.noise and r.cause_correct == r.cause_checked == r.found_diffs


def test_mobile_drill_cases_are_valid_and_deterministic():
    from src.training.drills import PRINCIPLES, build_cases

    cases = build_cases()
    assert cases == build_cases()
    kinds = {c["kind"] for c in cases}
    assert kinds == {"match", "diff", "action", "principle"}
    for c in cases:
        keys = {o["key"] for o in c["options"]}
        assert c["answer"] and set(c["answer"]) <= keys, c["id"]
        assert c["principle"] in PRINCIPLES and c["explain"]
    # 「報告なし」が正解の差異問題も混ざっている（何でも疑うと失点する）
    diff_answers = [c["answer"] for c in cases if c["kind"] == "diff"]
    assert ["none"] in diff_answers and any(a != ["none"] for a in diff_answers)


def test_mobile_drill_html_embeds_data(tmp_path):
    from src.training.drills import build_html

    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "drill.html"
    counts = build_html(root / "mobile" / "drill_template.html", out)
    html = out.read_text(encoding="utf-8")
    assert "/*__DRILL_DATA__*/" not in html and counts["total"] >= 100
