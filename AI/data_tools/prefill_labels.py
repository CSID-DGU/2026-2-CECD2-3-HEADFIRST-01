"""
labeling.csv의 사람 칸을 자동 단서로 미리 채운다 (사람은 확인·수정만).

규칙
  - 이미 값이 있는 칸은 건드리지 않는다. 빈 칸만 채운다.
  - 자동으로 채운 usable은 소문자 'y' / 'n' 이다. convert_raw.py는 대문자 'Y'만 변환하므로,
    사람이 확인한 뒤 Y/N으로 바꿔야 데이터에 들어간다. (확인 안 한 행이 섞이는 걸 막는 장치)
  - speaker_group: urls.txt 메모의 [노인]/[일반] 표시. [혼합]은 비움
  - usable 'n' 후보: MC·진행자 질문으로 보이는 발화(의문형 + 연세/성함/누구/어디…), 패턴 단서가 전혀 없는 행
  - usable 'y' 후보: 질문→답 단서(Q:/A:)가 있거나 값 단서(DA-1 등)가 있는 행
  - entity_type / pattern_tag / gt_value: 단서에서 유추 가능한 것만. 이름 값은 유추 안 함
  - corrected_text: raw_text 복사 (사람이 들리는 대로 고침)

실행: python prefill_labels.py            # labeling.csv 제자리 수정
      python prefill_labels.py --dry-run  # 몇 행이 어떻게 채워질지만 출력
"""

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

LABEL_COLS = ["speaker_group", "corrected_text", "entity_type", "gt_value", "pattern_tag", "usable", "notes"]

MC_QUESTION = re.compile(r"(연세|나이|성함|이름|누구|어디|언제|몇\s*(?:살|년|월)|어떻게\s*되|말씀해|알려주)")
QUESTION_END = re.compile(r"(\?|세요|십니까|습니까|나요|예요|에요|죠|까)\s*[.!]?$")
ARABIC_NUM = re.compile(r"\b(\d{1,3})\b")
HINT_TO_ENTITY = {"Q:age": "age", "Q:name": "name", "Q:date": "occurred_date", "DA-1": "birth_date", "DA-2": "birth_date",
                  "DA-3": "birth_date", "DA-4": "occurred_date", "DA-5": "occurred_date", "CT-1": "complaint", "UN-1": "age"}

# 질문 없이 값만 말한 발화 (10/20 추가): "일흔다섯이에요", "오십삼년생이요", "올해 여든이야"
NATIVE_NUM = r"(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|스물|스무|서른|마흔|쉰|예순|일흔|여든|아흔)+"
SINO_NUM = r"[일이삼사오육륙칠팔구십백천]+"
AGE_STATEMENT = re.compile(rf"(?:{NATIVE_NUM}|{SINO_NUM}|\d{{2,3}})\s*(?:살|세)|(?:올해|지금|금년|나이는?)\s*(?:{NATIVE_NUM}|{SINO_NUM}|\d{{2,3}})(?:이|야|예요|이에요|인데|요)|(?:^|\s)(?:{NATIVE_NUM}|{SINO_NUM})(?:이에요|이요|입니다|이야|예요|이고)")
YEAR_STATEMENT = re.compile(rf"(?:{SINO_NUM}|\d{{2,4}})\s*년\s*생")

SINO_DIGITS = "영일이삼사오육칠팔구"


def num2kor(n):
    """정수 → 한자어 수 읽기 (0~99999). 1994→천구백구십사, 75→칠십오, 10→십"""
    if n == 0:
        return "영"
    units = [(10000, "만"), (1000, "천"), (100, "백"), (10, "십")]
    out = ""
    for val, name in units:
        d, n = divmod(n, val)
        if d:
            out += (SINO_DIGITS[d] if d > 1 else "") + name
    if n:
        out += SINO_DIGITS[n]
    return out


def digits_to_korean(text):
    """발화 속 아라비아 숫자를 한글 읽기로 (전화번호·소수점은 건드리지 않음)."""
    def repl(m):
        tok = m.group(0)
        if "-" in tok or "." in tok or len(tok) > 5:
            return tok
        return num2kor(int(tok))
    return re.sub(r"\d[\d\-.]*", repl, text)
HINT_TO_TAG = {"A:non-inform": "NON-INFORM", "FIX": "FIX", "DA-1": "DA-1", "DA-2": "DA-2", "DA-3": "DA-3",
               "DA-4": "DA-4", "DA-5": "DA-5", "UN-1": "UN-1", "UN-2": "UN-2", "CT-1": "CT-1",
               "NM-L1-1": "NM-L1-1", "NM-L1-2/3": "NM-L1-2", "NM-L2": "NM-L2-1", "NM-SP-1": "NM-SP-1",
               "NM-SP-3": "NM-SP-3", "NM-SP-4": "NM-SP-4"}


