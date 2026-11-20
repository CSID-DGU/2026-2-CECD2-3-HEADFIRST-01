# -*- coding: utf-8 -*-
"""v3.2 학습셋 만들기: 줄이기 · 유형 변환 · 표현 다양화 · 검증.

순서
  1) python make_v32.py reduce   --train sft_train_v3_1.jsonl --cap 10
       → out/v32/kept.jsonl(남긴 것) · removed.jsonl(틀당 cap 초과분) · reduce_report.md
  2) python make_v32.py requests --train sft_train_v3_1.jsonl [--weights weights_v32.json] [--per 30]
       → out/v32/requests.jsonl  (유형 변환 요청 + removed.jsonl의 표현 다양화 요청)
  3) python make_v32.py run --base-url http://.../v1 --model <이름> [--api-key-env OPENAI_API_KEY]
       → out/v32/responses.jsonl (이어 하기 가능. OpenAI 호환 /chat/completions)
  4) python make_v32.py build    --train sft_train_v3_1.jsonl
       → out/v32/sft_train_v3_2_A.jsonl (실험 A = v3.1 + 유형 변환)
         out/v32/sft_train_v3_2_B.jsonl (실험 B = 줄인 v3.1 + 유형 변환 + 표현 다양화)
         out/v32/build_report.md (통과·탈락 건수, 사유), out/v32/review_sample.csv (유형 부합 확인용 표본)

원칙
  - 값(이름·번호·날짜)은 **기존 v3.1 학습 데이터의 정답 값을 다시 쓴다.** 새 값을 만들지 않는다.
  - 값의 말 표현(읽는 법)은 코드가 만들고, LLM에는 "이 표현을 글자 그대로 넣어라"로 준다
    → 정답 라벨은 변형 규칙에서 정해지고, 값 보존은 문자열 검사로 확인된다.
  - 하드셋 문장은 프롬프트에 넣지 않는다(예시는 전부 이 파일에서 따로 쓴 것).
"""
import argparse
import csv
import json
import random
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from template_tools import load_sft, names_of, template, value_signature

BASE = Path(__file__).resolve().parent
OUT = BASE / "out" / "v32"
INTENT = "FileComplaint"
OPENING_Q = "안녕하세요 구청 민원 접수입니다. 민원 접수를 위해 개인정보 수집에 동의하시나요?"
OPENING_A = "네 동의합니다."
STD_Q = {
    "consent": OPENING_Q, "name": "성함이 어떻게 되세요?", "birth_date": "생년월일을 말씀해 주시겠어요?",
    "phone": "연락받으실 전화번호를 알려주세요.", "complaint_type": "어떤 일로 연락 주셨어요?",
    "occurred_date": "언제부터 그러셨어요?", "reply_channel": "처리 결과는 어떻게 알려드릴까요?",
}
COMPLAINTS = ["불법 주정차", "도로·보도 파손", "가로등·보안등 고장", "불법 광고물", "쓰레기·동물 사체"]

# ---------------------------------------------------------------------------
# 숫자 읽기
# ---------------------------------------------------------------------------
_D = "영일이삼사오육칠팔구"


def sino(n):
    if n == 0:
        return "영"
    out = ""
    for unit, name in ((1000, "천"), (100, "백"), (10, "십")):
        q, n = divmod(n, unit)
        if q:
            out += ("" if q == 1 else _D[q]) + name
    return out + (_D[n] if n else "")


def digits_read(s):
    return "".join("공" if c == "0" else _D[int(c)] for c in s)


def month_read(m):
    return {6: "유월", 10: "시월"}.get(m, sino(m) + "월")


def day_read(d):
    return sino(d) + "일"


def year_read(y, short=False):
    return sino(y % 100 if short else y) + "년"


# ---------------------------------------------------------------------------
# 유형 변환 정의
#   hard: 하드셋 유형 번호(1~10) · slot: 질문받은 슬롯 · make(v, rng) → dict
#     inst      변형 지시(LLM에 줌)
#     must      글자 그대로 들어가야 하는 표현 목록
#     ban       들어가면 안 되는 표현 목록
#     order     [(앞, 뒤)] 앞 표현이 뒤 표현보다 먼저 나와야 함(마지막 등장 기준)
#     gold      [(slot, act, value)] 정답. 변형 규칙에서 정해짐
#     nums_ok   True면 must 밖의 숫자 표현을 허용(긴 사연 등). 기본 False = 다른 숫자가 나오면 탈락
#   v = 기존 학습 데이터에서 뽑은 값 묶음: name, birth(date), phone('010-1234-5678'), today(date), occ(date)
# ---------------------------------------------------------------------------
FAMILY = ["아들", "딸", "남편", "집사람", "며느리", "손주", "큰애", "작은애"]
PEER = ["남편", "집사람", "영감", "언니", "오빠", "동생"]  # 생년이 본인과 비슷한 가족(생년월일 변환용)


def _b(v):
    b = v["birth"]
    return {"Y": year_read(b.year), "y": year_read(b.year, True), "M": month_read(b.month), "D": day_read(b.day),
            "iso": b.isoformat()}


def _p(v):
    a, b, c = v["phone"].split("-")
    return {"a": digits_read(a), "b": digits_read(b), "c": digits_read(c), "bn": b, "cn": c, "iso": v["phone"]}


def _other_day(b, rng):
    d = rng.choice([x for x in range(1, 29) if x != b.day])
    return day_read(d)


def _wrong_digits(c, rng):
    i, j = rng.sample(range(4), 2)
    w = list(c)
    w[i], w[j] = w[j], w[i]
    if "".join(w) == c:
        w[i] = str((int(w[i]) + 3) % 10)
    return "".join(w)


def _pairs_read(g):
    """9900 → '구 두 개 공 두 개', 3344 → '삼 두 개 사 두 개'. 같은 숫자 두 개씩이 아니면 None"""
    if g[0] == g[1] and g[2] == g[3]:
        return f"{digits_read(g[0])} 두 개 {digits_read(g[2])} 두 개"
    return None


def _pairs_fmt(pr, rng):
    """'구 두 개 공 두 개'의 표기만 바꿈: 붙여 쓰기, 숫자 표기"""
    return None if pr is None else rng.choice([pr, pr, pr.replace("두 개", "두개"), pr.replace("두 개", "2개"), pr.replace(" 두 개", "2개")])


def _birth_pairs(b):
    """월일 네 자리에서 같은 숫자가 겹치는 곳을 'X 두 개'로. (월 표현, 일 표현) 또는 None. 1943-11-08 → ('일 두 개', '공팔')"""
    m, d = f"{b.month:02d}", f"{b.day:02d}"
    pm, pd = m[0] == m[1], d[0] == d[1]
    if not (pm or pd):
        return None
    return (f"{digits_read(m[0])} 두 개" if pm else digits_read(m), f"{digits_read(d[0])} 두 개" if pd else digits_read(d))


HOLIDAYS = [("새해 첫날", 1, 1), ("삼일절", 3, 1), ("식목일", 4, 5), ("어린이날", 5, 5), ("어버이날", 5, 8), ("현충일", 6, 6),
            ("광복절", 8, 15), ("개천절", 10, 3), ("한글날", 10, 9), ("성탄절", 12, 25), ("크리스마스", 12, 25)]


def _holiday(today, rng):
    name, m, d = rng.choice(HOLIDAYS)
    this = date(today.year, m, d)
    if this < today and rng.random() < 0.6:
        return name, "올해", this
    return name, "작년", date(today.year - 1, m, d)


def T(tid, hard, slot, desc, make):
    return {"id": tid, "hard": hard, "slot": slot, "desc": desc, "make": make}


def _occ_parts(v):
    o = v["occ"]
    return month_read(o.month), day_read(o.day), o.isoformat()


