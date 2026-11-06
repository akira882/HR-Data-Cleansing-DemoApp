"""練習用ブックの数式を、表計算ソフト（LibreOffice）で実際に計算して検証するための補助関数。

この環境の LibreOffice（24.2）は XLOOKUP に対応していないため、検証時だけ
XLOOKUP(値, 探す範囲, 返す範囲, 既定値) を IFERROR(INDEX(返す範囲, MATCH(値, 探す範囲, 0)), 既定値) に置き換える。
（完全一致・見つからないときの既定値という点で同じ動きをする）
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from openpyxl import load_workbook

from src.training.ab_generator import DEPT_VARIANTS, EMP_TYPE_VARIANTS, EMP_TYPES, ORG_OLD_NAMES, ORGS
from src.training.formulas import FUNCTION_DRILLS, formula_for, steps_for


def _split_args(s: str) -> list[str]:
    args, depth, quote, cur = [], 0, False, ""
    for ch in s:
        if ch == '"':
            quote = not quote
        if not quote:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                args.append(cur)
                cur = ""
                continue
        cur += ch
    args.append(cur)
    return args


def xlookup_to_index_match(f: str) -> str:
    while "XLOOKUP(" in f:
        start = f.index("XLOOKUP(")
        i, depth, quote = start + len("XLOOKUP("), 1, False
        while depth:
            ch = f[i]
            if ch == '"':
                quote = not quote
            elif not quote and ch == "(":
                depth += 1
            elif not quote and ch == ")":
                depth -= 1
            i += 1
        v, look, ret, default = _split_args(f[start + len("XLOOKUP("):i - 1])
        f = f[:start] + f"IFERROR(INDEX({ret},MATCH({v},{look},0)),{default})" + f[i:]
    return f


def _key(s: str) -> str:
    return s.replace(" ", "").replace("　", "")


def correct_maps() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    dept = {}
    for code, name, _ in ORGS:
        dept[_key(name)] = code
    for code, old in ORG_OLD_NAMES.items():
        dept[_key(old)] = code
    for code, variants in DEPT_VARIANTS.items():
        for v in variants:
            dept[_key(v)] = code
    types = {_key(label): code for code, label in EMP_TYPES.items() if code != "00"}
    for code, variants in EMP_TYPE_VARIANTS.items():
        for v in variants:
            types[_key(v)] = code
    return sorted(dept.items()), sorted(types.items())


def fill_model_answers(xlsx: Path) -> None:
    """学習者が手順どおりに入力した状態を再現する（検証用の数式に置き換えて）。"""
    wb = load_workbook(xlsx)
    for sheet in ("A_work", "B_work"):
        ws = wb[sheet]
        for step in steps_for(sheet):
            for r in range(2, ws.max_row + 1):
                ws[f"{step.col}{r}"] = xlookup_to_index_match(formula_for(step, r))
    dept, types = correct_maps()
    for name, rows in (("map_dept", dept), ("map_type", types)):
        for i, (k, v) in enumerate(rows, start=2):
            wb[name].cell(row=i, column=1, value=k)
            wb[name].cell(row=i, column=2, value=v)
    drill = wb["関数ドリル"]
    for i, d in enumerate(FUNCTION_DRILLS, start=2):
        drill.cell(row=i, column=7, value=xlookup_to_index_match(d[6].replace("{r}", str(i))))
    wb.save(xlsx)


def recalc(xlsx: Path, out_dir: Path) -> Path:
    """LibreOffice で開いて再計算し、計算結果入りの xlsx を out_dir に保存する。"""
    soffice = shutil.which("soffice")
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = (out_dir / "lo_profile").resolve()
    subprocess.run([soffice, f"-env:UserInstallation=file://{profile}", "--headless", "--calc", "--convert-to",
                    "xlsx:Calc MS Excel 2007 XML", "--outdir", str(out_dir), str(xlsx)],
                   check=True, capture_output=True, timeout=600)
    return out_dir / xlsx.name


def export_submission(recalculated: Path, target: Path) -> None:
    """手順シートの「提出」の書き出し方を、そのまま機械的に行う。"""
    wb = load_workbook(recalculated, data_only=True)
    a_ws, b_ws = wb["A_work"], wb["B_work"]
    out = load_workbook(target)
    m_ws, d_ws = out["matches"], out["diffs"]
    m_row = d_row = 2
    for r in range(2, b_ws.max_row + 1):
        uid, dest = b_ws[f"A{r}"].value, b_ws[f"W{r}"].value
        if dest:
            m_ws.cell(row=m_row, column=1, value=str(dest))
            m_ws.cell(row=m_row, column=2, value=uid)
            m_row += 1
        for col in ("Z", "AA", "AB", "AC", "AD", "AE"):
            item = b_ws[f"{col}{r}"].value
            if item:
                for c, v in enumerate((str(dest), uid, item), start=1):
                    d_ws.cell(row=d_row, column=c, value=v)
                d_row += 1
        if b_ws[f"AF{r}"].value == "b_only":
            d_ws.cell(row=d_row, column=2, value=uid)
            d_ws.cell(row=d_row, column=3, value="b_only")
            d_row += 1
    for r in range(2, a_ws.max_row + 1):
        if a_ws[f"S{r}"].value == "a_only":
            d_ws.cell(row=d_row, column=1, value=a_ws[f"A{r}"].value)
            d_ws.cell(row=d_row, column=3, value="a_only")
            d_row += 1
    out.save(target)


def drill_results(recalculated: Path) -> list[str]:
    ws = load_workbook(recalculated, data_only=True)["関数ドリル"]
    return [ws.cell(row=i, column=8).value for i in range(2, len(FUNCTION_DRILLS) + 2)]
