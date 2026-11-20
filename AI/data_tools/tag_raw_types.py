# -*- coding: utf-8 -*-
"""raw 368건에 하드 테스트셋 유형(1~10)을 붙인다. (AI 초안 → 사람이 확인)

목적: 하드셋 유형이 실제 발화에서 관찰되는지 건수로 보이기 위함.
규칙(정규식) + 직접 읽고 정한 목록(MANUAL)을 합친다. 한 발화에 유형이 여러 개 붙을 수 있다.
학습 데이터에는 쓰지 않는다(raw test 62도 포함돼 있으므로 보강 근거로 쓰지 말 것).

  python tag_raw_types.py
출력: out/raw_types/raw_type_tags.csv, out/raw_types/raw_type_summary.md
"""
import csv, json, re, collections, pathlib

SRC = pathlib.Path("out/raw_release_20261021")
OUT = pathlib.Path("out/raw_types"); OUT.mkdir(parents=True, exist_ok=True)

TYPES = {1: "값 일부만", 2: "묻지 않은 정보 섞임", 3: "타인 정보", 4: "번복·교정", 5: "모호·추정",
         6: "되묻기·딴소리", 7: "거절·회피", 8: "조립·계산", 9: "숫자·한글 혼합", 10: "긴 사연 속 값"}
EXTRA = {"A": "별칭·호칭으로 답함(유형 밖)"}

# 직접 읽고 정한 것 (raw_eval_turns.jsonl 줄 번호, 0부터)
MANUAL = {
    2: [6, 29, 35, 51, 93, 127, 130, 155, 200, 366],
    # 11/20 사용자 확인: 타인 이름 INFORM은 64·77·114·138 네 건뿐(나머지 name INFORM 12건은 유형 3에서 뺌)
    3: [18, 24, 28, 64, 76, 77, 78, 98, 101, 114, 119, 120, 122, 138, 166, 171, 184, 206, 329, 352],
    4: [114, 207, 213, 236, 267, 273, 281, 296, 335],
    5: [3, 9, 10, 20, 22, 28, 32, 39, 40, 53, 54, 60, 61, 62, 76, 78, 79, 89, 94, 98, 171, 180, 193, 194,
        219, 220, 233, 238, 301, 304, 320, 335, 345, 362],
    6: [53, 61, 92, 132, 174, 234, 256, 310, 331, 339, 343, 358, 359, 362],
    7: [49, 57, 68, 70, 86, 176, 197, 198, 228, 272, 314, 337],
    8: [11, 36, 42, 87, 104, 116, 121, 129, 162, 163, 169, 170, 172, 177, 204, 230, 231, 233, 235, 253,
        274, 275, 278, 281, 287, 297, 298, 308, 355, 357],
    "A": [88, 103, 187, 208, 257, 348, 365],
    1: [65, 67, 196, 220],   # 이름 일부(성만·이름만), 달까지만
}
NUM = r"(띠|년|월|살|세\b|세[요입이고]|학년|스물|서른|마흔|쉰|예순|일흔|여든|아흔|[일이삼사오육칠팔구]십|백|구칠|구이|칠칠|고슴디|병자)"


def split_map():
    m = {}
    for sp in ("train", "val", "test"):
        p = SRC / f"raw_{sp}.json"
        if p.exists():
            for d in json.load(open(p, encoding="utf-8")):
                m[d["dialogue_id"]] = sp
    return m