TRANSFORMS = [
    # ---------------- birth_date
    T("B-T1-U", 1, "birth_date", "연도를 빼고 월·일만 말함 → UNCERTAIN", lambda v, r: (lambda b: dict(
        inst="생년월일을 묻는데 태어난 달과 날만 말한다. 연도·나이·띠는 말하지 않는다.",
        must=[b["M"], b["D"]], ban=[b["Y"], b["y"], "년생", "살", "띠"],
        gold=[("birth_date", "UNCERTAIN", "")]))(_b(v))),
    T("B-T3-U", 3, "birth_date", "가족의 생년월일을 말함 → UNCERTAIN", lambda v, r: (lambda b, f: dict(
        inst=f"본인이 아니라 '{f}'의 생년월일을 말한다. 누구 생일인지 발화에서 분명해야 한다. 본인 생년월일은 말하지 않는다.",
        must=[f, b["y"], b["M"], b["D"]], ban=[], gold=[("birth_date", "UNCERTAIN", "")]))(_b(v), r.choice(PEER))),
    T("B-T3-I", 3, "birth_date", "본인 것임을 밝히고 전부 말함 → INFORM", lambda v, r: (lambda b: dict(
        inst="가족 이야기를 잠깐 꺼내지만(가족의 날짜·숫자는 말하지 않음) 본인 생년월일임을 밝히고 연·월·일을 전부 말한다.",
        must=[b["Y"], b["M"], b["D"]], ban=[], gold=[("birth_date", "INFORM", b["iso"])]))(_b(v))),
    T("B-T4-I", 4, "birth_date", "날을 잘못 말했다가 고쳐서 확정 → INFORM(마지막 값)", lambda v, r: (lambda b, w: dict(
        inst=f"처음에는 날을 '{w}'로 잘못 말했다가 스스로 고쳐서 맞는 날로 확정한다. '아니' 한 단어로만 고치지 말고 고치는 말을 다양하게 쓴다.",
        must=[b["y"], b["M"], w, b["D"]], ban=[], order=[(w, b["D"])],
        gold=[("birth_date", "INFORM", b["iso"])]))(_b(v), _other_day(v["birth"], r))),
    T("B-T4-U", 4, "birth_date", "두 날 사이에서 끝내 못 정함 → UNCERTAIN", lambda v, r: (lambda b, w: dict(
        inst=f"날이 '{b['D']}'인지 '{w}'인지 헷갈려 하다가 끝까지 하나로 정하지 못한다.",
        must=[b["y"], b["M"], b["D"], w], ban=[], gold=[("birth_date", "UNCERTAIN", "")]))(_b(v), _other_day(v["birth"], r))),
    T("B-T6-I", 6, "birth_date", "질문을 되묻고 나서 전부 답함 → INFORM", lambda v, r: (lambda b: dict(
        inst="질문을 되묻거나 왜 묻는지 한마디 한 뒤에 연·월·일을 전부 답한다.",
        must=[b["y"], b["M"], b["D"]], ban=[], gold=[("birth_date", "INFORM", b["iso"])]))(_b(v))),
    T("B-T67-U", 6, "birth_date", "되묻기·딴소리·거절만 하고 값 없음 → UNCERTAIN", lambda v, r: dict(
        inst=r.choice(["질문을 못 알아듣고 되묻기만 한다.", "생년월일은 말하기 싫다고 거절한다.",
                       "이미 알고 있는 것 아니냐며 답을 하지 않는다.", "질문과 상관없는 민원 내용을 말하기 시작한다."])
        + " 날짜·숫자는 하나도 말하지 않는다.",
        must=[], ban=[], gold=[("birth_date", "UNCERTAIN", "")])),
    T("B-T8-I", 8, "birth_date", "연도 두 자리 + 월일 네 자리를 숫자 낭독 → INFORM", lambda v, r: (lambda b, yy, md: dict(
        inst="연도는 뒤 두 자리를, 월과 일은 네 자리 숫자를 한 자씩 읽는 식으로 말한다.",
        must=[yy + "년", md], ban=[], gold=[("birth_date", "INFORM", b["iso"])]))(
        _b(v), digits_read(f"{v['birth'].year % 100:02d}"), digits_read(f"{v['birth'].month:02d}{v['birth'].day:02d}"))),
    T("B-T8P-I", 8, "birth_date", "월일 숫자 낭독에서 겹치는 숫자를 '몇 두 개'로 말함 → INFORM", lambda v, r: (lambda b, yy, bp: None if bp is None else dict(
        inst="연도는 뒤 두 자리를 말하고, 월과 일은 두 자리 숫자씩 읽되 같은 숫자가 겹치는 곳은 아래 표현처럼 개수로 말한다. 순서는 연, 월, 일.",
        must=([yy + "년", bp[0] + " " + bp[1]] if bp[0] == bp[1] else [yy + "년", bp[0], bp[1]]), ban=[],
        order=([] if bp[0] == bp[1] else [(bp[0], bp[1])]),
        gold=[("birth_date", "INFORM", b["iso"])]))(_b(v), digits_read(f"{v['birth'].year % 100:02d}"), _birth_pairs(v["birth"]))),
    T("B-T8-U", 8, "birth_date", "숫자 낭독인데 일이 빠짐 → UNCERTAIN", lambda v, r: (lambda yy, m: dict(
        inst="연도는 뒤 두 자리를, 월은 두 자리 숫자를 한 자씩 읽는 식으로 말하고 날은 말하지 않는다.",
        must=[yy + "년", m], ban=["일생", "일이요"], gold=[("birth_date", "UNCERTAIN", "")]))(
        digits_read(f"{v['birth'].year % 100:02d}"), digits_read(f"{v['birth'].month:02d}"))),
    T("B-T9-I", 9, "birth_date", "아라비아 숫자와 한글 표기 혼합 → INFORM", lambda v, r: (lambda b, parts: dict(
        inst="아래 표현을 표기(숫자/한글) 그대로 섞어 쓴다.",
        must=parts, ban=[], gold=[("birth_date", "INFORM", b["iso"])]))(_b(v), r.choice([
            [f"{v['birth'].year}년", month_read(v["birth"].month), f"{v['birth'].day}일"],
            [year_read(v["birth"].year), f"{v['birth'].month}월", day_read(v["birth"].day)],
            [f"{v['birth'].year % 100}년", month_read(v["birth"].month), f"{v['birth'].day}일"],
            [year_read(v["birth"].year, True), f"{v['birth'].month}월", f"{v['birth'].day}일"]]))),
    T("B-T9-U", 9, "birth_date", "표기 혼합인데 날이 빠짐 → UNCERTAIN", lambda v, r: dict(
        inst="아래 표현을 표기 그대로 쓰고, 태어난 날은 말하지 않는다.",
        must=[f"{v['birth'].year}년", month_read(v["birth"].month)], ban=["일생", "일이요", "일에"],
        gold=[("birth_date", "UNCERTAIN", "")])),
    T("B-T10-I", 10, "birth_date", "긴 사연 속에 생년월일 → INFORM", lambda v, r: (lambda b: dict(
        inst="살아온 이야기나 하소연을 길게(60자 이상) 늘어놓는 중간에 본인 생년월일을 한 번만 말한다. 다른 날짜·연도는 말하지 않는다.",
        must=[b["Y"], b["M"], b["D"]], ban=[], nums_ok=True, gold=[("birth_date", "INFORM", b["iso"])]))(_b(v))),
    T("B-T2-II", 2, "birth_date", "생년월일 질문에 이름도 같이 말함 → 둘 다 INFORM", lambda v, r: (lambda b: dict(
        inst="생년월일을 묻는데 이름도 같이 말한다. 순서는 자유.",
        must=[v["name"], b["y"], b["M"], b["D"]], ban=[],
        gold=[("birth_date", "INFORM", b["iso"]), ("name", "INFORM", v["name"])]))(_b(v))),
    T("B-T2-UI", 2, "birth_date", "이름은 말하고 생일은 월·일만 → birth UNCERTAIN + name INFORM", lambda v, r: (lambda b: dict(
        inst="생년월일을 묻는데 이름을 말하고, 생일은 달과 날만 말한다. 연도·나이는 말하지 않는다.",
        must=[v["name"], b["M"], b["D"]], ban=[b["Y"], b["y"], "년생", "살"],
        gold=[("birth_date", "UNCERTAIN", ""), ("name", "INFORM", v["name"])]))(_b(v))),
    # ---------------- phone
    T("P-T1-U", 1, "phone", "뒷자리만 말하거나 중간에 끊김 → UNCERTAIN", lambda v, r: (lambda p, mode: dict(
        inst=("전화번호를 묻는데 끝 네 자리만 말한다." if mode else "앞자리와 가운데 네 자리까지만 말하고 나머지는 기억이 안 난다고 한다."),
        must=([p["c"]] if mode else [p["a"], p["b"]]), ban=([p["b"]] if mode else [p["c"]]),
        gold=[("phone", "UNCERTAIN", "")]))(_p(v), r.random() < 0.5)),
    T("P-T3-U", 3, "phone", "가족 번호를 말함 → UNCERTAIN", lambda v, r: (lambda p, f: dict(
        inst=f"본인 번호가 아니라 '{f}' 번호를 불러 준다. 누구 번호인지 발화에서 분명해야 한다.",
        must=[f, p["a"], p["b"], p["c"]], ban=[], gold=[("phone", "UNCERTAIN", "")]))(_p(v), r.choice(FAMILY))),
    T("P-T3-I", 3, "phone", "본인 번호임을 밝히고 말함 → INFORM", lambda v, r: (lambda p: dict(
        inst="본인 번호라는 것을 밝히면서 번호를 전부 말한다. 가족 번호는 말하지 않는다.",
        must=[p["a"], p["b"], p["c"]], ban=[], gold=[("phone", "INFORM", p["iso"])]))(_p(v))),
    T("P-T4-I", 4, "phone", "끝 네 자리를 틀리게 말했다가 고쳐 확정 → INFORM", lambda v, r: (lambda p, w: dict(
        inst=f"끝 네 자리를 처음에 '{w}'로 잘못 말했다가 스스로 고쳐서 확정한다.",
        must=[p["a"], p["b"], w, p["c"]], ban=[], order=[(w, p["c"])],
        gold=[("phone", "INFORM", p["iso"])]))(_p(v), digits_read(_wrong_digits(_p(v)["cn"], r)))),
    T("P-T4-U", 4, "phone", "고치려다 끝내 못 정함 → UNCERTAIN", lambda v, r: (lambda p, w: dict(
        inst=f"끝 네 자리가 '{p['c']}'인지 '{w}'인지 헷갈려 하다가 끝까지 정하지 못한다.",
        must=[p["a"], p["b"], p["c"], w], ban=[], gold=[("phone", "UNCERTAIN", "")]))(
        _p(v), digits_read(_wrong_digits(_p(v)["cn"], r)))),
    T("P-T6-I", 6, "phone", "되묻거나 투덜댄 뒤 번호를 전부 말함 → INFORM", lambda v, r: (lambda p: dict(
        inst="질문을 되묻거나 왜 필요한지 한마디 한 뒤에 번호를 전부 말한다.",
        must=[p["a"], p["b"], p["c"]], ban=[], gold=[("phone", "INFORM", p["iso"])]))(_p(v))),
    T("P-T67-U", 7, "phone", "거절·미루기·되묻기만 → UNCERTAIN", lambda v, r: dict(
        inst=r.choice(["전화번호는 알려 주기 싫다고 한다.", "왜 물어보느냐고 따지기만 한다.", "나중에 알려 주겠다고 미룬다.",
                       "질문을 못 알아듣고 되묻기만 한다.", "번호가 기억나지 않는다고 한다."]) + " 숫자는 하나도 말하지 않는다.",
        must=[], ban=[], gold=[("phone", "UNCERTAIN", "")])),
    T("P-T8-I", 8, "phone", "'몇 두 개' 식으로 조립해서 말함 → INFORM", lambda v, r: (lambda p, pr: None if pr is None else dict(
        inst="끝 네 자리를 아래 표현처럼 같은 숫자 개수로 풀어서 말한다.",
        must=[p["a"], p["b"], pr], ban=[], gold=[("phone", "INFORM", p["iso"])]))(_p(v), _pairs_fmt(_pairs_read(_p(v)["cn"]), r))),
    T("P-T8-U", 8, "phone", "조립했는데 자릿수가 모자람 → UNCERTAIN", lambda v, r: (lambda p: dict(
        inst="가운데 네 자리까지는 말하고 끝자리는 세 자리만 말하고 끝낸다. 모자란다는 말은 하지 않는다.",
        must=[p["a"], p["b"], p["c"][:3]], ban=[p["c"]], gold=[("phone", "UNCERTAIN", "")]))(_p(v))),
    T("P-T9-I", 9, "phone", "숫자와 한글 낭독 혼합 → INFORM", lambda v, r: (lambda p, parts: dict(
        inst="아래 표현을 표기(숫자/한글) 그대로 섞어 쓴다.", must=parts, ban=[],
        gold=[("phone", "INFORM", p["iso"])]))(_p(v), r.choice([
            [_p(v)["a"], _p(v)["bn"], _p(v)["c"]], [_p(v)["a"], _p(v)["b"], _p(v)["cn"]], ["010", _p(v)["b"], _p(v)["cn"]]]))),
    T("P-T10-I", 10, "phone", "긴 사연 속에 번호 → INFORM", lambda v, r: (lambda p: dict(
        inst="전화기나 연락과 관련된 이야기를 길게(60자 이상) 늘어놓는 중간에 본인 번호를 한 번만 전부 말한다.",
        must=[p["a"], p["b"], p["c"]], ban=[], nums_ok=True, gold=[("phone", "INFORM", p["iso"])]))(_p(v))),
    T("P-T2-II", 2, "phone", "번호 질문에 회신 방법도 말함 → 둘 다 INFORM", lambda v, r: (lambda p, ch: dict(
        inst=f"번호를 전부 말하면서 결과는 '{ch}'로 알려 달라고 덧붙인다.",
        must=[p["a"], p["b"], p["c"], ch], ban=[],
        gold=[("phone", "INFORM", p["iso"]), ("reply_channel", "INFORM", ch)]))(_p(v), r.choice(["문자", "전화"]))),
    T("P-T2-UI", 2, "phone", "회신 방법은 말하고 번호는 일부만 → phone UNCERTAIN + reply INFORM", lambda v, r: (lambda p, ch: dict(
        inst=f"결과는 '{ch}'로 알려 달라고 하면서 번호는 가운데 네 자리까지만 말하고 나머지는 기억이 안 난다고 한다.",
        must=[p["b"], ch], ban=[p["c"]],
        gold=[("phone", "UNCERTAIN", ""), ("reply_channel", "INFORM", ch)]))(_p(v), r.choice(["문자", "전화"]))),
    # ---------------- name
    T("N-T2-II", 2, "name", "이름 질문에 생년월일도 말함 → 둘 다 INFORM", lambda v, r: (lambda b: dict(
        inst="이름을 묻는데 생년월일(연·월·일 전부)도 같이 말한다. 순서는 자유.",
        must=[v["name"], b["y"], b["M"], b["D"]], ban=[],
        gold=[("name", "INFORM", v["name"]), ("birth_date", "INFORM", b["iso"])]))(_b(v))),
    T("N-T3-U", 3, "name", "가족 이름을 말함 → UNCERTAIN", lambda v, r: (lambda f: dict(
        inst=f"본인 이름이 아니라 '{f}' 이름을 말한다. 누구 이름인지 발화에서 분명해야 한다. 본인 이름은 말하지 않는다.",
        must=[f, v["name"]], ban=[], gold=[("name", "UNCERTAIN", "")]))(r.choice(FAMILY))),
    T("N-T6-I", 6, "name", "되묻고 나서 이름을 말함 → INFORM", lambda v, r: dict(
        inst="질문을 되묻거나 한마디 투덜댄 뒤에 본인 이름 석 자를 말한다.",
        must=[v["name"]], ban=[], gold=[("name", "INFORM", v["name"])])),
    T("N-T67-U", 7, "name", "되묻기·거절만 → UNCERTAIN", lambda v, r: dict(
        inst=r.choice(["이름을 말하기 싫다고 한다.", "질문을 못 알아듣고 되묻기만 한다.",
                       "이름은 됐고 민원부터 들어 달라고 한다.", "왜 이름이 필요하냐고 따지기만 한다."]) + " 사람 이름은 말하지 않는다.",
        must=[], ban=[], gold=[("name", "UNCERTAIN", "")])),
    T("N-T10-I", 10, "name", "긴 사연 속에 본인 이름 → INFORM", lambda v, r: dict(
        inst="자기소개를 길게(60자 이상) 늘어놓는 중간에 본인 이름 석 자를 한 번 말한다. 다른 사람 이름은 말하지 않는다.",
        must=[v["name"]], ban=[], nums_ok=True, gold=[("name", "INFORM", v["name"])])),
    # ---------------- occurred_date
    T("O-T5-I", 5, "occurred_date", "망설이다가 날짜를 확정 → INFORM", lambda v, r: (lambda m, d, iso: dict(
        inst="언제였는지 잠깐 망설이다가(다른 날짜·숫자는 말하지 않음) 올해 아래 날짜부터라고 확정한다.",
        must=[m, d], ban=["작년", "재작년"], gold=[("occurred_date", "INFORM", iso)]))(*_occ_parts(v))),
    T("O-T5-U", 5, "occurred_date", "어림으로만 말함 → UNCERTAIN", lambda v, r: dict(
        inst=r.choice(["며칠쯤 됐다고 어림으로만 말한다(예: 두 숫자에 걸친 일수).", "몇 달쯤 됐다고 어림으로만 말한다.",
                       "언제부터인지 기억이 안 난다고 한다.", "꽤 오래됐다고만 한다."]) + " 달·날을 특정하지 않는다.",
        must=[], ban=["월 ", "요일"], nums_ok=True, gold=[("occurred_date", "UNCERTAIN", "")])),
    T("O-T1-U", 1, "occurred_date", "달까지만 말하고 날은 말하지 않음 → UNCERTAIN", lambda v, r: (lambda o, yr: dict(
        inst="언제부터인지 묻는데 아래 표현으로 달까지만 말하고 며칠인지는 말하지 않는다. 초순·중순·말 같은 말도 쓰지 않는다.",
        must=[yr, month_read(o.month)], ban=["일부터", "일에", "일날", "일쯤", "초순", "중순", "월말", "말일", "며칠"],
        gold=[("occurred_date", "UNCERTAIN", "")]))(v["occ"], r.choice(["올해", f"{v['occ'].year}년", year_read(v["occ"].year) ]))),
    T("O-T8-I", 8, "occurred_date", "날짜가 정해진 기념일로 말함 → INFORM", lambda v, r: (lambda h: dict(
        inst="날짜 숫자는 말하지 않고 아래 기념일 이름과 '올해/작년'으로 언제부터인지 말한다. 그날부터라는 것이 분명해야 한다(무렵·쯤·전후 금지).",
        must=[h[1], h[0]], ban=["무렵", "쯤", "전후", "즈음", "근처"], order=[(h[1], h[0])],
        gold=[("occurred_date", "INFORM", h[2].isoformat())]))(_holiday(v["today"], r))),
    T("O-T9-I", 9, "occurred_date", "숫자·한글 표기 혼합 날짜 → INFORM", lambda v, r: (lambda o: dict(
        inst="아래 표현을 표기(숫자/한글) 그대로 섞어 쓴다. 올해 일이다.",
        must=r.choice([[f"{o.month}월", day_read(o.day)], [month_read(o.month), f"{o.day}일"]]), ban=["작년"],
        gold=[("occurred_date", "INFORM", o.isoformat())]))(v["occ"])),
    T("O-T10-I", 10, "occurred_date", "긴 사연 속에 날짜 한 번 → INFORM", lambda v, r: (lambda m, d, iso: dict(
        inst="불편했던 사정을 길게(60자 이상) 하소연하는 중간에 올해 아래 날짜부터 그랬다고 한 번만 말한다. 다른 날짜는 말하지 않는다.",
        must=[m, d], ban=["작년", "재작년"], nums_ok=True, gold=[("occurred_date", "INFORM", iso)]))(*_occ_parts(v))),
    T("O-T10-U", 10, "occurred_date", "긴 사연인데 시점이 둘이거나 흐릿함 → UNCERTAIN", lambda v, r: (lambda m, d, iso: dict(
        inst="길게(60자 이상) 하소연한다. 본인이 본 날은 아래 날짜인데 이웃 말로는 그보다 훨씬 전부터 그랬다고 해서 언제부터인지 정하지 못한다.",
        must=[m, d], ban=[], nums_ok=True, gold=[("occurred_date", "UNCERTAIN", "")]))(*_occ_parts(v))),
    T("O-T67-U", 6, "occurred_date", "되묻기·딴소리 → UNCERTAIN", lambda v, r: dict(
        inst=r.choice(["질문을 못 알아듣고 되묻기만 한다.", "언제부터인지는 답하지 않고 빨리 고쳐 달라고만 한다."]) + " 날짜·숫자는 말하지 않는다.",
        must=[], ban=[], gold=[("occurred_date", "UNCERTAIN", "")])),
    # ---------------- complaint_type
    T("C-T5-U", 5, "complaint_type", "무슨 민원인지 말하지 않음 → UNCERTAIN", lambda v, r: dict(
        inst=r.choice(["불편한 게 있어서 전화했다고만 하고 무슨 일인지는 말하지 않는다.", "할 말이 많아서 뭐부터 말할지 모르겠다고 한다.",
                       "질문을 되묻기만 한다."]), must=[], ban=[], gold=[("complaint_type", "UNCERTAIN", "")])),
    T("C-T10-I", 10, "complaint_type", "긴 사연으로 민원 한 가지를 설명 → INFORM", lambda v, r: (lambda c: dict(
        inst=f"'{c}'에 해당하는 일을 겪은 사정을 길게(80자 이상) 풀어서 말한다. 분류 이름 '{c}'를 그대로 쓰지 말고 상황으로 말한다. 다른 종류의 민원은 섞지 않는다.",
        must=[], ban=[], nums_ok=True, gold=[("complaint_type", "INFORM", c)]))(r.choice(COMPLAINTS))),
    T("C-T10-U", 10, "complaint_type", "긴 사연에 민원 두 가지 → UNCERTAIN", lambda v, r: (lambda cs: dict(
        inst=f"'{cs[0]}'에 해당하는 일과 '{cs[1]}'에 해당하는 일을 둘 다 접수해 달라고 길게(80자 이상) 말한다.",
        must=[], ban=[], nums_ok=True, gold=[("complaint_type", "UNCERTAIN", "")]))(r.sample(COMPLAINTS, 2))),
    # ---------------- consent
    T("S-T67-T", 6, "consent", "되묻거나 투덜대다가 동의 → INFORM true", lambda v, r: dict(
        inst="동의 질문을 되묻거나 왜 필요한지 투덜댄 뒤에 결국 동의한다고 분명히 말한다.",
        must=[], ban=[], gold=[("consent", "INFORM", "true")])),
    T("S-T7-F", 7, "consent", "분명히 거절 → INFORM false", lambda v, r: dict(
        inst="개인정보 수집에 동의하지 않는다고 분명히 말한다. 이유를 한마디 붙여도 된다.",
        must=[], ban=[], gold=[("consent", "INFORM", "false")])),
    T("S-T67-U", 7, "consent", "되묻기·걱정·따지기만 하고 동의 여부를 말하지 않음 → UNCERTAIN", lambda v, r: dict(
        inst=r.choice(["왜 그런 걸 하느냐고 묻기만 한다.", "동의하면 정보가 새는 것 아니냐고 걱정만 한다.",
                       "질문을 못 알아듣고 되묻기만 한다.", "잘 모르겠다고 한다."]) + " 동의한다/안 한다는 말은 하지 않는다.",
        must=[], ban=["동의합니다", "동의할게", "동의 안"], gold=[("consent", "UNCERTAIN", "")])),
    # ---------------- reply_channel
    T("R-T3-I", 3, "reply_channel", "본인 번호로 문자/전화 → INFORM", lambda v, r: (lambda ch: dict(
        inst=f"본인 번호로 '{ch}'로 알려 달라고 한다. 번호 숫자는 말하지 않는다.",
        must=[ch], ban=[], gold=[("reply_channel", "INFORM", ch)]))(r.choice(["문자", "전화"]))),
    T("R-T3-U", 3, "reply_channel", "가족에게 알려 달라고만 함 → UNCERTAIN", lambda v, r: (lambda f: dict(
        inst=f"본인 말고 '{f}'에게 알려 달라고만 하고 문자인지 전화인지는 말하지 않는다. 번호 숫자는 말하지 않는다.",
        must=[f], ban=["문자", "전화로"], gold=[("reply_channel", "UNCERTAIN", "")]))(r.choice(FAMILY))),
    T("R-T7-N", 7, "reply_channel", "연락 필요 없다고 함 → INFORM 회신 안 함", lambda v, r: dict(
        inst="처리만 해 주면 되고 결과 연락은 필요 없다고 한다.",
        must=[], ban=[], gold=[("reply_channel", "INFORM", "회신 안 함")])),
    T("R-T67-U", 6, "reply_channel", "되묻기·아무거나 → UNCERTAIN", lambda v, r: dict(
        inst=r.choice(["질문을 못 알아듣고 되묻기만 한다.", "문자든 전화든 아무거나 편한 대로 하라고 한다.", "그건 나중에 생각해 보겠다고 한다."]),
        must=[], ban=[], gold=[("reply_channel", "UNCERTAIN", "")])),
    # --- 11/19 추가: '몇 두 개'로 말했는데 자릿수가 모자람. '두 개' 표현이 INFORM에만 붙는 쏠림을 없애려는 것.
    #     requests 재실행 시 앞 변환의 난수 순서가 바뀌지 않도록 목록 맨 끝에 둠. 요청은 `append`로 따로 만든다.
    T("P-T8P-U", 8, "phone", "'몇 두 개'로 조립했는데 자릿수가 모자람 → UNCERTAIN", lambda v, r: (lambda p, k, f: dict(
        inst=("가운데 네 자리는 두 자리만 아래 표현처럼 개수로 말하고 끝 네 자리는 그대로 말한다. 가운데가 모자란다는 말은 하지 않고, 다른 숫자를 덧붙이지 않는다."
              if k == "mid" else
              "가운데 네 자리까지는 말하고 끝자리는 아래 표현만 말하고 끝낸다. 모자란다는 말은 하지 않고, 다른 숫자를 덧붙이지 않는다."),
        must=([p["a"], f(f"{digits_read(p['bn'][0])} 두 개"), p["c"]] if k == "mid" else
              [p["a"], p["b"], f({"two": f"{digits_read(p['cn'][0])} 두 개",
                                  "two1": f"{digits_read(p['cn'][0])} 두 개 {digits_read(p['cn'][2])}",
                                  "one2": f"{digits_read(p['cn'][0])} {digits_read(p['cn'][2])} 두 개",
                                  "three": f"{digits_read(p['cn'][0])} 세 개"}[k])]),
        ban=[], gold=[("phone", "UNCERTAIN", "")]))(
        _p(v), r.choice(["two", "two1", "two1", "one2", "three", "mid"]),
        (lambda rr: (lambda s: s.replace("두 개", rr).replace("세 개", {"두개": "세개", "2개": "3개"}.get(rr, "세 개"))))(r.choice(["두 개", "두 개", "두개", "2개"])))),
    T("B-T8P-U", 8, "birth_date", "연도 뒤에 '몇 두 개' 두 자리만 말함 → UNCERTAIN", lambda v, r: (lambda yy, bp: None if bp is None else dict(
        inst="연도는 뒤 두 자리를 말하고, 그 뒤는 아래 개수 표현 하나만 말하고 끝낸다. 그것이 달인지 날인지 밝히지 않고, 나머지 숫자는 말하지 않는다.",
        must=[yy + "년", r.choice([x for x in bp if "두 개" in x]).replace("두 개", r.choice(["두 개", "두 개", "두개", "2개"]))],
        ban=[], gold=[("birth_date", "UNCERTAIN", "")]))(digits_read(f"{v['birth'].year % 100:02d}"), _birth_pairs(v["birth"]))),
    # --- 11/19 저녁 추가: 가족 말이 나오면 UNCERTAIN으로만 쏠리는 것(phone 60:4, name 56:8, reply 30:3)과
    #     기념일이 INFORM으로만 쏠리는 것(30:0)을 줄이는 반대쪽 예시.
    T("P-T3F-I", 3, "phone", "가족 이야기를 꺼내지만 본인 번호를 말함 → INFORM", lambda v, r: (lambda p, f: dict(
        inst=f"'{f}' 이야기를 한마디 꺼내지만(예: 대신 전화를 걸어 줬다, 전화기를 사 줬다, 그쪽 번호 말고) 그 사람의 번호는 말하지 않고, 본인 번호라는 것을 밝히며 전부 말한다.",
        must=[f, p["a"], p["b"], p["c"]], ban=[], gold=[("phone", "INFORM", p["iso"])]))(_p(v), r.choice(FAMILY))),
    T("N-T3F-I", 3, "name", "가족 이야기를 꺼내지만 본인 이름을 말함 → INFORM", lambda v, r: (lambda f: dict(
        inst=f"'{f}' 이야기를 한마디 꺼내지만 그 사람의 이름은 말하지 않고 본인 이름 석 자를 말한다. 본인 이름이라는 것이 발화에서 분명해야 한다.",
        must=[f, v["name"]], ban=[], gold=[("name", "INFORM", v["name"])]))(r.choice(FAMILY))),
    T("R-T3F-I", 3, "reply_channel", "가족 말고 본인에게 문자/전화 → INFORM", lambda v, r: (lambda f, ch: dict(
        inst=f"'{f}' 말고 본인에게 '{ch}'로 알려 달라고 한다. 번호 숫자는 말하지 않는다.",
        must=[f, ch], ban=[], gold=[("reply_channel", "INFORM", ch)]))(r.choice(FAMILY), r.choice(["문자", "전화"]))),
    T("O-T8-U", 8, "occurred_date", "기념일 무렵이라고 어림으로만 말함 → UNCERTAIN", lambda v, r: (lambda h: dict(
        inst="날짜 숫자는 말하지 않고 아래 기념일 이름과 '올해/작년'으로 말하되, 그날부터가 아니라 그 무렵·전후·며칠 지나서라고 어림으로만 말한다.",
        must=[h[1], h[0]], ban=["그날부터", "당일"], order=[(h[1], h[0])],
        gold=[("occurred_date", "UNCERTAIN", "")]))(_holiday(v["today"], r))),
]
TRANSFORM_BY_ID = {t["id"]: t for t in TRANSFORMS}
LATE_IDS = {"P-T8P-U", "B-T8P-U", "P-T3F-I", "N-T3F-I", "R-T3F-I", "O-T8-U"}  # 목록 끝에 나중에 추가한 변환(append로만 요청 생성)

