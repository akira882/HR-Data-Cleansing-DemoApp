"""突合結果を正解表と照合して自己採点する。

使い方:
    python tools/score_recon.py --matches learning/output/matches.csv --diffs learning/output/diffs.csv
    python tools/score_recon.py ... --log          # learning/score_log.csv に結果を記録
    python tools/score_recon.py ... --reveal       # 見逃し・ノイズを1件ずつ表示（答えを見ることになる）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.training.scoring import append_log, format_report, score  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matches", type=Path, default=ROOT / "learning" / "output" / "matches.csv")
    parser.add_argument("--diffs", type=Path, default=ROOT / "learning" / "output" / "diffs.csv")
    parser.add_argument("--key-dir", type=Path, default=ROOT / "data" / "answer_key")
    parser.add_argument("--reveal", action="store_true", help="個別の見逃し・ノイズを表示する")
    parser.add_argument("--log", action="store_true", help="learning/score_log.csv に結果を追記する")
    args = parser.parse_args()

    result = score(args.matches, args.diffs, args.key_dir)
    print(format_report(result, reveal=args.reveal))
    if args.log:
        append_log(result, ROOT / "learning" / "score_log.csv")
        print("learning/score_log.csv に記録しました。")


if __name__ == "__main__":
    main()
