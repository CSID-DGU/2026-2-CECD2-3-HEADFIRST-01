"""raw train의 소수 셀(birth_date INFORM, name UNCERTAIN)을 채우는 보강 발화.
합성 v3와 독립적으로 사람(Claude)이 직접 쓴 문장. 노인 전화 접수 말투, raw에서 관찰된 유형을 따름.
A(합성 v3) vs B+(raw+보강) 비교에 v3 문장이 섞이지 않도록 v3에서는 한 줄도 가져오지 않는다.

출력: out/raw_release_노인_20261021/fill_minority.jsonl (SFT 형식, raw와 동일 뼈대)
      raw_노인_train_plus.jsonl = raw_노인_train.jsonl + fill_minority.jsonl (섞음, 시드 42)
"""
import json
import random
from pathlib import Path

import convert_raw as c

CALL_DATE = "2026-10-19"
CONSENT_Q = "안녕하세요 구청 민원 접수입니다. 민원 접수를 위해 개인정보 수집에 동의하시나요?"

# birth_date INFORM: 월·일까지 말함 → YYYY-MM-DD (음력은 " (음력)")
BD_INFORM = [
    ("오십오년 삼월 십사일이요.", "1955-03-14"),
    ("나 사십팔년 음력 정월 초하루날 났어.", "1948-01-01 (음력)"),
    ("천구백사십삼년 시월 이십구일.", "1943-10-29"),
    ("오십일년생이고 생일은 유월 열흘날이야.", "1951-06-10"),
    ("사십육년 사월 초파일, 음력으로.", "1946-04-08 (음력)"),
    ("생년월일? 오십삼년 구월 이십일일이요.", "1953-09-21"),
    ("나는 삼십구년 섣달 그믐날 태어났어, 음력.", "1939-12-30 (음력)"),
    ("천구백오십년 이월 칠일입니다.", "1950-02-07"),
    ("사십팔년 칠월 십오일인데 호적은 그대로예요.", "1948-07-15"),
    ("오십육년 십일월 삼일생이요.", "1956-11-03"),
    ("음력으로 사십오년 팔월 보름이요.", "1945-08-15 (음력)"),
    ("천구백사십일년 오월 열이튿날.", "1941-05-12"),
    ("오십년 일월 이십육일, 양력이요.", "1950-01-26"),
    ("사십사년 삼월 초사흘날 났지, 음력으로다가.", "1944-03-03 (음력)"),
    ("생일이 오십이년 십이월 이십사일이에요.", "1952-12-24"),
    ("나 사십칠년 유월 십구일생이야, 돼지띠.", "1947-06-19"),
    ("천구백오십사년 사월 삼십일이요.", "1954-04-30"),
    ("오십팔년 음력 시월 열하루.", "1958-10-11 (음력)"),
    ("사십구년 구월 구일, 중구절날이요.", "1949-09-09"),
    ("천구백삼십팔년 팔월 이십일일입니다.", "1938-08-21"),
]

# name UNCERTAIN: 성만 / 이름만 / 별칭 / 되묻기 / 기억 못 함 / 두 이름 걸침 / 타인 이름 / 거절 / 글자풀이 미완
NM_UNCERTAIN = [
    "성은 김가요.",
    "이름? 나 그냥 순자라고 불러.",
    "영감 이름으로 하면 안 돼? 내 이름은 잘 안 써서.",
    "뭐라고? 이름? 잘 안 들려.",
    "호적에는 옥분인가 옥순인가 그렇게 돼 있어.",
    "아이고 이름은 뭐 하러 물어. 그냥 민원만 넣어줘.",
    "다들 나를 평촌댁이라고 불러요.",
    "이름 말하기가 좀 그런데 꼭 해야 돼요?",
    "박씨요, 박씨. 밀양 박씨.",
    "우리 아들 이름으로 해도 되나? 아들이 박정호인데.",
    "글자가 어려워서 그런데, 성은 최고 이름은 잘 모르겠어, 어릴 때 이름이랑 달라서.",
    "나? 할매라고 하면 돼.",
    "이름이 두 개야. 호적 이름하고 부르는 이름하고 달라.",
    "잠깐만, 뭐라고 물었어? 성함?",
    "그건 나중에 말할게. 먼저 가로등 고장 난 거부터 적어요.",
]


def dialogue(idx, slot, utt, value):
    act = ({"act": "INFORM", "slot": slot, "values": [value], "canonical_values": [value]} if value
           else {"act": "UNCERTAIN", "slot": slot, "values": [], "canonical_values": []})
    return {
        "dialogue_id": f"FILL-{slot}-{idx:03d}", "call_date": CALL_DATE, "pattern": "FILL",
        "turns": [
            {"speaker": "SYSTEM", "utterance": CONSENT_Q},
            {"speaker": "USER", "utterance": "네 동의합니다."},
            {"speaker": "SYSTEM", "utterance": c.STD_QUESTION[slot]},
            {"speaker": "USER", "utterance": utt, "frames": [{"actions": [act]}]},
        ],
    }


def main():
    out = Path("out/raw_release_노인_20261021")
    tmpl = c.SYSTEM_TEMPLATE.read_text(encoding="utf-8")
    fills = [dialogue(i, "birth_date", u, v) for i, (u, v) in enumerate(BD_INFORM)]
    fills += [dialogue(i, "name", u, None) for i, u in enumerate(NM_UNCERTAIN)]
    lines = [json.dumps(c.build_sft(d, tmpl), ensure_ascii=False) for d in fills]
    (out / "fill_minority.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    raw = (out / "raw_노인_train.jsonl").read_text(encoding="utf-8").splitlines()
    plus = raw + lines
    random.Random(42).shuffle(plus)
    (out / "raw_노인_train_plus.jsonl").write_text("\n".join(plus) + "\n", encoding="utf-8")
    print(f"fill {len(lines)} (birth_date INFORM {len(BD_INFORM)}, name UNCERTAIN {len(NM_UNCERTAIN)}) → train_plus {len(plus)}")


if __name__ == "__main__":
    main()