def main():
    rows = [json.loads(l) for l in open(SRC / "raw_eval_turns.jsonl", encoding="utf-8")]
    sp = split_map()
    man = collections.defaultdict(set)
    for t, idxs in MANUAL.items():
        for i in idxs:
            man[i].add(t)
    out = []
    for i, r in enumerate(rows):
        u = r["utterance"]
        acts = r["gold"]["actions"]
        slot, act = acts[0]["slot"], acts[0]["act"]
        ts = set(man[i])
        # 1 값 일부만: 날짜 슬롯에서 값의 일부(나이·연도·띠·월일)만 말해 UNCERTAIN
        if act == "UNCERTAIN" and slot in ("birth_date", "occurred_date") and re.search(NUM, u) \
                and not (ts & {6, 7}) :
            ts.add(1)
        # 10 긴 사연 속 값: 35자 이상
        if len(u) >= 35:
            ts.add(10)
        out.append({"idx": i, "dialogue_id": r["dialogue_id"], "split": sp.get(r["dialogue_id"], ""),
                    "track": r["category"][0], "slot": slot, "act": act, "utterance": u,
                    "types": " ".join(str(t) for t in sorted(ts, key=str)), "확인(틀리면 고쳐 쓰기)": ""})
    with open(OUT / "raw_type_tags.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)

    n = len(out); eld = sum(1 for o in out if o["track"] == "노인")
    L = [f"## raw {n}건의 하드셋 유형 분포 (AI 초안, 사람 확인 전)", "",
         f"- 대상: raw 확정 {n}건(노인 {eld}, 일반 {n - eld}). 슬롯은 name · birth_date · occurred_date뿐(방송에는 전화번호 · 동의 · 민원유형 · 회신방법이 안 나옴).",
         "- 한 발화에 유형이 여러 개 붙을 수 있어 합계가 건수보다 크다.",
         "- 예시는 train 분할에서만 뽑았다.", "",
         "| 유형 | 전체 | 노인 | 일반 | INFORM / UNCERTAIN | 예시 |", "|---|---:|---:|---:|---|---|"]
    def has(o, t): return str(t) in o["types"].split()
    for t, name in list(TYPES.items()) + list(EXTRA.items()):
        sel = [o for o in out if has(o, t)]
        e = [o["utterance"] for o in sel if o["split"] == "train"][:2]
        L.append(f"| {t} {name} | {len(sel)} | {sum(o['track']=='노인' for o in sel)} | {sum(o['track']!='노인' for o in sel)} | "
                 f"{sum(o['act']=='INFORM' for o in sel)} / {sum(o['act']=='UNCERTAIN' for o in sel)} | "
                 + " / ".join(f"\"{x[:40]}\"" for x in e) + " |")
    none = [o for o in out if not o["types"]]
    L.append(f"| (유형 없음: 값만 말함) | {len(none)} | {sum(o['track']=='노인' for o in none)} | {sum(o['track']!='노인' for o in none)} | "
             f"{sum(o['act']=='INFORM' for o in none)} / {sum(o['act']=='UNCERTAIN' for o in none)} | |")
    L += ["", "### 유형 3(타인 정보)에서 raw 라벨과 하드셋 기준이 다른 점", ""]
    t3 = [o for o in out if has(o, 3)]
    L.append(f"- raw에서 타인 정보로 본 {len(t3)}건 중 INFORM {sum(o['act']=='INFORM' for o in t3)}건, UNCERTAIN {sum(o['act']=='UNCERTAIN' for o in t3)}건. "
             "raw는 '말한 이름을 뽑는다'는 기준으로 라벨했고(사람 찾기 방송이라 타인 이름이 답), 하드셋은 '타인 정보는 UNCERTAIN'이 기준이다. 팀 확인 필요.")
    L += ["", "### 분할별 건수", "", "| 유형 | train | val | test |", "|---|---:|---:|---:|"]
    for t, name in list(TYPES.items()) + list(EXTRA.items()):
        sel = [o for o in out if has(o, t)]
        L.append(f"| {t} {name} | " + " | ".join(str(sum(o['split']==s for o in sel)) for s in ("train", "val", "test")) + " |")
    (OUT / "raw_type_summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    # 점검용: UNCERTAIN인데 유형이 하나도 안 붙은 것
    print("\n[점검] UNCERTAIN인데 유형 없음:")
    for o in none:
        if o["act"] == "UNCERTAIN": print("  ", o["idx"], o["slot"], o["utterance"])


if __name__ == "__main__":
    main()