STYLES = [
    "짧게 툭 던지듯이", "공손한 합쇼체로", "반말을 섞어서", "'그', '저', '뭐더라' 같은 군말을 넣어서",
    "혼잣말을 조금 섞어서", "같은 말을 한 번 되풀이하면서", "말끝을 흐리면서", "조금 퉁명스럽게",
    "천천히 또박또박", "말을 고르다가 이어 가듯이", "상담원을 '아가씨' 또는 '선생님'으로 부르면서", "한숨을 섞어서",
]

GEN_SYSTEM = """너는 구청 민원 전화 접수 대화의 학습 데이터를 쓰는 작성자다.
60~80대 민원인이 상담원 질문에 답하는 발화를 **한 개** 쓴다. 전화 통화를 받아 적은 글처럼 쓴다.

규칙
1. [변형 지시]를 그대로 따른다. 지시에 없는 정보(다른 날짜·번호·이름·주소)는 넣지 않는다.
2. [반드시 포함]의 표현은 글자 하나, 띄어쓰기 하나 바꾸지 말고 그대로 넣는다. 숫자를 한글로, 한글을 숫자로 바꾸지 않는다.
3. [포함 금지]의 표현은 쓰지 않는다.
4. 사투리와 지명은 쓰지 않는다. 문장부호는 거의 쓰지 않는다.
5. [말투]를 반영하되 매번 문장 구조를 다르게 쓴다. "~이요" 한 가지로 끝내지 않는다.
6. 출력은 JSON 한 개: {"utterance": "..."}"""

