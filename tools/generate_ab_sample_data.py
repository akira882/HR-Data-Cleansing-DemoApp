"""A・B 2システム分の合成人事データ（汚れ入り）と正解表を生成する。

使い方:
    python tools/generate_ab_sample_data.py --level 1 --seed 42
    python tools/generate_ab_sample_data.py --level 1 --xlsx   # スプレッドシート練習用のブックも作る

出力:
    data/ab/            受領ファイル（学習者が扱うデータ）
    data/answer_key/    正解表（採点が終わるまで見ないこと）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.training.ab_generator import generate, write_outputs  # noqa: E402
from src.training.workbook import build_workbook  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=42, help="乱数の種。変えると別の問題になる")
    parser.add_argument("--level", type=int, default=1, choices=[1, 2, 3], help="難易度（1〜3）")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "ab")
    parser.add_argument("--xlsx", action="store_true", help="練習用ブック data/ab/training_workbook.xlsx も作る")
    parser.add_argument("--key-out", type=Path, default=ROOT / "data" / "answer_key")
    args = parser.parse_args()

    manifest = write_outputs(generate(args.seed, args.level), args.out, args.key_out)
    print(f"生成しました（seed={manifest['seed']}, level={manifest['level']}, 基準日={manifest['as_of']}）")
    print(f"  Aシステム: {manifest['a_records']} 件 / Bシステム: {manifest['b_records']} 件")
    print(f"  受領ファイル: {args.out}")
    if args.xlsx:
        print(f"  練習用ブック: {build_workbook(args.out, args.out / 'training_workbook.xlsx')}")
    print(f"  正解表     : {args.key_out}  ← 採点が終わるまで開かないでください")


if __name__ == "__main__":
    main()
