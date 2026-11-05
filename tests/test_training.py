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
