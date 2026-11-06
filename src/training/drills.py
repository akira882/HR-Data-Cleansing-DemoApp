"""スマホ用「判断ドリル」の問題を、合成データ生成器の正解表から作る。

PCの練習（仕組みを作る）とスマホの練習（判断を鍛える）が、同じ汚れのパターンを扱うようにするため、
問題は手書きせず、生成器が仕込んだ汚れと正解からつくる。原則問題だけは手書き。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from src.training.ab_generator import EMP_TYPES, ORG_NAME, STATUS, generate

PRINCIPLES = {
    "P1": ("人事データには正解がある", "所属・入社日・雇用区分の正解は、発令書や雇用契約という一次資料にある。確認できるのに推測で埋めるのは判断の放棄。"),
    "P2": ("用途で処理が変わる", "給与・アカウントなどの運用用途は1件ずつ正しくなければならない。分析用途は全体の偏りがなければよい。"),
    "P3": ("汚れの正体は時間", "「いつから有効か（発令日）」と「いつ入力されたか」のズレが差異の多くを生む。上書きすると当時の正解を証明できなくなる。"),
    "P4": ("社員番号は雇用関係の番号", "再雇用・転籍では同じ人に別の番号が付く。「人のキー」と「雇用のキー」を分けて考える。"),
    "P5": ("誤りのコストは非対称", "別人を同一人物とみなす誤り（誤統合）は致命的。同一人物を別人とみなす誤りは手間が増えるだけ。自動化は検出まで、確定は人。"),
    "P6": ("空欄も情報", "空欄には「不明」「該当なし」「まだ来ていない」「入力漏れ」の少なくとも4つの意味がある。"),
    "P7": ("ありえない値と珍しい値は別物", "退職日が入社日より前なら誤り。年収3,000万円は珍しいだけ。人事の外れ値は重要な人であることが多い。"),
    "P8": ("ルール集は上流の欠陥リスト", "表記ゆれを下流で直し続けるのは税金。ルールを上流の改善要望として使い、クレンジング自体を不要にする。"),
    "P9": ("変換はすべて業務判断", "「休職者を在籍に含める」は人事の方針。責任者を明示し、記録を残し、元に戻せるようにする。"),
}

# 項目ごとの吸収すべき汚れ（C / T-ok）の解説
C_EXPLAIN = {
    "name_space_variant": ("name", "氏名の空白の違いは表記ゆれ。空白を除いて比較すれば一致するので報告しない。"),
    "itaiji": ("name", "髙と高などは異体字。比較用のキーでは同じ字に寄せる（原文の字体は残す）。"),
    "empno_zero_drop": ("emp_no", "社員番号の先頭ゼロが消えただけ。6桁にそろえれば一致する。Excelで開いたときによく起きる。"),
    "email_case": ("email", "メールアドレスの大文字・小文字は区別しない。比較しない項目でもある。"),
    "dept_name_variant": ("org", "部署名の略称・半角カナ・空白ゆれ。変換表で組織コードにすれば一致する。"),
    "dept_old_name": ("org", "2026-04-01の組織改編前の名称。組織コードは同じなので一致扱い（旧名称が残っていること自体は改善要望の対象）。"),
    "emp_type_label_variant": ("emp_type", "雇用形態ラベルの表記ゆれ。コードに変換すれば一致する。"),
    "date_format_variant": ("hire_date", "和暦・ISO形式など日付の書き方の違い。日付として解釈すれば一致する。"),
    "start_date_preregistration": ("hire_date", "入社日の7日前以内の事前登録は仕様で許容。報告しない。"),
}
E_EXPLAIN = {
    "transfer_not_reflected": "所属の組織コードが違う。異動がBに反映されていない（Aが正）。",
    "surname_change_not_reflected": "姓が違うが、社員番号とメールは一致している。改姓がBに反映されていない。",
    "retired_still_active": "Aでは退職なのに、Bのアカウントが有効のまま。セキュリティ上の最優先事項。",
    "leave_marked_inactive": "休職者は在籍扱いなので、Bは有効が正しい（仕様）。",
    "emp_type_change_not_reflected": "契約社員から正社員への登用がBに反映されていない。",
    "hire_date_typo": "利用開始日が入社日と1年ずれている。許容差（7日）を超えるので報告する。",
    "empno_missing": "B社員番号が空欄。メールで結合できても、空欄そのものを報告して入力を依頼する。",
    "rehire_empno_carried_over": "定年再雇用者のBアカウントが旧社員番号・旧利用開始日のまま。",
    "same_name_different_person": "B社員番号が空欄。同姓同名の別人がいるので、氏名だけで結合すると誤統合になる。",
}
ITEM_LABEL = {"name": "氏名", "org": "所属", "emp_type": "雇用区分", "hire_date": "入社日／利用開始日",
              "status": "在籍／有効", "emp_no": "社員番号", "none": "報告する差異はない"}

# 「次の一手」問題: dirt_type -> (問い, [(選択肢, 正解か)], 解説, 原則)
ACTIONS = {
    "transfer_not_reflected": (
        "所属が一致しません。最も適切な対応はどれですか。",
        [("Aの異動発令（発令日・発令番号）を確認し、Bの管理者に所属の修正を依頼する", True),
         ("Bのほうが新しい情報かもしれないので、Aの所属をBに合わせる", False),
         ("部署名の表記ゆれとして変換表に追加する", False),
         ("翌月には直るはずなので、記録せずに様子を見る", False)],
        "正とするのはA。根拠（発令）を添えて、正でない側の修正を依頼する。組織コードが違うので表記ゆれではない。",
        "P1"),
    "surname_change_not_reflected": (
        "姓だけが一致しません（社員番号・メールは一致）。最も適切な対応はどれですか。",
        [("Aの改姓の届出を確認し、Bの氏名変更を依頼する（旧姓使用の申請がないかも確認する）", True),
         ("姓が違うので別人と判断し、結合を外す", False),
         ("Aの氏名をBに合わせて旧姓に戻す", False),
         ("氏名は比較しなくてよい項目なので対応不要", False)],
        "社員番号とメールが一致しているので同一人物。改姓の反映漏れ。ただし会社によっては旧姓使用を認めているので、申請の有無を確認してから依頼する。",
        "P5"),
    "retired_still_active": (
        "Aでは退職済みなのに、Bのアカウントが有効です。最も適切な対応はどれですか。",
        [("Bの管理者に即日の無効化を依頼し、退職日以降のログイン履歴の確認も依頼する", True),
         ("タイミング差なので、翌月の突合で解消を確認する", False),
         ("自分でBのアカウントを削除する", False),
         ("Aの退職日が誤っている可能性が高いので、Aを修正する", False)],
        "退職者がログインできる状態は情報漏えいのリスク。最優先で無効化を依頼する。アナリストが自分でシステムを直さないのは職務分掌のため。",
        "P5"),
    "leave_marked_inactive": (
        "Aでは休職中の社員のBアカウントが無効になっています。最も適切な対応はどれですか。",
        [("突合仕様（休職者は有効）を確認し、Bの管理者に有効化を依頼する。復職予定日も確認する", True),
         ("休職中は使わないので無効が正しい。対応不要", False),
         ("Aの在籍区分を退職に変更する", False),
         ("Bのみの問題なので報告しない", False)],
        "休職者を在籍に含めるかは会社の方針で、この突合仕様では「有効」。方針と違う状態は差異として報告する。",
        "P9"),
    "emp_type_change_not_reflected": (
        "Aは正社員、Bは契約社員です。最も適切な対応はどれですか。",
        [("登用の発令を確認し、Bの雇用形態の修正を依頼する（勤怠ルールや承認者が変わる可能性も伝える）", True),
         ("ラベルの表記ゆれなので変換表に追加する", False),
         ("Aを契約社員に戻す", False),
         ("雇用形態は勤怠に関係ないので対応不要", False)],
        "「契約社員」と「正社員」は表記ゆれではなく別のコード。雇用区分は残業・休暇のルールに影響するので放置できない。",
        "P1"),
    "hire_date_typo": (
        "入社日と利用開始日がちょうど1年ずれています。最も適切な対応はどれですか。",
        [("入社書類でAの入社日を確認し、Bの利用開始日の修正を依頼する（有給の付与など日付に依存する処理への影響も確認する）", True),
         ("7日以内の差は許容なので対応不要", False),
         ("よくある入力ミスなので、自分の判断でBの日付を推測して直す", False),
         ("Aの入社日をBに合わせる", False)],
        "1年のずれは許容差（7日）を大きく超える。日付は勤続年数や有給付与に直結するので、根拠を確認して依頼する。",
        "P1"),
    "empno_missing": (
        "B社員番号が空欄ですが、メールアドレスでAの社員と一致しました。最も適切な対応はどれですか。",
        [("メールで結合したうえで差異として記録し、Bの管理者に社員番号の入力を依頼する", True),
         ("氏名でも一致しているので、結合して完了とする", False),
         ("社員番号がないのでBのみ（実在しない人）として無効化を依頼する", False),
         ("Aの社員番号をBに推測で入力する", False)],
        "メールは2番目に信頼できるキーなので結合してよい。ただし空欄は放置すると毎月同じ救済が必要になるので、上流で直してもらう。",
        "P8"),
    "test_or_shared_account": (
        "Aのどの社員にも結合しない有効アカウントがあります。最も適切な対応はどれですか。",
        [("利用目的と管理者を確認し、不要なら無効化を依頼する。必要なら人以外のアカウントとして台帳で管理する", True),
         ("人事データにいないので、自分ですぐに削除する", False),
         ("氏名が近い社員に結合しておく", False),
         ("人ではないので突合の対象外として無視する", False)],
        "Bのみの有効アカウントは「誰のものか分からないのにログインできる」状態。テスト用・共用でも管理者と目的を明確にする。",
        "P5"),
    "new_hire_not_registered": (
        "10月16日入社の社員が、まだBに登録されていません（基準日は10月31日）。最も適切な対応はどれですか。",
        [("タイミング差（T）として記録し、登録予定日をBの管理者に確認する。翌月の突合で解消を確認する", True),
         ("入社から時間が経っていないので、記録せずに除外する", False),
         ("Aの入社日が誤っている可能性があるのでAを修正する", False),
         ("Bに登録がない社員は在籍人数から外す", False)],
        "タイミング差は「説明済みの差異」。ただし記録しておかないと、翌月も解消されていないことに気づけない。",
        "P3"),
    "rehire_empno_carried_over": (
        "Bのアカウントの社員番号は、Aでは今年3月に定年退職したレコードを指しています。同じメールアドレスで、4月に嘱託として入社したレコードがAにあります。最も適切な対応はどれですか。",
        [("新しい雇用（嘱託の社員番号）に結合し直し、Bの社員番号の更新を依頼する。利用開始日の扱いも確認する", True),
         ("退職者のアカウントが残っているので、無効化を依頼する", False),
         ("嘱託のレコードはBに登録がないので、未登録として報告する", False),
         ("社員番号が一致しているので、退職レコードとの結合で正しい", False)],
        "社員番号は人ではなく雇用関係の番号。同じ人が再雇用されると番号が変わる。無効化を依頼すると、働いている人がログインできなくなる。",
        "P4"),
}

PRINCIPLE_QUESTIONS = [
    ("部署欄が空欄の社員が12名います。今日中に月次の人員レポートを出す必要があります。どうしますか。",
     [("「部署未確定」として分けて計上し、注記したうえで人事に確認を依頼する", True),
      ("前月の部署で埋める", False), ("レポートから除外する", False), ("一番人数の多い部署に入れる", False)],
     "正解は人事の原票にある。推測で埋めると、誤りに気づける人がいなくなる。分けて見せれば、読み手も判断できる。", "P1"),
    ("年収3,200万円の社員が1名います。平均年収を出すとき、どう扱いますか。",
     [("誤りと決めつけず、役員・専門職などの可能性を確認する。分析では中央値の併記などで扱う", True),
      ("外れ値なので削除する", False), ("平均値で置き換える", False), ("入力ミスとして修正依頼を出す", False)],
     "珍しい値は誤りではない。人事データの外れ値は、組織にとって重要な人であることが多い。", "P7"),
    ("退職日が入社日より前になっているレコードがあります。どう扱いますか。",
     [("ありえない値なので誤りとしてフラグを立て、原票の確認を依頼する", True),
      ("珍しいケースとしてそのまま使う", False), ("退職日を入社日と同じ日に直す", False), ("レコードを削除する", False)],
     "論理的にありえない値は誤り。ただし直すのは原票を確認してから。", "P7"),
    ("同じ氏名・同じ部署で、社員番号が違う2レコードがあります。どうしますか。",
     [("自動で統合せず、生年月日・メールアドレス・入社日で別人かどうかを確認する", True),
      ("重複なので新しいほうを残して統合する", False), ("重複なので古いほうを残して統合する", False), ("両方削除して再登録を依頼する", False)],
     "同姓同名は1,000人規模でも普通にいる。誤統合は他人の給与・個人情報の取り違えにつながる。", "P5"),
    ("離職率の傾向分析に使うデータで、部署が3%欠損しています。どう扱いますか。",
     [("分析用途なので「不明」として集計に含め、欠損率を注記する（運用データの修正は別途依頼）", True),
      ("欠損がある限り分析はできないので中止する", False), ("最頻値の部署で埋める", False), ("欠損者を除外して、注記なしで集計する", False)],
     "分析は全体の偏りが分かればよい。ただし運用データとしての欠損は、別に直してもらう。", "P2"),
    ("AとBで所属が違います。Aの異動の発令日は昨日です。どう考えますか。",
     [("タイミング差の可能性が高い。反映のルール（何日以内か）を確認し、許容内なら説明済みの差異として記録する", True),
      ("Bの入力誤りなので至急修正を依頼する", False), ("Aが早すぎるので、Aを元に戻す", False), ("差異はゼロであるべきなので、両方を確認するまで突合を止める", False)],
     "差異の多くは誤りではなく時間のズレ。目指すのは差異ゼロではなく、すべての差異に説明がつく状態。", "P3"),
    ("作業を効率化するため、クレンジングした結果で受領したCSVを上書きしたいと思いました。どうしますか。",
     [("受領ファイルは残し、クレンジング後のデータは別のファイルに出力する", True),
      ("効率が上がるので上書きする", False), ("上書きしたうえで、元の値をメモしておく", False), ("上書きして、問題が出たら再提出を依頼する", False)],
     "原本を上書きすると、是正依頼のときに「元の値が何だったか」を示せなくなる。", "P3"),
    ("毎月、Bの部署名「情シス」を「情報システム部」に変換しています。ほかにやるべきことは何ですか。",
     [("変換表で吸収しつつ、Bの部署名を自由入力から選択式にするよう改善を提案する", True),
      ("変換表があるので何もしなくてよい", False), ("Bの部署名を毎月手で直す", False), ("「情シス」を正式名称としてAに登録する", False)],
     "下流で直し続けるのは毎月の税金。表記ゆれが生まれる仕組みを直すと、クレンジング自体が要らなくなる。", "P8"),
    ("「休職者を在籍人数に含めるかどうか」を、あなたが決めてよいですか。",
     [("自分では決めない。人事責任者に、選択肢と数字への影響を示して決めてもらい、決定を記録する", True),
      ("統計的に正しいほうを自分で決める", False), ("前任者のやり方に合わせて黙って決める", False), ("毎月その場で判断する", False)],
     "どの定義を採用するかは業務判断。アナリストの仕事は、定義を明示し、混ざっていないかを検知すること。", "P9"),
    ("定年再雇用で、同じ人に社員番号が2つ（旧：退職、新：嘱託）あります。基準日時点の在籍人数は何人と数えますか。",
     [("1人（現在の雇用関係だけを数える）", True), ("2人（レコードが2つあるので）", False),
      ("0人（退職レコードがあるので）", False), ("数えられないので除外する", False)],
     "社員番号は雇用関係の番号。人を数えるのか、雇用を数えるのかを区別する。", "P4"),
    ("Aの退職日の欄が空欄です。これは何を意味しますか。",
     [("退職日がまだ来ていない（在籍中）", True), ("入力漏れなので確認が必要", False),
      ("退職日が不明", False), ("データが壊れている", False)],
     "空欄にも意味がある。退職日の空欄は「まだ来ていない」。すべての空欄を同じ欠損として扱うと情報が消える。", "P6"),
    ("突合で差異が120件出ました。うち80件は組織改編前の旧部署名です。どう進めますか。",
     [("80件は1つのパターンとして変換ルールに追加し、残り40件を個別に調べる", True),
      ("120件を上から順に1件ずつ調べる", False), ("件数が多いので今月は報告しない", False), ("全件をBの管理者に修正依頼する", False)],
     "件数の多いものはパターンで潰し、ルール化して二度と出ないようにする。人が追うのは残りだけ。", "P8"),
    ("名寄せのルールを調整しています。「誤統合を1件減らす」と「見逃しを10件減らす」、どちらを優先しますか。",
     [("誤統合を1件減らす", True), ("見逃しを10件減らす", False), ("件数が多いほうなので見逃し", False), ("どちらも同じ重さ", False)],
     "見逃しは次回直せるが、誤統合は気づかれないまま他人の情報を混ぜ続ける。", "P5"),
    ("上司から「今の在籍人数を教えて」と言われました。最初に何をしますか。",
     [("基準日（いつ時点か）と母集団（休職・出向・役員を含むか）を確認してから数える", True),
      ("すぐにAシステムの件数を数えて答える", False), ("Bシステムの有効アカウント数を答える", False), ("前月のレポートの数字を答える", False)],
     "数字には「いつ時点・誰を含むか・どの定義か」が必ず必要。これがない数字は、後で必ず食い違う。", "P3"),
    ("生年月日が1900-01-01のレコードが5件あります。どう扱いますか。",
     [("ダミー値として「不明」扱いにし、年齢の集計からは外して注記する。原票の確認を依頼する", True),
      ("126歳として集計する", False), ("平均年齢で置き換える", False), ("レコードを削除する", False)],
     "1900-01-01や9999-12-31は「値がない」ことを表すダミー値であることが多い。空欄と同じく意味を確かめる。", "P6"),
    ("社員が改姓しました。過去の月次レポートの氏名も、新しい姓に一括で置き換えますか。",
     [("置き換えない。過去のデータは当時の値のまま残し、氏名の履歴として管理する", True),
      ("置き換える。最新の情報にそろえるべき", False), ("過去のレポートを削除する", False), ("旧姓を空欄にする", False)],
     "履歴を上書きすると、当時の書類と突き合わせられなくなる。人事データは時間とともに持つ。", "P3"),
]


def _a_card(p) -> dict:
    return {
        "社員番号": p.emp_id, "氏名": f"{p.last} {p.first}", "入社年月日": p.hire.isoformat(),
        "在籍区分": f"{p.status}（{STATUS[p.status]}）"
        + (f" 退職日 {p.term.isoformat()}" if p.term else ""),
        "雇用区分": f"{p.emp_type}（{EMP_TYPES[p.emp_type]}）",
        "組織": f"{p.org_code}（{ORG_NAME[p.org_code]}）", "メール": p.email,
    }


def _b_card(r: dict) -> dict:
    d = r["start_date"]
    return {
        "ユーザーID": r["user_id"], "社員番号": r["emp_no"] or "（空欄）", "氏名": r["name"], "部署": r["dept"],
        "雇用形態": r["emp_type"] or "（空欄）", "利用開始日": r["start_date_text"] or f"{d.year}/{d.month}/{d.day}",
        "有効": r["active"], "メール": r["email"],
    }


def build_cases(seeds=(101, 102, 103), per_seed: dict | None = None) -> list[dict]:
    """全問題を作る。同じ seeds なら同じ問題になる。"""
    per_seed = per_seed or {"match": 12, "diff": 16, "action": 10}
    cases: list[dict] = []
    for seed in seeds:
        rng = random.Random(seed * 7)
        data = generate(seed=seed, level=3)
        persons = {p.emp_id: p for p in data.persons}
        rows = {r["user_id"]: r for r in data.b_rows}
        key_by_user: dict[str, list[dict]] = {}
        for a in data.answer_key:
            if a["b_user_id"]:
                key_by_user.setdefault(a["b_user_id"], []).append(a)
        diffs_by_pair: dict[tuple[str, str], list[str]] = {}
        for d in data.expected_diffs:
            if d["item"] not in ("a_only", "b_only"):
                diffs_by_pair.setdefault((d["a_emp_id"], d["b_user_id"]), []).append(d["item"])
        match_of = {m["b_user_id"]: m["a_emp_id"] for m in data.expected_matches}
        in_scope = [p for p in data.persons if p.in_scope]

        def decoy(p):
            same_last = [q for q in in_scope if q.last_romaji == p.last_romaji and q.emp_id != p.emp_id
                         and q.email != p.email]
            return rng.choice(same_last or [q for q in in_scope if q.emp_id != p.emp_id])

        # ---------- 名寄せ問題 ----------
        match_cases = []
        for uid, r in rows.items():
            types = {a["dirt_type"] for a in key_by_user.get(uid, [])}
            target = match_of.get(uid)
            if "test_or_shared_account" in types:
                cands = [rng.choice(in_scope)]
                answer, pr = "none", "P5"
                why = "Aのどの社員とも社員番号・メールが一致しない。氏名が似ている社員がいても結合しない。Bのみとして報告する。"
                tag = "test_or_shared_account"
            elif "rehire_empno_carried_over" in types:
                new = persons[target]
                old = next(q for q in data.persons if q.email == new.email and q.emp_id != new.emp_id)
                cands = [old, new]
                answer, tag, pr = new.emp_id, "rehire_empno_carried_over", "P4"
                why = "社員番号は旧レコード（退職）を指すが、同じメールの在籍レコードがある。アカウントは現在の雇用に結合する。"
            elif "same_name_different_person" in types:
                me = persons[target]
                twin = next(q for q in data.persons if q.last == me.last and q.first == me.first
                            and q.emp_id != me.emp_id and q.in_scope)
                cands = [me, twin]
                answer, tag, pr = me.emp_id, "same_name_different_person", "P5"
                why = "同姓同名の2人。B社員番号が空欄なので、メールアドレスで決める。氏名だけで選ぶと誤統合になる。"
            elif target and types & {"empno_zero_drop", "empno_missing", "surname_change_not_reflected", "itaiji",
                                     "retired_still_active"}:
                me = persons[target]
                cands = [me, decoy(me)]
                answer, pr = me.emp_id, "P5"
                tag = next(t for t in ("surname_change_not_reflected", "empno_missing", "retired_still_active",
                                       "empno_zero_drop", "itaiji") if t in types)
                why = {
                    "empno_zero_drop": "社員番号の先頭ゼロが消えているだけ。6桁にそろえると一致する。",
                    "empno_missing": "社員番号は空欄だが、メールアドレスが一致する。2番目に信頼できるキーで結合する。",
                    "surname_change_not_reflected": "姓は違うが、社員番号とメールが一致する。改姓の反映漏れで、同一人物。",
                    "itaiji": "髙と高は異体字。社員番号も一致する同一人物。",
                    "retired_still_active": "社員番号もメールも一致する同一人物。退職者のアカウントが有効なままという別の問題がある。",
                }[tag]
            elif target and not types and rng.random() < 0.02:
                me = persons[target]
                cands = [me, decoy(me)]
                answer, tag, pr = me.emp_id, "clean", "P5"
                why = "社員番号・メールが一致する。氏名が似た別の候補があっても、キーで決める。"
            else:
                continue
            rng.shuffle(cands)
            match_cases.append({
                "kind": "match", "tag": tag, "principle": pr, "b": _b_card(r),
                "candidates": [_a_card(c) for c in cands],
                "options": [{"key": c.emp_id, "label": f"候補 {c.emp_id}"} for c in cands]
                + [{"key": "none", "label": "どちらでもない（Bのみ）"}],
                "answer": [answer], "explain": why,
            })
        rng.shuffle(match_cases)
        by_tag: dict[str, list[dict]] = {}
        for c in match_cases:
            by_tag.setdefault(c["tag"], []).append(c)
        picked: list[dict] = []
        while len(picked) < per_seed["match"] and any(by_tag.values()):  # 種類ごとに1問ずつ順に取る
            for tag in sorted(by_tag):
                if by_tag[tag] and len(picked) < per_seed["match"]:
                    picked.append(by_tag[tag].pop())
        rng.shuffle(picked)
        cases += picked

        # ---------- 差異判定問題 ----------
        diff_cases = []
        for uid, a_id in match_of.items():
            r, p = rows[uid], persons[a_id]
            entries = key_by_user.get(uid, [])
            types = {a["dirt_type"] for a in entries}
            if types & {"rehire_empno_carried_over", "same_name_different_person"}:
                continue
            items = sorted(set(diffs_by_pair.get((a_id, uid), [])))
            c_types = [t for t in types if t in C_EXPLAIN and C_EXPLAIN[t][0] != "email"]
            if not items and not c_types and rng.random() > 0.03:
                continue  # 完全にきれいな組は少しだけ混ぜる（現実の大半はきれい）
            notes = [C_EXPLAIN[t][1] for t in c_types]
            notes += [E_EXPLAIN[t] for t in types if t in E_EXPLAIN]
            if not notes:
                notes = ["すべての項目が一致している。現実のデータの大半はこの状態。疑いすぎるとノイズになる。"]
            diff_cases.append({
                "kind": "diff", "tag": ",".join(sorted(types)) or "clean",
                "principle": "P8" if not items else "P1", "a": _a_card(p), "b": _b_card(r),
                "options": [{"key": k, "label": ITEM_LABEL[k]} for k in
                            ("name", "org", "emp_type", "hire_date", "status", "emp_no", "none")],
                "multi": True, "answer": items or ["none"], "explain": " ".join(notes),
            })
        rng.shuffle(diff_cases)
        with_diff = [c for c in diff_cases if c["answer"] != ["none"]]
        without = [c for c in diff_cases if c["answer"] == ["none"]]
        n = per_seed["diff"]
        cases += with_diff[: n // 2] + without[: n - n // 2]

        # ---------- 次の一手問題 ----------
        action_cases = []
        seen_types: dict[str, int] = {}
        for a in data.answer_key:
            t = a["dirt_type"]
            if t not in ACTIONS or seen_types.get(t, 0) >= 1:
                continue
            seen_types[t] = seen_types.get(t, 0) + 1
            q, opts, why, pr = ACTIONS[t]
            card: dict = {}
            if a["a_emp_id"] and a["a_emp_id"] in persons:
                card["a"] = _a_card(persons[a["a_emp_id"]])
            if a["b_user_id"] and a["b_user_id"] in rows:
                card["b"] = _b_card(rows[a["b_user_id"]])
            if t == "rehire_empno_carried_over":
                old_id = a["observed_value"]
                card["a2"] = _a_card(persons[old_id])
            labeled = [{"key": f"o{i}", "label": text, "ok": ok} for i, (text, ok) in enumerate(opts)]
            rng.shuffle(labeled)
            action_cases.append({
                "kind": "action", "tag": t, "principle": pr, "question": q, **card,
                "options": [{"key": o["key"], "label": o["label"]} for o in labeled],
                "answer": [next(o["key"] for o in labeled if o["ok"])], "explain": why,
            })
        cases += action_cases[: per_seed["action"]]

    for i, (q, opts, why, pr) in enumerate(PRINCIPLE_QUESTIONS):
        rng = random.Random(1000 + i)
        labeled = [{"key": f"o{j}", "label": text, "ok": ok} for j, (text, ok) in enumerate(opts)]
        rng.shuffle(labeled)
        cases.append({
            "kind": "principle", "tag": f"principle_{i + 1:02d}", "principle": pr, "question": q,
            "options": [{"key": o["key"], "label": o["label"]} for o in labeled],
            "answer": [next(o["key"] for o in labeled if o["ok"])], "explain": why,
        })
    for i, c in enumerate(cases, start=1):
        c["id"] = f"Q{i:03d}"
    return cases


def build_html(template_path: Path, out_path: Path, seeds=(101, 102, 103)) -> dict:
    """テンプレートに問題を埋め込み、単一ファイルのページを作る。"""
    cases = build_cases(seeds)
    payload = json.dumps({"cases": cases, "principles": PRINCIPLES}, ensure_ascii=False, separators=(",", ":"))
    html = template_path.read_text(encoding="utf-8").replace("/*__DRILL_DATA__*/null", payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    counts: dict[str, int] = {}
    for c in cases:
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1
    return {"total": len(cases), **counts}
