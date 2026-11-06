"""学習者の突合結果を正解表と照合して自己採点する。

提出物は2ファイル:
- matches.csv : a_emp_id, b_user_id           （同一人物と判定した組）
- diffs.csv   : a_emp_id, b_user_id, item[, cause]（報告すべき差異。1行＝1差異）
練習用ブック（.xlsx）の場合は、matches シートと diffs シートを読む。
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.training.ab_generator import DIFF_ITEMS

PASS_DIFF_RECALL = 0.9
PASS_MAX_NOISE = 5

# C（吸収すべき汚れ）が残っていた場合に出やすい差異項目
_C_ITEM_HINT = {
    "name_space_variant": {"name"}, "itaiji": {"name"}, "empno_zero_drop": {"emp_no", "a_only", "b_only"},
    "email_case": {"a_only", "b_only"}, "dept_name_variant": {"org"}, "dept_old_name": {"org"},
    "emp_type_label_variant": {"emp_type"}, "date_format_variant": {"hire_date"},
    "start_date_preregistration": {"hire_date"},
}
_TYPE_LABEL = {
    "name_space_variant": "氏名の空白ゆれ", "itaiji": "異体字", "empno_zero_drop": "社員番号の先頭ゼロ消失",
    "email_case": "メールの大文字小文字", "dept_name_variant": "部署名の略称・表記ゆれ",
    "dept_old_name": "組織改編前の旧部署名", "emp_type_label_variant": "雇用形態ラベルのゆれ",
    "date_format_variant": "日付形式のゆれ（和暦・ISO）", "start_date_preregistration": "許容範囲内の事前登録",
    "scope_excluded": "仕様上の対象外（役員・出向者）", "transfer_not_reflected": "異動の反映漏れ",
    "surname_change_not_reflected": "改姓の反映漏れ", "retired_still_active": "退職者アカウントの残存",
    "leave_marked_inactive": "休職者アカウントの誤った無効化", "emp_type_change_not_reflected": "登用の反映漏れ",
    "hire_date_typo": "利用開始日の入力誤り", "empno_missing": "社員番号の空欄",
    "test_or_shared_account": "テスト・共用アカウント", "new_hire_not_registered": "月中入社者の未登録",
    "rehire_empno_carried_over": "再雇用者の旧社員番号", "same_name_different_person": "同姓同名の別人",
    "should_match_b": "Bのみと報告したが、Aに結合すべき相手がいる（母集団の絞りすぎ・キーの不一致）",
    "should_match_a": "Aのみと報告したが、Bに結合すべき相手がいる（キーの不一致）",
}


def _read(path: Path, sheet: str | None = None) -> list[dict]:
    if path.suffix.lower() == ".xlsx":
        from src.training.workbook import read_sheet

        return read_sheet(path, sheet or path.stem)
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k.strip(): (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(f)]


def _diff_key(row: dict) -> tuple[str, str, str]:
    item = row["item"]
    a = "" if item == "b_only" else row.get("a_emp_id", "")
    b = "" if item == "a_only" else row.get("b_user_id", "")
    return a, b, item


@dataclass
class ScoreResult:
    seed: int
    level: int
    expected_matches: int
    correct_matches: int
    false_merges: list[tuple[str, str]]
    missed_matches: list[tuple[str, str]]
    expected_diffs: int
    found_diffs: int
    missed_diffs: list[dict]
    noise: list[tuple[tuple[str, str, str], str]]
    cause_checked: int = 0
    cause_correct: int = 0
    invalid_items: list[str] = field(default_factory=list)

    @property
    def match_precision(self) -> float:
        total = self.correct_matches + len(self.false_merges)
        return self.correct_matches / total if total else 0.0

    @property
    def match_recall(self) -> float:
        return self.correct_matches / self.expected_matches if self.expected_matches else 0.0

    @property
    def diff_recall(self) -> float:
        return self.found_diffs / self.expected_diffs if self.expected_diffs else 0.0

    @property
    def passed(self) -> bool:
        return not self.false_merges and self.diff_recall >= PASS_DIFF_RECALL and len(self.noise) <= PASS_MAX_NOISE


def score(matches_path: Path, diffs_path: Path, key_dir: Path) -> ScoreResult:
    manifest = json.loads((key_dir / "manifest.json").read_text(encoding="utf-8"))
    exp_matches = {(m["a_emp_id"], m["b_user_id"]) for m in _read(key_dir / "expected_matches.csv")}
    exp_diffs = {_diff_key(d): d for d in _read(key_dir / "expected_diffs.csv")}
    answer_key = _read(key_dir / "answer_key.csv")

    sub_matches = {(m.get("a_emp_id", ""), m.get("b_user_id", "")) for m in _read(matches_path, "matches")}
    sub_diff_rows = _read(diffs_path, "diffs")
    invalid = sorted({r.get("item", "") for r in sub_diff_rows if r.get("item", "") not in DIFF_ITEMS})
    sub_diffs = {_diff_key(r): r for r in sub_diff_rows if r.get("item", "") in DIFF_ITEMS}

    # 誤統合: 提出した組のうち、正解にない組（別人・別の雇用レコードとの結合）
    false_merges = sorted(sub_matches - exp_matches)
    missed_matches = sorted(exp_matches - sub_matches)

    found = exp_diffs.keys() & sub_diffs.keys()
    missed = [exp_diffs[k] for k in sorted(exp_diffs.keys() - sub_diffs.keys())]

    # ノイズ（報告すべきでない差異）の原因推定
    c_by_user: dict[str, list[str]] = {}
    for a in answer_key:
        if a["category"] in ("C", "T-ok") and a["b_user_id"]:
            c_by_user.setdefault(a["b_user_id"], []).append(a["dirt_type"])
    excluded = {a["a_emp_id"] for a in answer_key if a["dirt_type"] == "scope_excluded"}
    exp_users = {b for _, b in exp_matches}
    exp_as = {a for a, _ in exp_matches}
    noise = []
    for k in sorted(sub_diffs.keys() - exp_diffs.keys()):
        a_id, b_id, item = k
        reason = next((t for t in c_by_user.get(b_id, []) if item in _C_ITEM_HINT.get(t, set())), "unknown")
        if item == "a_only" and a_id in excluded:
            reason = "scope_excluded"
        elif reason == "unknown" and item == "b_only" and b_id in exp_users:
            reason = "should_match_b"
        elif reason == "unknown" and item == "a_only" and a_id in exp_as:
            reason = "should_match_a"
        noise.append((k, reason))

    cause_checked = cause_correct = 0
    for k in found:
        cause = sub_diffs[k].get("cause", "")
        if cause:
            cause_checked += 1
            cause_correct += cause.upper() == exp_diffs[k]["category"].upper()

    return ScoreResult(
        seed=manifest["seed"], level=manifest["level"], expected_matches=len(exp_matches),
        correct_matches=len(exp_matches & sub_matches), false_merges=false_merges, missed_matches=missed_matches,
        expected_diffs=len(exp_diffs), found_diffs=len(found), missed_diffs=missed, noise=noise,
        cause_checked=cause_checked, cause_correct=cause_correct, invalid_items=invalid,
    )


def format_report(r: ScoreResult, reveal: bool = False) -> str:
    lines = [
        "=" * 64,
        f" 突合トレーニング 採点結果（seed={r.seed}, level={r.level}）",
        "=" * 64,
        "",
        "■ 名寄せ（同一人物の判定）",
        f"  正しく結合できた組   : {r.correct_matches} / {r.expected_matches}  (再現率 {r.match_recall:.1%})",
        f"  誤統合（最重要）     : {len(r.false_merges)} 件  (適合率 {r.match_precision:.1%})",
        "",
        "■ 差異の検出",
        f"  検出できた差異       : {r.found_diffs} / {r.expected_diffs}  (再現率 {r.diff_recall:.1%})",
        f"  ノイズ（報告不要の差異）: {len(r.noise)} 件",
    ]
    if r.cause_checked:
        lines.append(f"  原因コードの正答     : {r.cause_correct} / {r.cause_checked}")
    if r.invalid_items:
        lines.append(f"  ⚠ 未定義の item 値   : {', '.join(r.invalid_items)}（{', '.join(DIFF_ITEMS)} のいずれか）")

    if r.missed_diffs:
        lines += ["", "■ 見逃した差異（種類別）"]
        for t, n in Counter(d["dirt_type"] for d in r.missed_diffs).most_common():
            lines.append(f"  - {_TYPE_LABEL.get(t, t)}: {n} 件")
    if r.noise:
        lines += ["", "■ ノイズの推定原因"]
        for t, n in Counter(reason for _, reason in r.noise).most_common():
            label = "原因不明（定義・突合ロジックを見直す）" if t == "unknown" else _TYPE_LABEL.get(t, t)
            lines.append(f"  - {label}: {n} 件")
    if r.false_merges:
        lines += ["", "■ 誤統合があります。別人（または別の雇用レコード）を同一人物と判定しています。",
                  "  氏名だけで結合していないか、再雇用者の新旧レコードを区別できているか確認してください。"]

    if reveal:
        lines += ["", "■ 詳細（--reveal）"]
        for a, b in r.false_merges:
            lines.append(f"  誤統合   a_emp_id={a} b_user_id={b}")
        for a, b in r.missed_matches:
            lines.append(f"  未結合   a_emp_id={a} b_user_id={b}")
        for d in r.missed_diffs:
            lines.append(f"  見逃し   a_emp_id={d['a_emp_id'] or '-'} b_user_id={d['b_user_id'] or '-'} "
                         f"item={d['item']} ({_TYPE_LABEL.get(d['dirt_type'], d['dirt_type'])})")
        for (a, b, item), reason in r.noise:
            lines.append(f"  ノイズ   a_emp_id={a or '-'} b_user_id={b or '-'} item={item} "
                         f"({_TYPE_LABEL.get(reason, '原因不明')})")

    verdict = "✅ 合格" if r.passed else "❌ 不合格"
    lines += ["", "-" * 64,
              f" 判定: {verdict}  （基準: 誤統合0件・差異の再現率{PASS_DIFF_RECALL:.0%}以上・ノイズ{PASS_MAX_NOISE}件以下）",
              "-" * 64]
    return "\n".join(lines)


def append_log(r: ScoreResult, log_path: Path) -> None:
    """採点結果を学習ログ（CSV）に1行追記する。"""
    new = not log_path.exists()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "seed", "level", "match_recall", "false_merges", "diff_recall",
                        "noise", "passed"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), r.seed, r.level, f"{r.match_recall:.3f}",
                    len(r.false_merges), f"{r.diff_recall:.3f}", len(r.noise), int(r.passed)])