def load_tracks(urls_path):
    tracks = {}
    if not urls_path.exists():
        return tracks
    for line in urls_path.read_text(encoding="utf-8").splitlines():
        m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", line)
        t = re.search(r"\[(노인|일반|혼합)", line)
        if m and t:
            tracks[m.group(1)] = {"노인": "노인", "일반": "일반", "혼합": ""}[t.group(1)]
    return tracks


def prefill(row, tracks):
    vid = row["cand_id"].rsplit("_", 1)[0]
    hints = [h for h in (row.get("pattern_hint") or "").split("|") if h]
    text = row.get("raw_text", "").strip()
    filled = {}

    def put(col, val):
        if val and not (row.get(col) or "").strip():
            row[col] = val
            filled[col] = val

    put("speaker_group", tracks.get(vid, ""))
    put("corrected_text", digits_to_korean(text))

    looks_mc = bool(MC_QUESTION.search(text) and QUESTION_END.search(text))
    has_qa = any(h.startswith(("Q:", "A:")) for h in hints)
    has_value_hint = any(h in HINT_TO_ENTITY for h in hints)
    # 질문 없이 값만 말한 발화도 후보로 (MC가 "102세 강예덕 씨"라고 소개하는 것도 걸리지만 검수에서 거름)
    if not has_value_hint and not looks_mc:
        if YEAR_STATEMENT.search(text):
            has_value_hint = True
            hints = hints + ["DA-1"]
        elif AGE_STATEMENT.search(text):
            has_value_hint = True
            hints = hints + ["AGE"]

    if looks_mc and not has_qa:
        put("usable", "n")
        put("notes", "자동: MC 질문으로 보임")
    elif has_qa or has_value_hint:
        put("usable", "y")
    else:
        put("usable", "n")
        put("notes", "자동: 패턴 단서 없음")

    for h in hints:
        if h in HINT_TO_ENTITY:
            put("entity_type", HINT_TO_ENTITY[h])
            break
    if "AGE" in hints:
        put("entity_type", "age")
        put("pattern_tag", "PLAIN")
    tags = [HINT_TO_TAG[h] for h in hints if h in HINT_TO_TAG]
    if "A:non-inform" not in hints and "Q:age" in hints and ARABIC_NUM.search(text):
        put("gt_value", ARABIC_NUM.search(text).group(1))
        tags.append("PLAIN")
    if "Q:age" in hints and ("A:non-inform" in hints or "UN-1" in hints):
        put("entity_type", "age")
    put("pattern_tag", "|".join(dict.fromkeys(tags)))
    return filled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="labeling.csv")
    ap.add_argument("--urls", default="urls.txt")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redo-auto", action="store_true",
                    help="미확인(소문자 y/n) 행의 자동 채움을 전부 지우고 현재 규칙으로 다시 계산 (확인된 Y/N은 유지)")
    args = ap.parse_args()

    path = Path(args.csv)
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows, cols = list(reader), reader.fieldnames
    tracks = load_tracks(Path(args.urls))

    # 질문 뒤 두 번째 반응도 후보로: 직전 후보 행이 Q: 단서(질문→답)였고, 이 행의 context_prev가 그 답이면
    # ("연세가?" → "아이 몰라요" → "숙녀의 나이를 물어보는 건 실례지" 같은 이어지는 회피)
    second = set()
    prev = None
    for r in rows:
        vid = r["cand_id"].rsplit("_", 1)[0]
        if prev and prev["cand_id"].rsplit("_", 1)[0] == vid and "Q:" in (prev.get("pattern_hint") or "") \
                and r.get("context_prev", "").strip() == prev.get("raw_text", "").strip() and "?" not in r.get("raw_text", ""):
            second.add(r["cand_id"])
        prev = r

    stats = Counter()
    for r in rows:
        if (r.get("usable") or "").strip() in ("Y", "N"):
            stats["이미 확인됨(건너뜀)"] += 1
            continue
        if args.redo_auto:
            for c in LABEL_COLS:
                r[c] = ""
        filled = prefill(r, tracks)
        if r["cand_id"] in second and r.get("usable") == "n":
            r["usable"] = "y"
            r["notes"] = "자동: 질문 뒤 2번째 반응(회피·이어지는 답 가능)"
            filled["usable"] = "y"
        stats[f"usable={filled.get('usable', '(유지)')}"] += 1
        if "gt_value" in filled:
            stats["gt_value 유추"] += 1

    print("자동 채움 결과:", dict(stats))
    y = [r for r in rows if r.get("usable") == "y"]
    print(f"사람이 들어봐야 할 행(usable=y): {len(y)}  /  n으로 둔 행: {sum(1 for r in rows if r.get('usable') == 'n')}")
    print("  y 행 영상별:", dict(Counter(r["cand_id"].rsplit("_", 1)[0] for r in y).most_common()))
    if args.dry_run:
        print("(dry-run: 저장 안 함)")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"[저장] {path}  → usable 소문자 y/n은 미확인 표시. 확인 후 Y/N으로 바꿀 것")


if __name__ == "__main__":
    main()
