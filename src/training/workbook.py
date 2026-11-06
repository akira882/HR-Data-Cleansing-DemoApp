"""スプレッドシート（Excel / Googleスプレッドシート）で練習するためのブックを作る。

- 受領データは全セルを「文字列」で書き込む（先頭ゼロ・日付の自動変換を防ぐ）
- 原本シート（*_raw）はシート保護をかけ、書き換えられないようにする
- 作業シート・変換表・提出シートのひな形を用意する
"""
from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from src.training.ab_generator import AS_OF, DIFF_ITEMS

HEADER_FILL = PatternFill("solid", fgColor="DDE7F3")
RAW_FILL = PatternFill("solid", fgColor="EEEEEE")
WORK_FILL = PatternFill("solid", fgColor="FFF2CC")

A_WORK_COLUMNS = ["社員番号キー", "氏名キー", "メールキー", "突合対象"]
B_WORK_COLUMNS = ["社員番号キー", "氏名キー", "メールキー", "組織コード", "雇用区分コード", "利用開始日(日付)",
                  "結合先_社員番号", "結合方法"]

README_LINES = [
    ("突合トレーニング用ブック", True),
    (f"基準日: {AS_OF.isoformat()} ／ 正とするシステム: A（人事給与）", False),
    ("", False),
    ("■ シートの役割", True),
    ("A_raw / B_raw / org_raw … 受領した原本。シート保護済み（書き換えない）", False),
    ("A_work / B_work … 原本の写し＋黄色の作業列。ここに数式を書く", False),
    ("map_dept / map_type … 部署名→組織コード、雇用形態ラベル→コードの変換表（自分で作る）", False),
    ("matches / diffs … 提出用。docs/02_how_to_train.md 第3節の提出形式と同じ", False),
    ("", False),
    ("■ 進め方", True),
    ("1. docs/02_how_to_train.md 第3節の突合仕様書を読む", False),
    ("2. A_work・B_work の黄色の列に、比較用のキーを作る数式を書く", False),
    ("3. 変換表を作り、XLOOKUP で組織コード・雇用区分コードに変換する", False),
    ("4. 結合先を決め、matches シートに a_emp_id / b_user_id を書く", False),
    ("5. 報告すべき差異を diffs シートに書く（item・cause はプルダウンから選ぶ）", False),
    ("6. このブックを保存し、PCで採点する: python tools/score_recon.py --xlsx <このファイル>", False),
    ("", False),
    ("■ 数式の例（Excel）", True),
    ('社員番号を6桁に:  =IF(B2="","",TEXT(B2,"000000"))', False),
    ('空白を除く:      =SUBSTITUTE(SUBSTITUTE(C2," ",""),"　","")', False),
    ('異体字を寄せる:  =SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(x,"髙","高"),"﨑","崎"),"齋","斎"),"邉","辺")', False),
    ('組織コードへ変換: =XLOOKUP(TRIM(D2),map_dept!A:A,map_dept!B:B,"★未登録")', False),
    ('メールで救済:    =XLOOKUP(LOWER(H2),A_work!O:O,A_work!A:A,"")', False),
    ("", False),
    ("■ 守ること", True),
    ("・原本シートを書き換えない ・推測で値を埋めない（★未登録は止まって調べる） ・氏名だけで同一人物と確定しない", False),
]


def _read_csv(path: Path, encoding: str) -> list[list[str]]:
    with path.open(encoding=encoding, newline="") as f:
        return list(csv.reader(f))


def _write_table(ws, rows: list[list[str]], fill: PatternFill | None = None, extra_headers: list[str] = ()) -> None:
    header = rows[0] + list(extra_headers)
    ws.append(header)
    for r in rows[1:]:
        ws.append(r + [""] * len(extra_headers))
    for col in range(1, len(header) + 1):
        letter = get_column_letter(col)
        is_extra = col > len(rows[0])
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True)
        cell.fill = WORK_FILL if is_extra else HEADER_FILL
        ws.column_dimensions[letter].width = max(10, min(28, len(str(header[col - 1])) * 2 + 4))
        for row in ws.iter_rows(min_row=2, min_col=col, max_col=col):
            row[0].number_format = "@"  # 文字列として扱う
            if fill is not None and not is_extra:
                row[0].fill = fill
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def build_workbook(data_dir: Path, xlsx_path: Path) -> Path:
    """data_dir の受領CSVから練習用ブックを作る。"""
    a = _read_csv(data_dir / "system_a_employees.csv", "cp932")
    org = _read_csv(data_dir / "system_a_org_master.csv", "cp932")
    b = _read_csv(data_dir / "system_b_users.csv", "utf-8-sig")

    wb = Workbook()
    ws = wb.active
    ws.title = "README"
    for text, bold in README_LINES:
        ws.append([text])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=bold, size=12 if bold else 11)
    ws.column_dimensions["A"].width = 120

    for name, rows in (("A_raw", a), ("B_raw", b), ("org_raw", org)):
        sheet = wb.create_sheet(name)
        _write_table(sheet, rows, fill=RAW_FILL)
        sheet.protection.sheet = True  # 原本は書き換えない（パスワードなし）
        sheet.protection.autoFilter = False
        sheet.protection.sort = False

    _write_table(wb.create_sheet("A_work"), a, extra_headers=A_WORK_COLUMNS)
    _write_table(wb.create_sheet("B_work"), b, extra_headers=B_WORK_COLUMNS)

    for name, header in (("map_dept", ["部署名(B・正規化後)", "組織コード", "根拠・メモ"]),
                         ("map_type", ["雇用形態ラベル(B・正規化後)", "雇用区分コード", "根拠・メモ"]),
                         ("matches", ["a_emp_id", "b_user_id"]),
                         ("diffs", ["a_emp_id", "b_user_id", "item", "cause"])):
        sheet = wb.create_sheet(name)
        _write_table(sheet, [header])
        for col in range(1, len(header) + 1):
            letter = get_column_letter(col)
            sheet.column_dimensions[letter].width = 26
            for r in range(2, 3001):
                sheet[f"{letter}{r}"].number_format = "@"
        sheet.cell(row=1, column=1).alignment = Alignment(wrap_text=True)

    diffs = wb["diffs"]
    item_dv = DataValidation(type="list", formula1='"' + ",".join(DIFF_ITEMS) + '"', allow_blank=True)
    cause_dv = DataValidation(type="list", formula1='"T,S,D,E,C,U"', allow_blank=True)
    diffs.add_data_validation(item_dv)
    diffs.add_data_validation(cause_dv)
    item_dv.add("C2:C3000")
    cause_dv.add("D2:D3000")

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(xlsx_path)
    return xlsx_path


def read_sheet(xlsx_path: Path, sheet: str) -> list[dict]:
    """提出シートを読み、文字列の dict のリストにする（空行は除く）。"""
    from openpyxl import load_workbook

    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    if sheet not in wb.sheetnames:
        raise ValueError(f"シート '{sheet}' が {xlsx_path} にありません")
    rows = list(wb[sheet].iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    out = []
    for r in rows[1:]:
        values = ["" if v is None else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)).strip()
                  for v in r]
        if any(values):
            out.append({h: v for h, v in zip(header, values) if h})
    return out
