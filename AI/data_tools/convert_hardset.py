# -*- coding: utf-8 -*-
"""하드 테스트셋 설계표(CSV) → minwon_eval 형식 json + SFT jsonl + 평가 턴 jsonl.

누수 방지: 이 스크립트는 **발화·정답 내용을 화면에 찍지 않는다.** 개수와 id만 찍는다.
test 결과물은 hardset/test_DO_NOT_OPEN/ 에 쓰고, 보강 담당(채연)은 열지 않는다.

사용:
  python convert_hardset.py                       # 카카오톡 폴더의 설계표 CSV 2개를 자동으로 찾음
  python convert_hardset.py --src a.csv b.csv     # 직접 지정
  python convert_hardset.py --orig-questions      # 표준 질문 대신 설계표 질문 문구 사용

변환 규칙
  - 대화 뼈대 = [동의 질문 → "네 동의합니다."(eval=False)] + [슬롯 질문 → 발화]. raw 변환(convert_raw.py)과 같음
  - 목표 슬롯이 consent면 뼈대 없이 [동의 질문 → 발화]
  - SYSTEM 질문은 합성 데이터의 표준 질문으로 치환(학습 때 본 질문과 같게 해서 '발화 유형'만 변수로 둠).
    설계표 원문 질문은 source.orig_question에 보존
  - '직전 턴' 칸이 '필요'로 시작하면 합성 데이터의 복창-교정 형식으로 이력을 넣음:
      질문 → "<오복창 값>이요"(eval=False) → "<오복창 값> 맞으세요?" → 발화
    (name·phone만. 카드의 '오복창' 값을 씀. 다른 슬롯이면 넣지 않고 경고)
  - 정답 = '최종' 칸에 "-> slot | act | value"가 있으면 그것, 없으면 '정답 슬롯·행위·값 (작성)' 칸
  - 정답 여러 줄 = 한 발화에 여러 action. 목표 슬롯이 맨 앞
  - call_date = '기준일' 칸, 비면 --default-call-date
"""
import argparse
import csv
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
SERVICE = "민원접수"
INTENT = "FileComplaint"
OPENING_Q = "안녕하세요 구청 민원 접수입니다. 민원 접수를 위해 개인정보 수집에 동의하시나요?"
OPENING_A = "네 동의합니다."
STD_QUESTION = {
    "consent": OPENING_Q,
    "name": "성함이 어떻게 되세요?",
    "birth_date": "생년월일을 말씀해 주시겠어요?",
    "phone": "연락받으실 전화번호를 알려주세요.",
    "complaint_type": "어떤 일로 연락 주셨어요?",
    "occurred_date": "언제부터 그러셨어요?",
    "reply_channel": "처리 결과는 어떻게 알려드릴까요?",
}
ENUMS = {
    "consent": {"true", "false"},
    "complaint_type": {"불법 주정차", "도로·보도 파손", "가로등·보안등 고장", "불법 광고물", "쓰레기·동물 사체", "기타"},
    "reply_channel": {"문자", "전화", "회신 안 함"},
}
DEFAULT_SRC_GLOB = "C:/Users/user/Documents/카카오톡 받은 파일/하드 테스트셋 설계표*설계표.csv"
ANS_RE = re.compile(r"^\s*(?:'?->\s*)?(\w+)\s*\|\s*(INFORM|UNCERTAIN)\s*\|\s*(.*?)\s*$")


def col(row, prefix):
    for k, v in row.items():
        if k and k.startswith(prefix):
            return (v or "").strip()
    return ""


def parse_answers(text):
    out = []
    for line in text.splitlines():
        m = ANS_RE.match(line)
        if m:
            slot, act, val = m.groups()
            out.append((slot, act, "" if val.lower() in ("null", "none", "") else val))
    return out


def final_answers(row):
    """(answers, 출처). 최종 칸의 '-> ...'가 있으면 우선."""
    fin = [a for l in col(row, "최종").splitlines() if "->" in l for a in parse_answers(l[l.index("->"):])]
    if fin:
        return fin, "최종"
    return parse_answers(col(row, "정답 슬롯")), "작성"


def validate(slot, act, val):
    if slot not in STD_QUESTION:
        return f"모르는 슬롯 {slot}"
    if act == "UNCERTAIN":
        return "UNCERTAIN인데 값이 있음" if val else None
    if not val:
        return "INFORM인데 값이 없음"
    if slot in ENUMS and val not in ENUMS[slot]:
        return "허용 값 목록에 없음"
    if slot in ("birth_date", "occurred_date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}( \(음력\))?", val):
        return "날짜 형식 아님"
    if slot == "phone" and not re.fullmatch(r"010-\d{4}-\d{4}", val):
        return "전화번호 형식 아님"
    if slot == "name" and not re.fullmatch(r"[가-힣]{2,5}", val):
        return "이름 형식 아님"
    return None


def action(slot, act, val):
    v = [val] if act == "INFORM" else []
    return {"act": act, "slot": slot, "values": v, "canonical_values": list(v)}


