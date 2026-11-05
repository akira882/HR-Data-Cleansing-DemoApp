"""A・B 2システム分の合成人事データ（汚れ入り）と正解表を生成する。

学習用の「仕込み正解（Planted Truth）」方式の中核モジュール。

1. 真実データ（Person）を作る
2. Aシステム（人事給与・SoR）形式と Bシステム（勤怠・ID管理）形式に出力し分ける
3. Bシステム側に汚れを仕込み、仕込んだ内容と「正しい突合結果」を正解表に記録する

生成されるデータはすべて架空であり、実在の人物・組織とは関係ありません。
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

AS_OF = date(2026, 10, 31)  # 突合の基準日
EMAIL_DOMAIN = "example.co.jp"

# --------------------------------------------------------------------------
# マスタ定義
# --------------------------------------------------------------------------
# (組織コード, 現在の正式名称, 人数の重み)
ORGS: list[tuple[str, str, int]] = [
    ("10000000", "経営企画部", 3),
    ("11000000", "人事部", 3),
    ("12000000", "経理部", 3),
    ("13000000", "総務部", 3),
    ("14000000", "情報システム部", 4),
    ("31010100", "法人営業部", 10),
    ("31020100", "個人営業部", 9),
    ("31030100", "海外営業部", 4),
    ("41010100", "開発第一部", 8),
    ("41020100", "開発第二部", 8),
    ("42010100", "品質保証部", 5),
    ("51010100", "東京工場 製造課", 14),
    ("51020100", "大阪工場 製造課", 12),
    ("61010100", "カスタマーサポート部", 9),
    ("71010100", "マーケティング部", 5),
]
ORG_NAME = {code: name for code, name, _ in ORGS}
REORG_DATE = date(2026, 4, 1)
# 2026-04-01 の組織改編で名称が変わった組織（コードは同じ）
ORG_OLD_NAMES = {"31010100": "営業第一部", "31020100": "営業第二部"}
# Bシステムで実際に見られる表記ゆれ・略称
DEPT_VARIANTS = {
    "11000000": ["人事部 "],
    "14000000": ["情シス", "情報ｼｽﾃﾑ部"],
    "42010100": ["品証部"],
    "51010100": ["東京工場製造課", "東京工場　製造課"],
    "51020100": ["大阪工場製造課"],
    "61010100": ["CS部", "ｶｽﾀﾏｰｻﾎﾟｰﾄ部"],
    "71010100": ["ﾏｰｹﾃｨﾝｸﾞ部", "マーケ部"],
}

EMP_TYPES = {"00": "役員", "01": "正社員", "02": "契約社員", "03": "嘱託", "04": "パート", "09": "出向受入"}
EMP_TYPE_VARIANTS = {
    "01": ["正社員　", "正社員(総合職)"],
    "02": ["契約", "ｹｲﾔｸ社員"],
    "03": ["嘱託社員"],
    "04": ["パートタイマー", "ﾊﾟｰﾄ"],
}
STATUS = {"1": "在籍", "2": "休職", "3": "退職"}

SURNAMES = [
    ("佐藤", "sato"), ("鈴木", "suzuki"), ("高橋", "takahashi"), ("田中", "tanaka"), ("伊藤", "ito"),
    ("渡辺", "watanabe"), ("山本", "yamamoto"), ("中村", "nakamura"), ("小林", "kobayashi"), ("加藤", "kato"),
    ("吉田", "yoshida"), ("山田", "yamada"), ("佐々木", "sasaki"), ("山口", "yamaguchi"), ("松本", "matsumoto"),
    ("井上", "inoue"), ("木村", "kimura"), ("林", "hayashi"), ("斎藤", "saito"), ("清水", "shimizu"),
    ("山崎", "yamazaki"), ("森", "mori"), ("池田", "ikeda"), ("橋本", "hashimoto"), ("阿部", "abe"),
    ("石川", "ishikawa"), ("前田", "maeda"), ("藤田", "fujita"), ("後藤", "goto"), ("岡田", "okada"),
    ("長谷川", "hasegawa"), ("村上", "murakami"), ("近藤", "kondo"), ("石井", "ishii"), ("坂本", "sakamoto"),
    ("遠藤", "endo"), ("青木", "aoki"), ("藤井", "fujii"), ("西村", "nishimura"), ("福田", "fukuda"),
]
GIVEN_NAMES = [
    ("翔", "sho"), ("健太", "kenta"), ("大輔", "daisuke"), ("拓也", "takuya"), ("直樹", "naoki"),
    ("誠", "makoto"), ("亮", "ryo"), ("悠斗", "yuto"), ("陽介", "yosuke"), ("和也", "kazuya"),
    ("浩二", "koji"), ("隆", "takashi"), ("修", "osamu"), ("蓮", "ren"), ("大翔", "hiroto"),
    ("花子", "hanako"), ("美咲", "misaki"), ("陽菜", "hina"), ("結衣", "yui"), ("恵", "megumi"),
    ("由美", "yumi"), ("彩", "aya"), ("真由美", "mayumi"), ("優子", "yuko"), ("さくら", "sakura"),
    ("明美", "akemi"), ("愛", "ai"), ("葵", "aoi"), ("千尋", "chihiro"), ("麻衣", "mai"),
]
# 戸籍上の字体（Aシステム）→ Bシステムでの一般的な字体
ITAIJI_VARIANTS = {"高橋": "髙橋", "山崎": "山﨑", "斎藤": "齋藤", "渡辺": "渡邉"}

# --------------------------------------------------------------------------
# 汚れの仕込み計画: dirt_type -> (category, 件数[level1, level2, level3], 説明)
#   category: C=クレンジングで吸収すべき（差異として報告しない）
#             E=入力誤り（差異として報告する） T=タイミング差（報告する）
#             T-ok=許容範囲内のタイミング差（報告しない） S=仕様上の対象外（報告しない）
#             trap=名寄せの罠（それ自体は差異ではない）
# --------------------------------------------------------------------------
DIRT_PLAN: dict[str, tuple[str, tuple[int, int, int], str]] = {
    "name_space_variant": ("C", (10, 20, 30), "氏名の空白ゆれ（全角スペース・空白なし・連続空白・末尾空白）"),
    "itaiji": ("C", (0, -1, -1), "Aは戸籍の字体（髙・﨑・齋・邉）、Bは一般的な字体"),
    "empno_zero_drop": ("C", (5, 15, 25), "B社員番号の先頭ゼロ消失"),
    "email_case": ("C", (0, 10, 15), "Bメールアドレスの大文字混在"),
    "dept_name_variant": ("C", (5, 15, 25), "B部署名の略称・半角カナ・空白ゆれ"),
    "dept_old_name": ("C", (0, 10, 15), "B部署名が組織改編前の旧名称のまま（組織コードは同じ）"),
    "emp_type_label_variant": ("C", (5, 10, 20), "B雇用形態ラベルの表記ゆれ"),
    "date_format_variant": ("C", (0, 10, 15), "B利用開始日の形式ゆれ（和暦・ISO形式）"),
    "start_date_preregistration": ("T-ok", (0, 8, 8), "入社前の事前登録（7日以内は許容）"),
    "scope_excluded": ("S", (-1, -1, -1), "役員・出向者はBの対象外（仕様）"),
    "transfer_not_reflected": ("E", (3, 5, 8), "異動がBに反映されていない"),
    "surname_change_not_reflected": ("E", (2, 3, 5), "改姓がBに反映されていない"),
    "retired_still_active": ("E", (2, 4, 6), "退職者のBアカウントが有効のまま"),
    "leave_marked_inactive": ("E", (0, 2, 3), "休職者のBアカウントが無効にされている（在籍扱いが正）"),
    "emp_type_change_not_reflected": ("E", (0, 2, 4), "契約社員→正社員の登用がBに未反映"),
    "hire_date_typo": ("E", (0, 2, 4), "B利用開始日の年の入力誤り"),
    "empno_missing": ("E", (0, 5, 10), "B社員番号が空欄"),
    "test_or_shared_account": ("E", (1, 2, 3), "テスト用・共用アカウント（人事上の実在者なし）"),
    "new_hire_not_registered": ("T", (3, 3, 3), "月中入社者がまだBに未登録"),
    "rehire_empno_carried_over": ("E", (0, 1, 3), "定年再雇用者のBアカウントが旧社員番号のまま"),
    "same_name_different_person": ("trap", (0, 1, 2), "同姓同名の別人（片方はB社員番号が空欄）"),
}

DIFF_ITEMS = ("a_only", "b_only", "name", "org", "emp_type", "hire_date", "status", "emp_no")


@dataclass
class Person:
    """人事上の真実。1レコード＝1雇用関係（再雇用は別レコード）。"""

    emp_id: str
    last: str
    first: str
    last_romaji: str
    first_romaji: str
    birth: date
    hire: date
    term: date | None
    status: str
    emp_type: str
    org_code: str
    seconded_out: bool = False
    email: str = ""
    human_id: int = 0  # 同一人物（再雇用）を表す内部ID

    @property
    def in_scope(self) -> bool:
        """突合対象（在籍・休職、役員でない、出向中でない）か。"""
        return self.status in ("1", "2") and self.emp_type != "00" and not self.seconded_out


@dataclass
class GeneratedData:
    persons: list[Person]
    b_rows: list[dict]
    answer_key: list[dict]
    expected_matches: list[dict]
    expected_diffs: list[dict]
    seed: int
    level: int
    meta: dict = field(default_factory=dict)


def _last_day_of_month(y: int, m: int) -> date:
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return nxt - timedelta(days=1)


def _shift_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 2/29
        return d.replace(year=d.year + years, day=28)


def to_wareki(d: date) -> str:
    """和暦の略記（例: H30.4.1, R2.4.1）。"""
    if d >= date(2019, 5, 1):
        return f"R{d.year - 2018}.{d.month}.{d.day}"
    if d >= date(1989, 1, 8):
        return f"H{d.year - 1988}.{d.month}.{d.day}"
    return f"S{d.year - 1925}.{d.month}.{d.day}"


class _Builder:
    def __init__(self, seed: int, level: int):
        if level not in (1, 2, 3):
            raise ValueError("level は 1〜3 で指定してください")
        self.rng = random.Random(seed)
        self.seed = seed
        self.level = level
        self.human_seq = 0
        self.persons: list[Person] = []
        self.b_rows: list[dict] = []
        self.answer_key: list[dict] = []
        self.expected_diffs: list[dict] = []
        self.dirty: set[tuple[str, str]] = set()  # (user_id, item) 汚し済み
        self.e_used: set[str] = set()  # E系の汚れを入れた user_id
        self.dirt_seq = 0

    # ---------------- 計画 ----------------
    def count(self, dirt_type: str) -> int:
        return DIRT_PLAN[dirt_type][1][self.level - 1]

    # ---------------- 人の生成 ----------------
    def _name(self) -> tuple[str, str, str, str]:
        last, last_r = self.rng.choice(SURNAMES)
        first, first_r = self.rng.choice(GIVEN_NAMES)
        if last in ITAIJI_VARIANTS and self.level >= 2 and self.rng.random() < 0.3:
            last = ITAIJI_VARIANTS[last]
        return last, first, last_r, first_r

    def _org(self) -> str:
        codes = [c for c, _, _ in ORGS if c != "10000000"]
        weights = [w for c, _, w in ORGS if c != "10000000"]
        return self.rng.choices(codes, weights)[0]

    def _new_person(self, *, emp_type: str, status: str, age_range: tuple[int, int],
                    hire: date | None = None, term: date | None = None, org: str | None = None) -> Person:
        rng = self.rng
        ref = term or AS_OF
        age = rng.randint(*age_range)
        birth = _shift_years(ref, -age) - timedelta(days=rng.randint(1, 364))
        if hire is None:
            earliest = max(_shift_years(birth, 22), date(1990, 4, 1))
            latest = min(ref - timedelta(days=30), date(2026, 10, 1))
            if earliest > latest:
                earliest = latest
            y = rng.randint(earliest.year, latest.year)
            if rng.random() < 0.6:
                hire = date(y, 4, 1)
            else:
                hire = date(y, rng.randint(1, 12), 1)
            hire = min(max(hire, earliest.replace(day=1)), latest.replace(day=1))
        last, first, last_r, first_r = self._name()
        self.human_seq += 1
        p = Person("", last, first, last_r, first_r, birth, hire, term, status, emp_type,
                   org or self._org(), human_id=self.human_seq)
        self.persons.append(p)
        return p

    def build_population(self) -> None:
        rng = self.rng
        # 役員
        for _ in range(10):
            self._new_person(emp_type="00", status="1", age_range=(52, 64), org="10000000")
        # 一般の在籍者
        n_regular = 1000 - 10 - self.count("new_hire_not_registered") - self.count("rehire_empno_carried_over") - 8
        types = ["01", "02", "03", "04", "09"]
        for _ in range(n_regular):
            t = rng.choices(types, [75, 12, 5, 6, 2])[0]
            age_range = (60, 64) if t == "03" else (22, 59)
            self._new_person(emp_type=t, status="1", age_range=age_range)
        regular = [p for p in self.persons if p.emp_type != "00"]
        for p in rng.sample(regular, 15):
            p.seconded_out = True
        for p in rng.sample([p for p in regular if not p.seconded_out], 20):
            p.status = "2"
        # 10/1 入社（事前登録の対象）
        for _ in range(8):
            self._new_person(emp_type=rng.choice(["01", "02"]), status="1", age_range=(22, 40), hire=date(2026, 10, 1))
        # 10/16 入社（Bに未登録＝タイミング差）
        self.new_hires = [
            self._new_person(emp_type=rng.choice(["01", "02"]), status="1", age_range=(23, 40), hire=date(2026, 10, 16))
            for _ in range(self.count("new_hire_not_registered"))
        ]
        # 直近13か月の退職者
        for _ in range(90):
            y, m = rng.choice([(2025, 10), (2025, 11), (2025, 12)] + [(2026, mm) for mm in range(1, 11)])
            self._new_person(emp_type=rng.choices(types[:4], [80, 12, 4, 4])[0], status="3",
                             age_range=(23, 59), term=_last_day_of_month(y, m))
        # 定年再雇用（旧レコード: 退職、新レコード: 嘱託として在籍）
        self.rehires: list[tuple[Person, Person]] = []
        for _ in range(self.count("rehire_empno_carried_over")):
            old = self._new_person(emp_type="01", status="3", age_range=(60, 60), term=date(2026, 3, 31))
            new = Person("", old.last, old.first, old.last_romaji, old.first_romaji, old.birth,
                         date(2026, 4, 1), None, "1", "03", old.org_code, human_id=old.human_id)
            self.persons.append(new)
            self.rehires.append((old, new))
        # 同姓同名の別人
        self.same_name_pairs: list[tuple[Person, Person]] = []
        pool = [p for p in self.persons if p.in_scope and p.emp_type in ("01", "02")
                and p not in self.new_hires and p.hire < date(2026, 1, 1)]
        picks = rng.sample(pool, self.count("same_name_different_person") * 2)
        for a, b in zip(picks[::2], picks[1::2]):
            b.last, b.first, b.last_romaji, b.first_romaji = a.last, a.first, a.last_romaji, a.first_romaji
            self.same_name_pairs.append((a, b))
        self._assign_ids_and_emails()

    def _assign_ids_and_emails(self) -> None:
        order = sorted(self.persons, key=lambda p: (p.hire, self.rng.random()))
        n = 100
        for p in order:
            n += self.rng.randint(1, 2)
            p.emp_id = f"{n:06d}"
        used: dict[str, int] = {}
        by_human: dict[int, str] = {}
        for p in order:
            if p.human_id in by_human:  # 再雇用は同じメールを引き継ぐ
                p.email = by_human[p.human_id]
                continue
            base = f"{p.first_romaji}.{p.last_romaji}"
            used[base] = used.get(base, 0) + 1
            local = base if used[base] == 1 else f"{base}{used[base]}"
            p.email = f"{local}@{EMAIL_DOMAIN}"
            by_human[p.human_id] = p.email

    # ---------------- Bシステムの生成 ----------------
    def build_b(self) -> None:
        rng = self.rng
        rehire_new = {new.emp_id: old for old, new in self.rehires}
        rehire_old_ids = {old.emp_id for old, _ in self.rehires}
        new_hire_ids = {p.emp_id for p in self.new_hires}
        rows = []
        for p in self.persons:
            if p.emp_id in rehire_old_ids or p.emp_id in new_hire_ids:
                continue
            if p.status == "3":
                if rng.random() > 0.7:  # 退職者のアカウント削除済み
                    continue
                active = "0"
            elif p.in_scope:
                active = "1"
            else:
                continue  # 役員・出向中は対象外
            last_b = {v: k for k, v in ITAIJI_VARIANTS.items()}.get(p.last, p.last)
            rows.append({
                "user_id": "", "emp_no": p.emp_id, "name": f"{last_b} {p.first}",
                "dept": ORG_NAME[p.org_code], "emp_type": EMP_TYPES[p.emp_type],
                "start_date": p.hire, "start_date_text": None, "active": active,
                "email": p.email, "_a_emp_id": p.emp_id, "_person": p,
            })
            if p.emp_id in rehire_new:  # 旧アカウントを引き継いでいる
                old = rehire_new[p.emp_id]
                rows[-1]["emp_no"] = old.emp_id
                rows[-1]["start_date"] = old.hire
        rng.shuffle(rows)
        for i, r in enumerate(rows, start=1):
            r["user_id"] = f"E{10000 + i * 3:05d}"
        self.b_rows = rows

    # ---------------- 正解表への記録 ----------------
    def _record(self, dirt_type: str, *, a_emp_id: str = "", b_user_id: str = "", item: str = "",
                true_value: str = "", observed_value: str = "", note: str = "",
                diff_item: str | None = None, diff_category: str | None = None) -> None:
        self.dirt_seq += 1
        dirt_id = f"D{self.dirt_seq:04d}"
        category = DIRT_PLAN[dirt_type][0]
        self.answer_key.append({
            "dirt_id": dirt_id, "dirt_type": dirt_type, "category": category,
            "a_emp_id": a_emp_id, "b_user_id": b_user_id, "item": item,
            "true_value": true_value, "observed_value": observed_value,
            "note": note or DIRT_PLAN[dirt_type][2],
        })
        if diff_item:
            self.expected_diffs.append({
                "a_emp_id": a_emp_id if diff_item != "b_only" else "",
                "b_user_id": b_user_id if diff_item != "a_only" else "",
                "item": diff_item, "category": diff_category or category,
                "dirt_id": dirt_id, "dirt_type": dirt_type,
            })

    def _pick_rows(self, n: int, item: str, cond=lambda r: True, exclusive: bool = False) -> list[dict]:
        cands = [r for r in self.b_rows if r["_person"] is not None and (r["user_id"], item) not in self.dirty
                 and (not exclusive or r["user_id"] not in self.e_used) and cond(r)]
        picks = self.rng.sample(cands, min(n, len(cands)))
        for r in picks:
            self.dirty.add((r["user_id"], item))
            if exclusive:
                self.e_used.add(r["user_id"])
        return picks

    # ---------------- 汚れの仕込み ----------------
    def plant(self) -> None:
        rng = self.rng
        active_row = lambda r: r["active"] == "1" and r["_person"].status == "1"  # noqa: E731
        special = {p.emp_id for pair in self.same_name_pairs for p in pair} | {n.emp_id for _, n in self.rehires}
        normal = lambda r: active_row(r) and r["_a_emp_id"] not in special  # noqa: E731

        # --- 仕様差（S）と構造的なケース ---
        for p in self.persons:
            if p.status in ("1", "2") and not p.in_scope:
                self._record("scope_excluded", a_emp_id=p.emp_id, item="a_only",
                             note="役員（Bの対象外）" if p.emp_type == "00" else "出向中（Bの対象外）")
        for p in self.new_hires:
            self._record("new_hire_not_registered", a_emp_id=p.emp_id, item="a_only",
                         true_value=p.hire.isoformat(), diff_item="a_only")
        for old, new in self.rehires:
            row = next(r for r in self.b_rows if r["_a_emp_id"] == new.emp_id)
            for item in ("emp_no", "hire_date"):
                self.dirty.add((row["user_id"], item))
            self.e_used.add(row["user_id"])
            self._record("rehire_empno_carried_over", a_emp_id=new.emp_id, b_user_id=row["user_id"], item="emp_no",
                         true_value=new.emp_id, observed_value=old.emp_id,
                         note=f"旧社員番号 {old.emp_id}（2026-03-31 定年退職）のまま。正しい突合先は新社員番号",
                         diff_item="emp_no")
            self.expected_diffs.append({"a_emp_id": new.emp_id, "b_user_id": row["user_id"], "item": "hire_date",
                                        "category": "E", "dirt_id": self.answer_key[-1]["dirt_id"],
                                        "dirt_type": "rehire_empno_carried_over"})
        for a, b in self.same_name_pairs:
            row = next(r for r in self.b_rows if r["_a_emp_id"] == b.emp_id)
            self.dirty.add((row["user_id"], "emp_no"))
            self.e_used.add(row["user_id"])
            row["emp_no"] = ""
            self._record("same_name_different_person", a_emp_id=b.emp_id, b_user_id=row["user_id"], item="emp_no",
                         true_value=b.emp_id, observed_value="",
                         note=f"{a.emp_id} と同姓同名の別人。B社員番号が空欄のため、氏名だけで突合すると誤統合する",
                         diff_item="emp_no", diff_category="E")

        # --- 入力誤り（E） ---
        for r in self._pick_rows(self.count("transfer_not_reflected"), "org", normal, exclusive=True):
            p = r["_person"]
            other = rng.choice([c for c, _, _ in ORGS if c not in (p.org_code, "10000000")])
            r["dept"] = ORG_NAME[other]
            self._record("transfer_not_reflected", a_emp_id=p.emp_id, b_user_id=r["user_id"], item="org",
                         true_value=p.org_code, observed_value=other, diff_item="org")
        for r in self._pick_rows(self.count("surname_change_not_reflected"), "name", normal, exclusive=True):
            p = r["_person"]
            old_last = r["name"].split(" ")[0]
            new_last = rng.choice([s for s, _ in SURNAMES if s != old_last and s not in ITAIJI_VARIANTS])
            p.last = new_last  # Aは改姓後。Bとメールアドレスは旧姓のまま
            self._record("surname_change_not_reflected", a_emp_id=p.emp_id, b_user_id=r["user_id"], item="name",
                         true_value=f"{new_last} {p.first}", observed_value=r["name"], diff_item="name")
        retired = lambda r: r["_person"].status == "3"  # noqa: E731
        for r in self._pick_rows(self.count("retired_still_active"), "status", retired, exclusive=True):
            r["active"] = "1"
            p = r["_person"]
            self._record("retired_still_active", a_emp_id=p.emp_id, b_user_id=r["user_id"], item="status",
                         true_value="0", observed_value="1",
                         note=f"退職日 {p.term.isoformat()}。アカウントが有効のまま（セキュリティ上の最優先事項）",
                         diff_item="status")
        on_leave = lambda r: r["_person"].status == "2"  # noqa: E731
        for r in self._pick_rows(self.count("leave_marked_inactive"), "status", on_leave, exclusive=True):
            r["active"] = "0"
            self._record("leave_marked_inactive", a_emp_id=r["_a_emp_id"], b_user_id=r["user_id"], item="status",
                         true_value="1", observed_value="0", diff_item="status")
        seishain = lambda r: normal(r) and r["_person"].emp_type == "01"  # noqa: E731
        for r in self._pick_rows(self.count("emp_type_change_not_reflected"), "emp_type", seishain, exclusive=True):
            r["emp_type"] = "契約社員"
            self._record("emp_type_change_not_reflected", a_emp_id=r["_a_emp_id"], b_user_id=r["user_id"],
                         item="emp_type", true_value="01", observed_value="契約社員", diff_item="emp_type")
        for r in self._pick_rows(self.count("hire_date_typo"), "hire_date", normal, exclusive=True):
            wrong = _shift_years(r["start_date"], -1)
            self._record("hire_date_typo", a_emp_id=r["_a_emp_id"], b_user_id=r["user_id"], item="hire_date",
                         true_value=r["start_date"].isoformat(), observed_value=wrong.isoformat(),
                         diff_item="hire_date")
            r["start_date"] = wrong
        for r in self._pick_rows(self.count("empno_missing"), "emp_no", normal, exclusive=True):
            self._record("empno_missing", a_emp_id=r["_a_emp_id"], b_user_id=r["user_id"], item="emp_no",
                         true_value=r["emp_no"], observed_value="", diff_item="emp_no")
            r["emp_no"] = ""
        test_names = ["テスト ユーザー", "共用 受付", "研修 用", "管理者 一時"]
        for i in range(self.count("test_or_shared_account")):
            uid = f"T{i + 1:04d}"
            self.b_rows.append({
                "user_id": uid, "emp_no": "", "name": test_names[i % len(test_names)], "dept": "情報システム部",
                "emp_type": "", "start_date": date(2025, 4, 1), "start_date_text": None, "active": "1",
                "email": f"test{i + 1:02d}@{EMAIL_DOMAIN}", "_a_emp_id": None, "_person": None,
            })
            self._record("test_or_shared_account", b_user_id=uid, item="b_only", observed_value=uid,
                         diff_item="b_only")

        # --- 許容範囲内のタイミング差（T-ok） ---
        oct_hires = lambda r: r["_person"].hire == date(2026, 10, 1)  # noqa: E731
        for r in self._pick_rows(self.count("start_date_preregistration"), "hire_date", oct_hires):
            new_start = r["start_date"] - timedelta(days=rng.randint(1, 7))
            self._record("start_date_preregistration", a_emp_id=r["_a_emp_id"], b_user_id=r["user_id"],
                         item="hire_date", true_value=r["start_date"].isoformat(),
                         observed_value=new_start.isoformat())
            r["start_date"] = new_start

        # --- クレンジングで吸収すべき汚れ（C） ---
        has_person = lambda r: True  # noqa: E731
        for r in self.b_rows:
            p = r["_person"]
            if p is not None and p.last in ITAIJI_VARIANTS.values() and (r["user_id"], "name") not in self.dirty:
                self._record("itaiji", a_emp_id=p.emp_id, b_user_id=r["user_id"], item="name",
                             true_value=f"{p.last} {p.first}", observed_value=r["name"])
        for r in self._pick_rows(self.count("name_space_variant"), "name", has_person):
            before = r["name"]
            r["name"] = rng.choice([before.replace(" ", "　"), before.replace(" ", ""),
                                    before.replace(" ", "  "), before + " "])
            self._record("name_space_variant", a_emp_id=r["_a_emp_id"], b_user_id=r["user_id"], item="name",
                         true_value=before, observed_value=r["name"])
        with_zero = lambda r: r["emp_no"].startswith("0")  # noqa: E731
        for r in self._pick_rows(self.count("empno_zero_drop"), "emp_no", with_zero):
            before = r["emp_no"]
            r["emp_no"] = before.lstrip("0")
            self._record("empno_zero_drop", a_emp_id=r["_a_emp_id"], b_user_id=r["user_id"], item="emp_no",
                         true_value=before, observed_value=r["emp_no"])
        for r in self._pick_rows(self.count("email_case"), "email", has_person):
            before = r["email"]
            local, domain = before.split("@")
            r["email"] = rng.choice([local.title(), local.upper()]) + "@" + domain
            self._record("email_case", a_emp_id=r["_a_emp_id"], b_user_id=r["user_id"], item="email",
                         true_value=before, observed_value=r["email"])
        variant_org = lambda r: r["_person"].org_code in DEPT_VARIANTS and r["dept"] == ORG_NAME[r["_person"].org_code]  # noqa: E731,E501
        for r in self._pick_rows(self.count("dept_name_variant"), "org", variant_org):
            before = r["dept"]
            r["dept"] = rng.choice(DEPT_VARIANTS[r["_person"].org_code])
            self._record("dept_name_variant", a_emp_id=r["_a_emp_id"], b_user_id=r["user_id"], item="org",
                         true_value=before, observed_value=r["dept"])
        renamed = lambda r: r["_person"].org_code in ORG_OLD_NAMES and r["_person"].hire < REORG_DATE and r["dept"] == ORG_NAME[r["_person"].org_code]  # noqa: E731,E501
        for r in self._pick_rows(self.count("dept_old_name"), "org", renamed):
            before = r["dept"]
            r["dept"] = ORG_OLD_NAMES[r["_person"].org_code]
            self._record("dept_old_name", a_emp_id=r["_a_emp_id"], b_user_id=r["user_id"], item="org",
                         true_value=before, observed_value=r["dept"])
        variant_type = lambda r: r["emp_type"] in [EMP_TYPES[k] for k in EMP_TYPE_VARIANTS]  # noqa: E731
        for r in self._pick_rows(self.count("emp_type_label_variant"), "emp_type", variant_type):
            code = next(k for k, v in EMP_TYPES.items() if v == r["emp_type"])
            before = r["emp_type"]
            r["emp_type"] = rng.choice(EMP_TYPE_VARIANTS[code])
            self._record("emp_type_label_variant", a_emp_id=r["_a_emp_id"], b_user_id=r["user_id"],
                         item="emp_type", true_value=before, observed_value=r["emp_type"])
        for r in self._pick_rows(self.count("date_format_variant"), "hire_date_format", has_person):
            d = r["start_date"]
            r["start_date_text"] = rng.choice([to_wareki(d), d.isoformat()])
            self._record("date_format_variant", a_emp_id=r["_a_emp_id"], b_user_id=r["user_id"],
                         item="hire_date", true_value=d.isoformat(), observed_value=r["start_date_text"])

    def expected_matches(self) -> list[dict]:
        return sorted(
            ({"a_emp_id": r["_a_emp_id"], "b_user_id": r["user_id"]} for r in self.b_rows if r["_a_emp_id"]),
            key=lambda m: m["a_emp_id"],
        )


def generate(seed: int = 42, level: int = 2) -> GeneratedData:
    """合成データ一式をメモリ上に生成する。同じ seed・level なら常に同じ結果になる。"""
    b = _Builder(seed, level)
    b.build_population()
    b.build_b()
    b.plant()
    return GeneratedData(
        persons=b.persons, b_rows=b.b_rows, answer_key=b.answer_key,
        expected_matches=b.expected_matches(),
        expected_diffs=sorted(b.expected_diffs, key=lambda d: (d["item"], d["a_emp_id"], d["b_user_id"])),
        seed=seed, level=level,
    )


# --------------------------------------------------------------------------
# ファイル出力
# --------------------------------------------------------------------------
A_COLUMNS = ["社員番号", "姓", "名", "生年月日", "入社年月日", "退職年月日", "在籍区分", "雇用区分",
             "組織コード", "組織名", "出向区分", "メールアドレス"]
B_COLUMNS = ["ユーザーID", "社員番号", "氏名", "部署", "雇用形態", "利用開始日", "有効", "メールアドレス"]


def _ymd(d: date | None) -> str:
    return d.strftime("%Y%m%d") if d else ""


def _write_csv(path: Path, header: list[str], rows: list[list[str]] | list[dict], encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as f:
        if rows and isinstance(rows[0], dict):
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(rows)
        else:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_outputs(data: GeneratedData, out_dir: Path, key_dir: Path) -> dict:
    """受領ファイル（out_dir）と正解表（key_dir）を書き出し、マニフェストを返す。"""
    persons = sorted(data.persons, key=lambda p: p.emp_id)
    a_rows = [[p.emp_id, p.last, p.first, _ymd(p.birth), _ymd(p.hire), _ymd(p.term), p.status, p.emp_type,
               p.org_code, ORG_NAME[p.org_code], "1" if p.seconded_out else "0", p.email] for p in persons]
    org_rows = []
    for code, name, _ in ORGS:
        if code in ORG_OLD_NAMES:
            org_rows.append([code, ORG_OLD_NAMES[code], "20150401", "20260331"])
            org_rows.append([code, name, _ymd(REORG_DATE), "99991231"])
        else:
            org_rows.append([code, name, "20150401", "99991231"])
    b_rows = []
    for r in sorted(data.b_rows, key=lambda r: r["user_id"]):
        d = r["start_date"]
        text = r["start_date_text"] or f"{d.year}/{d.month}/{d.day}"
        b_rows.append([r["user_id"], r["emp_no"], r["name"], r["dept"], r["emp_type"], text, r["active"], r["email"]])

    files = {
        "system_a_employees.csv": (out_dir, A_COLUMNS, a_rows, "cp932"),
        "system_a_org_master.csv": (out_dir, ["組織コード", "組織名", "有効開始日", "有効終了日"], org_rows, "cp932"),
        "system_b_users.csv": (out_dir, B_COLUMNS, b_rows, "utf-8-sig"),
        "answer_key.csv": (key_dir, list(data.answer_key[0].keys()), data.answer_key, "utf-8-sig"),
        "expected_matches.csv": (key_dir, ["a_emp_id", "b_user_id"], data.expected_matches, "utf-8-sig"),
        "expected_diffs.csv": (key_dir, ["a_emp_id", "b_user_id", "item", "category", "dirt_id", "dirt_type"],
                               data.expected_diffs, "utf-8-sig"),
    }
    manifest = {"seed": data.seed, "level": data.level, "as_of": AS_OF.isoformat(),
                "a_records": len(a_rows), "b_records": len(b_rows),
                "planted": len(data.answer_key), "expected_diffs": len(data.expected_diffs), "files": {}}
    for name, (d, header, rows, enc) in files.items():
        path = d / name
        _write_csv(path, header, rows, enc)
        manifest["files"][name] = _sha256(path)
    (key_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # 受領側にも「抽出依頼書の控え」として件数だけを置く（正解は含めない）
    receipt = {"as_of": AS_OF.isoformat(), "system_a_employees.csv": len(a_rows), "system_b_users.csv": len(b_rows)}
    (out_dir / "control_totals.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