DIV_SYSTEM = """너는 구청 민원 전화 접수 대화의 학습 데이터를 고쳐 쓰는 작성자다.
민원인 발화 한 개를 받아 **뜻과 값은 그대로 두고 말투만** 바꾼다.

규칙
1. 숫자·날짜·이름 표현은 글자 그대로, 나온 순서 그대로 둔다. 새 숫자·이름을 넣지 않는다.
2. 고쳐 말하는 문장이면 '틀린 값 → 맞는 값' 순서를 지킨다.
3. 바꿀 것: 어순, 말끝, 군말(그, 저, 뭐), 호칭. 문장 구조가 원문과 눈에 띄게 달라야 한다.
4. 사투리와 지명은 쓰지 않는다. 문장부호는 거의 쓰지 않는다.
5. 출력은 JSON 한 개: {"utterance": "..."}"""


# ---------------------------------------------------------------------------
def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def raw_lines(path):
    with open(path, encoding="utf-8") as f:
        return [l.rstrip("\n") for l in f if l.strip()]


# ---------------------------------------------------------------------------
# 1) 줄이기
# ---------------------------------------------------------------------------
def reduce_items(items, cap, seed):
    """틀당 cap개까지만 남긴다. UNCERTAIN이 들어간 턴은 줄이지 않는다(부족한 쪽).
    한 틀 안에서는 패턴 코드를 돌아가며 뽑아 특정 패턴이 통째로 빠지지 않게 한다."""
    rng = random.Random(seed)
    groups = defaultdict(list)
    for x in items:
        groups[template(x["utt"], names_of(x))].append(x)
    keep, drop = set(), set()
    for t, g in groups.items():
        protected = [x for x in g if any(a["act"] == "UNCERTAIN" for a in x["actions"])]
        rest = [x for x in g if x not in protected]
        for x in protected:
            keep.add(x["line"])
        room = max(0, cap - len(protected))
        if len(rest) <= room:
            keep.update(x["line"] for x in rest)
            continue
        by_pat = defaultdict(list)
        for x in rest:
            by_pat[x["pattern"]].append(x)
        for v in by_pat.values():
            rng.shuffle(v)
        order = []
        while any(by_pat.values()):
            for p in sorted(by_pat):
                if by_pat[p]:
                    order.append(by_pat[p].pop())
        keep.update(x["line"] for x in order[:room])
        drop.update(x["line"] for x in order[room:])
    return keep, drop, groups