def sys_turn(utt):
    return {"speaker": "SYSTEM", "utterance": utt, "frames": [{"service": SERVICE, "actions": [], "state": None}]}


def user_turn(utt, actions, evaluate):
    t = {"speaker": "USER", "utterance": utt,
         "frames": [{"service": SERVICE, "actions": actions,
                     "state": {"active_intent": INTENT, "requested_slots": [], "slot_values": {}}}]}
    if not evaluate:
        t["eval"] = False
    return t


def misread_value(row, slot):
    """카드의 오복창 값. name: '김영숙 (김영순)' → 김영순 / phone: '010-3344-7120 (7210)' → 010-3344-7210"""
    if slot == "name":
        m = re.search(r"\(([가-힣]+)\)", col(row, "카드 이름"))
        return m.group(1) if m else None
    if slot == "phone":
        m = re.match(r"\s*(010-\d{4})-\d{4}\s*\((\d{4})\)", col(row, "카드 번호"))
        return f"{m.group(1)}-{m.group(2)}" if m else None
    return None


def build(row, author, args, warnings):
    rid = col(row, "id")
    target = col(row, "목표 슬롯")
    answers, ans_src = final_answers(row)
    if not answers:
        warnings.append(f"{rid}: 정답 칸을 읽지 못함 → 제외")
        return None
    for s, a, v in answers:
        err = validate(s, a, v)
        if err:
            warnings.append(f"{rid}: {s} {a} {err}")
    answers.sort(key=lambda x: x[0] != target)  # 목표 슬롯 먼저
    if answers[0][0] != target:
        warnings.append(f"{rid}: 정답에 목표 슬롯({target})이 없음")
    if answers[0][1] != col(row, "목표 라벨") and ans_src == "작성":
        warnings.append(f"{rid}: 목표 라벨 칸과 정답 칸의 행위가 다름")

    utt = col(row, "발화")
    orig_q = re.sub(r"^Q\d+\s*", "", col(row, "질문"))
    question = orig_q if args.orig_questions else STD_QUESTION.get(target, orig_q)
    call_date = col(row, "기준일") or args.default_call_date
    acts = [action(*a) for a in answers]

    turns = [sys_turn(OPENING_Q)]
    prev_mode = "none"
    if target != "consent":
        turns.append(user_turn(OPENING_A, [action("consent", "INFORM", "true")], False))
        turns.append(sys_turn(question))
        if col(row, "직전 턴").startswith("필요"):
            mis = misread_value(row, target)
            if mis:
                turns.append(user_turn(f"{mis}이요", [action(target, "INFORM", mis)], False))
                turns.append(sys_turn(f"{mis} 맞으세요?"))
                prev_mode = "readback"
            else:
                warnings.append(f"{rid}: 직전 턴 필요 표시인데 {target}은 복창 값이 없어 이력 미삽입")
                prev_mode = "missing"
    elif args.orig_questions:
        turns[0] = sys_turn(orig_q)
    turns.append(user_turn(utt, acts, True))

    m = re.match(r"\s*(\d+)\s*(.*)", col(row, "유형"))
    type_no, type_name = (int(m.group(1)), m.group(2).strip()) if m else (0, col(row, "유형"))
    diff = col(row, "난이도")
    return {
        "dialogue_id": rid,
        "services": [SERVICE],
        "pattern": f"H{type_no:02d}",
        "type": f"{type_no} {type_name}",
        "difficulty": int(diff) if diff.isdigit() else None,
        "call_date": call_date,
        "turns": turns,
        # 평가·분석용. 모델 입력에는 들어가지 않음
        "source": {"split": col(row, "split"), "author": author, "card": col(row, "카드"),
                   "target_slot": target, "target_act": answers[0][1], "pair": col(row, "짝"),
                   "orig_question": orig_q, "prev_turn": prev_mode, "answer_from": ans_src,
                   "review": col(row, "일치")},
    }


def to_sft(d, system_template):
    turns = d["turns"]
    k = len(turns) - 1
    hist = "\n".join(f"{t['speaker']}: {t['utterance']}" for t in turns[:k])
    user = f"[대화 이력]\n{hist}\n\n[마지막 USER 발화]\n{turns[k]['utterance']}"
    asst = json.dumps({"active_intent": INTENT, "actions": turns[k]["frames"][0]["actions"]}, ensure_ascii=False)
    return {"messages": [{"role": "system", "content": system_template.replace("{call_date}", d["call_date"])},
                         {"role": "user", "content": user},
                         {"role": "assistant", "content": asst}],
            "pattern": d["pattern"], "dialogue_id": d["dialogue_id"]}


def to_eval_turn(d):
    """out/raw_eval_turns.jsonl(팀 results_v2_baseline.jsonl 입력 필드)과 같은 형식 + type/difficulty."""
    turns = d["turns"]
    k = len(turns) - 1
    prev_state = {}
    for t in turns[:k]:
        if t["speaker"] == "USER":
            for a in t["frames"][0]["actions"]:
                if a["act"] == "INFORM":
                    prev_state[a["slot"]] = a["canonical_values"]
    return {"dialogue_id": d["dialogue_id"], "turn": str(k), "variant": "hard", "service": SERVICE,
            "history": [f"{t['speaker']}: {t['utterance']}" for t in turns[:k]],
            "utterance": turns[k]["utterance"], "noise": [d["pattern"]], "category": [d["type"]],
            "gold": {"active_intent": INTENT, "actions": turns[k]["frames"][0]["actions"]},
            "prev_state": prev_state, "today": d["call_date"],
            "type": d["type"], "difficulty": d["difficulty"], "source": d["source"]}


