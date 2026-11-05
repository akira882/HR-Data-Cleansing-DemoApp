"""突合トレーニングのスターターコード（わざと素朴に書いてある）。

このまま実行すると動きますが、採点すると多くの見逃し・ノイズが出ます。
TODO を一つずつ解消して、採点結果がどう変わるかを観察してください。

    python learning/starter_recon.py
    python tools/score_recon.py --log
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "ab"
OUT = ROOT / "learning" / "output"


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # 受領時点では全列を文字列で読む（先頭ゼロを守るため）
    a = pd.read_csv(DATA / "system_a_employees.csv", encoding="cp932", dtype=str, keep_default_na=False)
    org = pd.read_csv(DATA / "system_a_org_master.csv", encoding="cp932", dtype=str, keep_default_na=False)
    b = pd.read_csv(DATA / "system_b_users.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    return a, org, b


def main() -> None:
    a, org, b = load()

    # TODO(Stage 1): 突合対象の母集団は本当にこれでよいか？（休職者・役員・出向者・退職者はどう扱う？）
    a_target = a[a["在籍区分"] == "1"]

    # TODO(Stage 4): 社員番号・氏名・部署名・雇用形態・日付をそろえる（クレンジング）
    # TODO(Stage 5): 社員番号だけで結合してよいか？ 空欄・先頭ゼロ消失・再雇用はどうする？
    merged = pd.merge(a_target, b, on="社員番号", how="outer", suffixes=("_a", "_b"), indicator=True)

    matches = merged[merged["_merge"] == "both"][["社員番号", "ユーザーID"]]
    matches.columns = ["a_emp_id", "b_user_id"]

    diffs = []
    for _, r in merged.iterrows():
        if r["_merge"] == "left_only":
            diffs.append({"a_emp_id": r["社員番号"], "b_user_id": "", "item": "a_only"})
        elif r["_merge"] == "right_only":
            diffs.append({"a_emp_id": "", "b_user_id": r["ユーザーID"], "item": "b_only"})
        else:
            # TODO(Stage 4): 比較の前に正規化しないと、表記ゆれがすべて差異になる
            if f"{r['姓']} {r['名']}" != r["氏名"]:
                diffs.append({"a_emp_id": r["社員番号"], "b_user_id": r["ユーザーID"], "item": "name"})
            if r["組織名"] != r["部署"]:
                diffs.append({"a_emp_id": r["社員番号"], "b_user_id": r["ユーザーID"], "item": "org"})
            # TODO(Stage 5): 雇用形態・入社日（許容差7日）・有効フラグ・社員番号も比較する

    OUT.mkdir(parents=True, exist_ok=True)
    matches.to_csv(OUT / "matches.csv", index=False)
    pd.DataFrame(diffs, columns=["a_emp_id", "b_user_id", "item"]).to_csv(OUT / "diffs.csv", index=False)
    print(f"出力しました: {OUT}（結合 {len(matches)} 組 / 差異 {len(diffs)} 件）")


if __name__ == "__main__":
    main()
