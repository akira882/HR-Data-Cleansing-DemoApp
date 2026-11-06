"""スプレッドシート（Excel / Googleスプレッドシート）で練習するためのブックを作る。

- 受領データは全セルを「文字列」で書き込む（先頭ゼロ・日付の自動変換を防ぐ）
- 原本シート（*_raw）はシート保護をかけ、書き換えられないようにする
- 関数ドリル（1関数ずつ練習し、その場で○×が出る）と、手順シート（列ごとの数式と読み方）を入れる
- 作業シートの列見出しは src/training/formulas.py の手順と一致させる
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from src.training.ab_generator import AS_OF, DIFF_ITEMS
from src.training.formulas import (DRILL_LIST, DRILL_LOOKUP_TABLE, FUNCTION_DRILLS, STEPS, formula_for,
                                   steps_for)

HEADER_FILL = PatternFill("solid", fgColor="DDE7F3")
RAW_FILL = PatternFill("solid", fgColor="EEEEEE")
WORK_FILL = PatternFill("solid", fgColor="FFF2CC")
HINT_FONT = Font(color="808080")

README_LINES = [
    ("突合トレーニング用ブック", True),
    (f"基準日: {AS_OF.isoformat()} ／ 正とするシステム: A（人事給与）", False),
    ("", False),
    ("■ 進める順番", True),
    ("1. 「関数ドリル」シート … 使う関数を1つずつ練習する。G列に数式を書くと、H列に○×が出る", False),
    ("2. 「手順」シート … A_work・B_work の黄色の列に、上から順に数式を入れる。列ごとに目的・数式・読み方・注意がある", False),
    ("3. 変換表（map_dept・map_type）を作る … B_work の ★未登録 がなくなるまで1行ずつ足す", False),
    ("4. 提出シート（matches・diffs）を作る … 手順シートの最後に書き出し方がある", False),
    ("5. PCで採点する: python tools/score_recon.py --xlsx <このファイル> --log", False),
    ("", False),
    ("■ シートの役割", True),
    ("A_raw / B_raw / org_raw … 受領した原本。シート保護済み（書き換えない）", False),
    ("A_work / B_work … 原本の写し＋黄色の作業列。ここに数式を書く", False),
    ("map_dept / map_type … 変換表（自分で作る）", False),
    ("matches / diffs … 提出用。item・cause はプルダウンから選ぶ", False),
    ("", False),
    ("■ 数式の入れ方（初めての人へ）", True),
    ("・2行目に数式を入れ、セルの右下の■をダブルクリックすると、最終行までコピーされる（行番号は自動でずれる）", False),
    ("・数式は「手順」シートからコピーせず、読みながら自分で入力すると身につく。詰まったら手順シートを見る", False),
    ("・XLOOKUP は Excel 2021 / Microsoft 365 / Googleスプレッドシートで使える。古いExcelでは使えない", False),
    ("・Googleスプレッドシートは「ファイル」→「設定」で地域を「日本」にしておく（日付の解釈のため）", False),
    ("", False),
    ("■ 守ること", True),
    ("・原本シートを書き換えない ・推測で値を埋めない（★未登録は止まって調べる） ・氏名だけで同一人物と確定しない", False),
]

EXPORT_STEPS = [
    ("matches を作る",
     "B_work で W列（結合先）が空欄でない行に絞り込み、W列を matches の a_emp_id、A列を b_user_id に「値として貼り付け」する"),
    ("diffs を作る（項目の差異）",
     "B_work の Z〜AE列を1列ずつ、空欄でない行に絞り込む。結合先(W)・ユーザーID(A)・その列の値を、"
     "diffs の a_emp_id・b_user_id・item に値として貼り付ける"),
    ("diffs を作る（Bのみ）", "B_work の AF列が b_only の行を絞り込み、ユーザーID(A)を b_user_id に、b_only を item に貼る（a_emp_id は空欄）"),
    ("diffs を作る（Aのみ）", "A_work の S列が a_only の行を絞り込み、社員番号(A)を a_emp_id に、a_only を item に貼る（b_user_id は空欄）"),
    ("cause を付ける（Stage 6〜）", "diffs の各行に原因コード（T タイミング差 / E 入力誤り など）をプルダウンで選ぶ"),
]


def _to_value(v):
    if isinstance(v, str) and v.startswith("__DATE__"):
        return date.fromisoformat(v[len("__DATE__"):])
    return v


def _set_text(cell, text: str) -> None:
    """数式に見える文字列（=で始まる）も、計算せずに文字列として入れる。"""
    cell.value = text
    cell.data_type = "s"


def _read_csv(path: Path, encoding: str) -> list[list[str]]:
    with path.open(encoding=encoding, newline="") as f:
        return list(csv.reader(f))


def _style_header(ws, ncols: int, work_from: int | None = None) -> None:
    for col in range(1, ncols + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True)
        cell.fill = WORK_FILL if work_from and col >= work_from else HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"


def _write_table(ws, rows: list[list[str]], fill: PatternFill | None = None, extra_headers: list[str] = ()) -> None:
    header = rows[0] + list(extra_headers)
    ws.append(header)
    for r in rows[1:]:
        ws.append(r + [""] * len(extra_headers))
    raw_cols = len(rows[0])
    for col in range(1, len(header) + 1):
        letter = get_column_letter(col)
        ws.column_dimensions[letter].width = max(10, min(24, len(str(header[col - 1])) * 2 + 4))
        if col <= raw_cols:
            for row in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                row[0].number_format = "@"  # 文字列として扱う
                if fill is not None:
                    row[0].fill = fill
    _style_header(ws, len(header), work_from=raw_cols + 1 if extra_headers else None)
    ws.auto_filter.ref = ws.dimensions


def _work_headers(sheet: str, raw_cols: int) -> list[str]:
    steps = steps_for(sheet)
    for i, s in enumerate(steps):  # 列の位置と手順の列記号が一致しているか
        assert column_index_from_string(s.col) == raw_cols + 1 + i, (sheet, s.col)
    return [s.header for s in steps]


def _drill_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("関数ドリル")
    ws.append(["No", "関数", "やりたいこと", "入力1", "入力2", "期待する結果", "あなたの数式（ここに入力）", "判定",
               "構文", "部署キー（表）", "組織コード（表）", "", "社員番号一覧", "答えの例（詰まったら見る）"])
    _style_header(ws, 14)
    for i, (fn, goal, in1, in2, expected, syntax, answer) in enumerate(FUNCTION_DRILLS, start=2):
        ws.cell(row=i, column=1, value=i - 1)
        ws.cell(row=i, column=2, value=fn)
        ws.cell(row=i, column=3, value=goal)
        for col, v in ((4, in1), (5, in2)):
            c = ws.cell(row=i, column=col, value=_to_value(v) if v != "" else None)
            c.number_format = "yyyy-mm-dd" if isinstance(c.value, date) else "@"
        exp = ws.cell(row=i, column=6, value=_to_value(expected))
        exp.number_format = "yyyy-mm-dd" if isinstance(exp.value, date) else ("General" if isinstance(expected, int)
                                                                              else "@")
        ws.cell(row=i, column=7).fill = WORK_FILL
        ws.cell(row=i, column=7).number_format = "yyyy-mm-dd" if isinstance(exp.value, date) else "General"
        ws.cell(row=i, column=8, value=f'=IF(G{i}="","",IF(G{i}=F{i},"○","×"))')
        ws.cell(row=i, column=9, value=syntax)
        _set_text(ws.cell(row=i, column=14), answer.replace("{r}", str(i)))
        ws.cell(row=i, column=14).font = HINT_FONT
    for j, (k, v) in enumerate(DRILL_LOOKUP_TABLE[1:], start=2):
        ws.cell(row=j, column=10, value=k)
        c = ws.cell(row=j, column=11, value=v)
        c.number_format = "@"
    for j, v in enumerate(DRILL_LIST[1:], start=2):
        c = ws.cell(row=j, column=13, value=v)
        c.number_format = "@"
    for col, width in zip("ABCDEFGHIJKLMN", (5, 14, 34, 22, 14, 20, 34, 6, 40, 14, 14, 2, 14, 48)):
        ws.column_dimensions[col].width = width


def _steps_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("手順")
    ws.append(["No", "シート", "列", "見出し", "何をするか", "数式（2行目に入れる例）", "構文の読み方", "注意"])
    _style_header(ws, 8)
    for i, s in enumerate(STEPS, start=1):
        ws.append([i, s.sheet, s.col, s.header, s.purpose, "", s.reading.replace("{r}", "2"), s.pitfall])
        _set_text(ws.cell(row=ws.max_row, column=6), formula_for(s, 2))
    ws.append([])
    ws.append(["", "提出", "", "", "書き出し方（値として貼り付け）"])
    ws.cell(row=ws.max_row, column=2).font = Font(bold=True)
    for title, how in EXPORT_STEPS:
        ws.append(["", "提出", "", title, how])
    for col, width in zip("ABCDEFGH", (5, 9, 5, 18, 44, 60, 60, 44)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")


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

    _drill_sheet(wb)
    _steps_sheet(wb)

    for name, rows in (("A_raw", a), ("B_raw", b), ("org_raw", org)):
        sheet = wb.create_sheet(name)
        _write_table(sheet, rows, fill=RAW_FILL)
        sheet.protection.sheet = True  # 原本は書き換えない（パスワードなし）
        sheet.protection.autoFilter = False
        sheet.protection.sort = False

    _write_table(wb.create_sheet("A_work"), a, extra_headers=_work_headers("A_work", len(a[0])))
    _write_table(wb.create_sheet("B_work"), b, extra_headers=_work_headers("B_work", len(b[0])))

    for name, header in (("map_dept", ["部署キー（B_work L列の値）", "組織コード", "根拠・メモ"]),
                         ("map_type", ["雇用形態キー（B_work N列の値）", "雇用区分コード", "根拠・メモ"]),
                         ("matches", ["a_emp_id", "b_user_id"]),
                         ("diffs", ["a_emp_id", "b_user_id", "item", "cause"])):
        sheet = wb.create_sheet(name)
        sheet.append(header)
        _style_header(sheet, len(header))
        for col in range(1, len(header) + 1):
            letter = get_column_letter(col)
            sheet.column_dimensions[letter].width = 28
            for r in range(2, 3001):
                sheet[f"{letter}{r}"].number_format = "@"

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


__all__ = ["build_workbook", "read_sheet", "STEPS"]