def cmd_reduce(args):
    items = load_sft(args.train)
    lines = raw_lines(args.train)
    keep, drop, groups = reduce_items(items, args.cap, args.seed)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "kept.jsonl").write_text("\n".join(lines[i] for i in sorted(keep)) + "\n", encoding="utf-8")
    (OUT / "removed.jsonl").write_text("\n".join(lines[i] for i in sorted(drop)) + "\n", encoding="utf-8")
    n = len(items)
    pat_before = Counter(x["pattern"] for x in items)
    pat_after = Counter(x["pattern"] for x in items if x["line"] in keep)
    cell = lambda x: (x["actions"][0]["slot"], x["actions"][0]["act"]) if x["actions"] else ("-", "-")
    cb, ca = Counter(map(cell, items)), Counter(cell(x) for x in items if x["line"] in keep)
    rep = [f"# 줄이기 결과 (틀당 {args.cap}개, seed {args.seed})\n",
           f"- {n:,}턴 → 남김 {len(keep):,} / 뺌 {len(drop):,} ({len(drop) / n:.1%})",
           f"- cap을 넘던 틀: {sum(len(g) > args.cap for g in groups.values())}개 / 전체 틀 {len(groups):,}개",
           "- UNCERTAIN이 들어간 턴은 줄이지 않음\n",
           "| 칸(첫 슬롯·라벨) | 전 | 후 | 뺀 수 |\n|---|---:|---:|---:|"]
    for k in sorted(cb, key=lambda k: -cb[k]):
        rep.append(f"| {k[0]} {k[1]} | {cb[k]:,} | {ca[k]:,} | {cb[k] - ca[k]:,} |")
    rep.append("\n| 패턴 | 전 | 후 | 남은 비율 |\n|---|---:|---:|---:|")
    for p in sorted(pat_before, key=lambda p: pat_after[p] / pat_before[p]):
        rep.append(f"| {p} | {pat_before[p]} | {pat_after[p]} | {pat_after[p] / pat_before[p]:.0%} |")
    (OUT / "reduce_report.md").write_text("\n".join(rep), encoding="utf-8")
    print("\n".join(rep[:14]))
    print(f"\n→ {OUT}\\kept.jsonl, removed.jsonl, reduce_report.md")


