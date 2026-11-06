"""スマホ用「判断ドリル」のページ（単一HTML）を作る。

使い方:
    python tools/build_mobile_drill.py
出力:
    mobile/hr_judgment_drill.html（問題データを埋め込んだページ。スマホのブラウザで開ける）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.training.drills import build_html  # noqa: E402


def main() -> None:
    counts = build_html(ROOT / "mobile" / "drill_template.html", ROOT / "mobile" / "hr_judgment_drill.html")
    print(f"作成しました: mobile/hr_judgment_drill.html（{counts}）")


if __name__ == "__main__":
    main()