def write_split(items, outdir, name, system_template):
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"hard_{name}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(outdir / f"hard_{name}_sft.jsonl", "w", encoding="utf-8") as f:
        for d in items:
            f.write(json.dumps(to_sft(d, system_template), ensure_ascii=False) + "\n")
    with open(outdir / f"hard_{name}_eval_turns.jsonl", "w", encoding="utf-8") as f:
        for d in items:
            f.write(json.dumps(to_eval_turn(d), ensure_ascii=False) + "\n")


def summary(items, name):
    print(f"\n[{name}] {len(items)}문제")
    by_type = Counter((d["type"], d["source"]["target_act"]) for d in items)
    types = sorted({d["type"] for d in items}, key=lambda s: int(s.split()[0]))
    print("  유형별 INFORM/UNCERTAIN: " + ", ".join(
        f"{t.split()[0]}={by_type[(t, 'INFORM')]}/{by_type[(t, 'UNCERTAIN')]}" for t in types))
    print("  목표 슬롯:", dict(Counter(d["source"]["target_slot"] for d in items).most_common()))
    print("  난이도:", dict(sorted(Counter(d["difficulty"] for d in items).items(), key=lambda x: str(x[0]))))
    print("  작성자:", dict(Counter(d["source"]["author"] for d in items)))
    print("  action 2개 이상:", sum(len(d["turns"][-1]["frames"][0]["actions"]) > 1 for d in items),
          "/ 복창 이력 삽입:", sum(d["source"]["prev_turn"] == "readback" for d in items),
          "/ 정답을 '최종' 칸에서:", sum(d["source"]["answer_from"] == "최종" for d in items))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", nargs="*", help="설계표 CSV. 생략하면 카카오톡 폴더에서 찾음")
    ap.add_argument("--out", default=str(BASE / "hardset"))
    ap.add_argument("--default-call-date", default="2026-11-18")
    ap.add_argument("--orig-questions", action="store_true", help="표준 질문 대신 설계표 질문 문구 사용")
    args = ap.parse_args()

    srcs = args.src or sorted(glob.glob(DEFAULT_SRC_GLOB))
    if not srcs:
        sys.exit("설계표 CSV를 찾지 못함. --src로 지정")
    system_template = (BASE / "system_prompt_template.txt").read_text(encoding="utf-8")
    warnings, items, seen = [], [], set()
    for p in srcs:
        author = "김천일" if "천일" in Path(p).name else "손승현" if "손승현" in Path(p).name else Path(p).stem
        with open(p, encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f) if col(r, "id")]
        print(f"읽음: {author} {len(rows)}행")
        for r in rows:
            rid = col(r, "id")
            if rid in seen:
                warnings.append(f"{rid}: id 중복 → 제외")
                continue
            seen.add(rid)
            if not col(r, "발화"):
                warnings.append(f"{rid}: 발화 비어 있음 → 제외")
                continue
            d = build(r, author, args, warnings)
            if d:
                items.append(d)

    out = Path(args.out)
    dev = [d for d in items if d["source"]["split"] == "dev"]
    test = [d for d in items if d["source"]["split"] == "test"]
    other = len(items) - len(dev) - len(test)
    write_split(dev, out, "dev", system_template)
    write_split(test, out / "test_DO_NOT_OPEN", "test", system_template)
    summary(dev, "dev")
    summary(test, "test")
    if other:
        print(f"\nsplit이 dev/test가 아닌 행 {other}개는 버림")
    # 짝 문장이 dev/test로 갈라졌는지(갈라지면 dev를 보고 test 짝을 유추할 수 있음)
    pair_split = {}
    for d in items:
        if d["source"]["pair"]:
            pair_split.setdefault((d["source"]["author"], d["source"]["pair"]), set()).add(d["source"]["split"])
    crossed = [k for k, v in pair_split.items() if len(v) > 1]
    print(f"\n짝 {len(pair_split)}개 중 dev/test로 갈라진 짝: {len(crossed)}개")
    # dev·test 발화 문자열 중복
    du = {d["turns"][-1]["utterance"] for d in dev}
    print("dev와 발화가 완전히 같은 test 문제:", sum(d["turns"][-1]["utterance"] in du for d in test))
    print(f"\n경고 {len(warnings)}건 (id와 사유만)")
    for w in warnings:
        print("  -", w)
    (out / "convert_warnings.txt").write_text("\n".join(warnings), encoding="utf-8")
    print(f"\n출력: {out}\\hard_dev*.json(l), {out}\\test_DO_NOT_OPEN\\hard_test*.json(l)")


if __name__ == "__main__":
    main()