# ---------------------------------------------------------------------------
# 2) 요청 만들기
# ---------------------------------------------------------------------------
def value_pool(items):
    names, births, phones, todays = set(), set(), set(), []
    for x in items:
        for a in x["actions"]:
            if a["act"] != "INFORM" or not a["canonical_values"]:
                continue
            v = a["canonical_values"][0]
            if a["slot"] == "name" and re.fullmatch(r"[가-힣]{3}", v):
                names.add(v)
            elif a["slot"] == "birth_date" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                births.add(v)
            elif a["slot"] == "phone" and re.fullmatch(r"010-\d{4}-\d{4}", v):
                phones.add(v)
    return sorted(names), sorted(births), sorted(phones)


def cmd_requests(args):
    rng = random.Random(args.seed)
    items = load_sft(args.train)
    names, births, phones = value_pool(items)
    todays = sorted({re.search(r"오늘 날짜: (\d{4}-\d{2}-\d{2})", l).group(1) for l in raw_lines(args.train)})
    pair_phones = [p for p in phones if _pairs_read(p.split("-")[2])]
    weights = json.load(open(args.weights, encoding="utf-8")) if args.weights else {}
    reqs = []
    only = set(getattr(args, "ids", None) or [])
    for t in TRANSFORMS:
        if (t["id"] in LATE_IDS) != bool(only) or (only and t["id"] not in only):
            continue
        n = int(weights.get(t["id"], args.per))
        made, tries = 0, 0
        while made < n and tries < n * 20:
            tries += 1
            today = date.fromisoformat(rng.choice(todays))
            occ = today - timedelta(days=rng.randint(2, min(240, (today - date(today.year, 1, 1)).days)))
            v = {"name": rng.choice(names), "birth": date.fromisoformat(rng.choice(births)),
                 "phone": rng.choice(pair_phones if t["id"] == "P-T8-I" and pair_phones else phones),
                 "today": today, "occ": occ}
            spec = t["make"](v, rng)
            if spec is None or len(set(spec["must"])) != len(spec["must"]):
                continue
            if any(a != b and a in b for a in spec["must"] for b in spec["must"]):
                continue  # 한 표현이 다른 표현에 포함되면 검사가 모호해짐 (예: 일일 ⊂ 십일일)
            style = rng.choice(STYLES)
            user = (f"[상담원 질문] {STD_Q[t['slot']]}\n[변형 지시] {spec['inst']}\n"
                    f"[반드시 포함] {' / '.join(spec['must']) or '(없음)'}\n"
                    f"[포함 금지] {' / '.join(spec['ban']) or '(없음)'}\n[말투] {style}")
            made += 1
            reqs.append({"req_id": f"{t['id']}_{made:04d}", "kind": "transform", "transform": t["id"], "hard": t["hard"],
                         "slot": t["slot"], "today": today.isoformat(), "must": spec["must"], "ban": spec["ban"],
                         "order": spec.get("order", []), "nums_ok": bool(spec.get("nums_ok")), "gold": spec["gold"],
                         "name": v["name"], "system": GEN_SYSTEM, "user": user})
    if only:  # append: 기존 requests.jsonl 뒤에 붙이고 주문서 묶음을 따로 씀
        prev = read_jsonl(OUT / "requests.jsonl")
        have = {r["req_id"] for r in prev}
        reqs = [r for r in reqs if r["req_id"] not in have]
        write_jsonl(OUT / "requests.jsonl", prev + reqs)
        (OUT / "batches").mkdir(exist_ok=True)
        body = "\n\n".join("### " + r["req_id"] + "\n" + r["user"] for r in reqs)
        (OUT / "batches" / args.batch).write_text(GEN_SYSTEM + "\n\n" + body + "\n", encoding="utf-8")
        print(f"추가 요청 {len(reqs)}건 → requests.jsonl 뒤에 붙임, 주문서 {OUT / 'batches' / args.batch}")
        return
    n_tr = len(reqs)
    removed = OUT / "removed.jsonl"
    if removed.exists() and not args.no_diversify:
        rem = load_sft(removed)
        rem_lines = raw_lines(removed)
        rng.shuffle(rem)
        for x in rem[: args.diversify_max]:
            reqs.append({"req_id": f"DIV_{x['line']:05d}", "kind": "diversify", "src_line": rem_lines[x["line"]],
                         "src_utt": x["utt"], "names": names_of(x), "system": DIV_SYSTEM,
                         "user": f"[원문] {x['utt']}\n[말투] {rng.choice(STYLES)}"})
    write_jsonl(OUT / "requests.jsonl", reqs)
    c = Counter(r["transform"] for r in reqs if r["kind"] == "transform")
    print(f"유형 변환 요청 {n_tr}건 (변환 {len(c)}종), 표현 다양화 요청 {len(reqs) - n_tr}건 → {OUT}\\requests.jsonl")
    cells = Counter((r["gold"][0][0], r["gold"][0][1]) for r in reqs if r["kind"] == "transform")
    for k in sorted(cells):
        print(f"  {k[0]:15s} {k[1]:9s} {cells[k]}")


# ---------------------------------------------------------------------------
# 3) LLM 호출 (OpenAI 호환)
# ---------------------------------------------------------------------------
def cmd_run(args):
    import os
    reqs = read_jsonl(OUT / "requests.jsonl")
    out_path = OUT / "responses.jsonl"
    done = {r["req_id"] for r in read_jsonl(out_path)} if out_path.exists() else set()
    key = os.environ.get(args.api_key_env, "EMPTY")
    todo = [r for r in reqs if r["req_id"] not in done][: args.limit or None]
    print(f"요청 {len(reqs)}건 중 남은 {len(todo)}건 실행")
    with open(out_path, "a", encoding="utf-8") as f:
        for i, r in enumerate(todo, 1):
            body = {"model": args.model, "temperature": args.temperature, "max_tokens": 400,
                    "messages": [{"role": "system", "content": r["system"]}, {"role": "user", "content": r["user"]}]}
            req = urllib.request.Request(args.base_url.rstrip("/") + "/chat/completions",
                                         data=json.dumps(body).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    text = json.load(resp)["choices"][0]["message"]["content"]
            except Exception as e:  # 실패한 요청은 기록하지 않아 다음 실행 때 다시 시도됨
                print(f"  {r['req_id']} 실패: {type(e).__name__}")
                continue
            f.write(json.dumps({"req_id": r["req_id"], "text": text}, ensure_ascii=False) + "\n")
            f.flush()
            if i % 50 == 0:
                print(f"  {i}/{len(todo)}")


# ---------------------------------------------------------------------------
# 4) 검사 + 조립
# ---------------------------------------------------------------------------
def parse_utt(text):
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return str(json.loads(m.group(0)).get("utterance", "")).strip()
        except Exception:
            pass
    return ""


def check_transform(r, utt):
    """통과하면 None, 아니면 탈락 사유"""
    if not utt:
        return "출력 형식"
    for s in r["must"]:
        if s not in utt:
            return "필수 표현 빠짐"
    for s in r["ban"]:
        if s in utt:
            return "금지 표현 포함"
    for a, b in r["order"]:
        if utt.rfind(a) > utt.rfind(b) or utt.find(a) > utt.rfind(b):
            return "값 순서 틀림"
    if not r["nums_ok"]:
        rest = utt
        for s in sorted(r["must"], key=len, reverse=True):
            rest = rest.replace(s, " ")
        if re.search(r"\d", rest) or "<N>" in template(rest, [r["name"]]):
            return "지시에 없는 숫자"
    if "긴 사연" in TRANSFORM_BY_ID[r["transform"]]["desc"] and len(utt) < 50:
        return "길이 부족"
    return None


def order_gold(r, utt):
    """슬롯이 둘이면 발화에서 먼저 말한 슬롯을 앞에 둔다(v3.1 관례: 말한 순서)."""
    gold = [tuple(g) for g in r["gold"]]
    if len(gold) < 2:
        return gold
    special = {g[2] for g in gold if g[0] in ("name", "reply_channel") and g[2]}

    def pos(g):
        if g[0] == "name":
            return utt.find(g[2])
        if g[0] == "reply_channel":
            m = re.search(re.escape(g[2]) + r"(?!번호|기)", utt)
            return m.start() if m else len(utt)
        ps = [utt.find(s) for s in r["must"] if s not in special and s in utt]
        return min(ps) if ps else len(utt)
    return sorted(gold, key=pos)


def sft_line(system_template, today, slot, utt, gold, pattern, did):
    hist = [f"SYSTEM: {OPENING_Q}"]
    if slot != "consent":
        hist += [f"USER: {OPENING_A}", f"SYSTEM: {STD_Q[slot]}"]
    actions = [{"act": a, "slot": s, "values": [v] if a == "INFORM" else [],
                "canonical_values": [v] if a == "INFORM" else []} for s, a, v in gold]
    return json.dumps({"messages": [
        {"role": "system", "content": system_template.replace("{call_date}", today)},
        {"role": "user", "content": "[대화 이력]\n" + "\n".join(hist) + f"\n\n[마지막 USER 발화]\n{utt}"},
        {"role": "assistant", "content": json.dumps({"active_intent": INTENT, "actions": actions}, ensure_ascii=False)}],
        "pattern": pattern, "dialogue_id": did}, ensure_ascii=False)


def cmd_build(args):
    system_template = (BASE / "system_prompt_template.txt").read_text(encoding="utf-8")
    reqs = {r["req_id"]: r for r in read_jsonl(OUT / "requests.jsonl")}
    resp = {r["req_id"]: r["text"] for r in read_jsonl(OUT / "responses.jsonl")}
    base_items = load_sft(args.train)
    base_lines = raw_lines(args.train)
    kept_lines = raw_lines(OUT / "kept.jsonl")
    base_utts = {x["utt"].strip() for x in base_items}
    tpl_count = Counter(template(x["utt"], names_of(x)) for x in load_sft(OUT / "kept.jsonl"))

    fails = defaultdict(Counter)
    new_tr, new_div, review = [], [], []
    seen = set()
    for rid, r in reqs.items():
        if rid not in resp:
            fails[r.get("transform", "DIV")]["응답 없음"] += 1
            continue
        utt = parse_utt(resp[rid])
        key = r.get("transform", "DIV")
        if r["kind"] == "transform":
            why = check_transform(r, utt)
            names = [r["name"]]
        else:
            names = r["names"]
            why = (None if utt else "출력 형식")
            if not why and value_signature(utt, names) != value_signature(r["src_utt"], names):
                why = "값 또는 값 순서 바뀜"
            if not why and template(utt, names) == template(r["src_utt"], names):
                why = "틀이 원문과 같음"
        if not why and (utt in base_utts or utt in seen):
            why = "기존 발화와 중복"
        t = template(utt, names) if not why else None
        if not why and tpl_count[t] >= args.cap:
            why = f"틀당 {args.cap}개 초과"
        if why:
            fails[key][why] += 1
            continue
        seen.add(utt)
        tpl_count[t] += 1
        if r["kind"] == "transform":
            new_tr.append(sft_line(system_template, r["today"], r["slot"], utt, order_gold(r, utt), f"V32-{r['transform']}", rid))
            review.append({"req_id": rid, "transform": r["transform"], "hard_type": r["hard"],
                           "desc": TRANSFORM_BY_ID[r["transform"]]["desc"], "utterance": utt,
                           "gold": " ; ".join(f"{s}|{a}|{v}" for s, a, v in r["gold"]), "유형 맞음(Y/N)": "", "라벨 맞음(Y/N)": ""})
        else:
            o = json.loads(r["src_line"])
            o["messages"][1]["content"] = o["messages"][1]["content"].rsplit("[마지막 USER 발화]\n", 1)[0] + "[마지막 USER 발화]\n" + utt
            o["dialogue_id"] = f"{o.get('dialogue_id', '')}-DIV"
            new_div.append(json.dumps(o, ensure_ascii=False))

    a_lines = base_lines + new_tr
    b_lines = kept_lines + new_tr + new_div
    (OUT / "sft_train_v3_2_A.jsonl").write_text("\n".join(a_lines) + "\n", encoding="utf-8")
    (OUT / "sft_train_v3_2_B.jsonl").write_text("\n".join(b_lines) + "\n", encoding="utf-8")
    (OUT / "v32_transform_only.jsonl").write_text("\n".join(new_tr) + "\n", encoding="utf-8")
    # 유형 부합 확인용 표본: 변환별 최대 --review-per 건
    rng = random.Random(args.seed)
    by = defaultdict(list)
    for r in review:
        by[r["transform"]].append(r)
    sample = [r for k in sorted(by) for r in rng.sample(by[k], min(args.review_per, len(by[k])))]
    with open(OUT / "review_sample.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sample[0].keys()) if sample else ["req_id"])
        w.writeheader()
        w.writerows(sample)

    rep = ["# v3.2 조립 결과\n",
           f"- 실험 A (v3.1 + 유형 변환): {len(base_lines):,} + {len(new_tr):,} = {len(a_lines):,}줄",
           f"- 실험 B (줄인 v3.1 + 유형 변환 + 표현 다양화): {len(kept_lines):,} + {len(new_tr):,} + {len(new_div):,} = {len(b_lines):,}줄",
           f"- 유형 부합 확인 표본: {len(sample)}건 (review_sample.csv)\n",
           "| 변환 | 요청 | 통과 | 통과율 | 탈락 사유 |\n|---|---:|---:|---:|---|"]
    req_n = Counter(r.get("transform", "DIV") for r in reqs.values())
    pass_n = Counter(r["transform"] for r in review)
    pass_n["DIV"] = len(new_div)
    for k in sorted(req_n):
        rep.append(f"| {k} | {req_n[k]} | {pass_n[k]} | {pass_n[k] / req_n[k]:.0%} | "
                   + ", ".join(f"{w} {c}" for w, c in fails[k].most_common()) + " |")
    (OUT / "build_report.md").write_text("\n".join(rep), encoding="utf-8")
    print("\n".join(rep))
    print("\n다음: python dist_train.py out/v32/sft_train_v3_2_B.jsonl --name v3.2-B  (분포 전후 표)")


def cmd_list(args):
    print("| id | 하드 유형 | 슬롯 | 변형 → 라벨 |\n|---|---:|---|---|")
    for t in TRANSFORMS:
        print(f"| {t['id']} | {t['hard']} | {t['slot']} | {t['desc']} |")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("reduce"); p.add_argument("--train", required=True); p.add_argument("--cap", type=int, default=10)
    p.add_argument("--seed", type=int, default=0); p.set_defaults(fn=cmd_reduce)
    p = sub.add_parser("requests"); p.add_argument("--train", required=True); p.add_argument("--weights")
    p.add_argument("--per", type=int, default=30); p.add_argument("--seed", type=int, default=0)
    p.add_argument("--no-diversify", action="store_true"); p.add_argument("--diversify-max", type=int, default=100000)
    p.set_defaults(fn=cmd_requests)
    p = sub.add_parser("append"); p.add_argument("--train", required=True); p.add_argument("--weights"); p.add_argument("--ids", nargs="+", required=True)
    p.add_argument("--per", type=int, default=30); p.add_argument("--seed", type=int, default=1); p.add_argument("--batch", default="e01.txt")
    p.add_argument("--no-diversify", action="store_true"); p.set_defaults(fn=cmd_requests)
    p = sub.add_parser("run"); p.add_argument("--base-url", required=True); p.add_argument("--model", required=True)
    p.add_argument("--api-key-env", default="OPENAI_API_KEY"); p.add_argument("--temperature", type=float, default=0.9)
    p.add_argument("--limit", type=int, default=0); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("build"); p.add_argument("--train", required=True); p.add_argument("--cap", type=int, default=10)
    p.add_argument("--review-per", type=int, default=15); p.add_argument("--seed", type=int, default=0)
    p.set_defaults(fn=cmd_build)
    p = sub.add_parser("list"); p.set_defaults(fn=cmd_list)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
