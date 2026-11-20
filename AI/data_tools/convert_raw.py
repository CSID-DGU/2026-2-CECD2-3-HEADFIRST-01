"""
labeling.csv(사람이 라벨 단 raw 발화) → 합성 데이터와 같은 형식으로 변환.

출력 (기본 out/ 폴더)
  raw_dialogues.json          KoSGD 대화 형식 전체 (minwon_eval_v2.json과 같은 구조 + split + source)
  raw_{train,val,test}.json   split별 대화 형식
  raw_{train,val,test}.jsonl  split별 SFT 형식 (sft_train.jsonl과 동일한 system/user/assistant 문자열)
  raw_all.jsonl, raw_노인.jsonl, raw_일반.jsonl   split 없이 전체·트랙별 SFT 형식 (전달용)
  synthetic_subset.jsonl      --synthetic-subset 지정 시: sft_train.jsonl에서 raw train과
                              같은 개수·같은 (slot, act) 비율로 뽑은 합성 부분집합

변환 규칙 (LABELING_GUIDE.md와 합성 데이터의 system 프롬프트 규칙을 그대로 따름)
  - usable == Y 행만 사용
  - SYSTEM 질문은 MC 원문이 아니라 합성 데이터의 **표준 질문**으로 치환 (조건 동일). MC 원문은 source.mc_question에 보존
  - 대화 뼈대: [동의 질문 → "네 동의합니다."] + [표준 질문 → corrected_text]  (합성 데이터의 최소 구조와 동일)
  - gt_value 있으면 INFORM, 비면 UNCERTAIN. 단 entity_type=age는 값이 있어도 birth_date UNCERTAIN (연도·나이만 → UNCERTAIN 규칙)
  - birth_date가 YYYY만 있으면 UNCERTAIN, YYYY-MM-DD(또는 " (음력)")면 INFORM
  - occurred_date는 YYYY-MM-DD 형식일 때만 INFORM, 상대 표현("그저께")은 UNCERTAIN
  - complaint는 키워드로 6개 유형에 매핑, 안 되면 "기타"
  - call_date = urls.txt 메모의 방송일(YYYY.MM.DD). 없으면 --default-call-date
  - split은 행이 아니라 **영상(화자) 단위**로 6:2:2, 트랙(일반/노인)별로 따로 나눔 → 같은 사람이 train/test에 걸치지 않음

SFT 문자열 생성은 sft_train.jsonl 4,750줄 중 4,749줄을 minwon_train_v2.json에서 바이트 단위로 재현하는 것을 확인한 코드다
(나머지 1줄 RC-1_0009는 이력이 14턴이라 첫 SYSTEM 턴이 잘린 경우. raw는 이력이 짧아 해당 없음).

실행:
  python convert_raw.py                                  # labeling.csv → out/
  python convert_raw.py --synthetic-subset               # + 합성 부분집합
  python convert_raw.py --default-call-date 2026-10-19 --seed 42
"""

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).parent
TEAM_DATA = BASE / "2026-2-CECD2-3-HEADFIRST-01" / "AI" / "data"
SYSTEM_TEMPLATE = BASE / "system_prompt_template.txt"  # sft_train.jsonl에서 추출, {call_date} 자리만 다름

SERVICE = "민원접수"
INTENT = "FileComplaint"

# 합성 데이터에서 각 슬롯을 묻는 표준 질문 (minwon_train_v2.json 최빈 문구)
OPENING_Q = "안녕하세요 구청 민원 접수입니다. 민원 접수를 위해 개인정보 수집에 동의하시나요?"
OPENING_A = "네 동의합니다."
STD_QUESTION = {
    "name": "성함이 어떻게 되세요?",
    "birth_date": "생년월일을 말씀해 주시겠어요?",
    "phone": "연락받으실 전화번호를 알려주세요.",
    "complaint_type": "어떤 일로 연락 주셨어요?",
    "occurred_date": "언제부터 그러셨어요?",
    "reply_channel": "처리 결과는 어떻게 알려드릴까요?",
}
# labeling.csv entity_type → 슬롯
ENTITY_TO_SLOT = {
    "name": "name",
    "age": "birth_date",
    "birth_date": "birth_date",
    "occurred_date": "occurred_date",
    "complaint": "complaint_type",
    "phone": "phone",
    "reply_channel": "reply_channel",
}
COMPLAINT_TYPES = ["불법 주정차", "도로·보도 파손", "가로등·보안등 고장", "불법 광고물", "쓰레기·동물 사체", "기타"]
COMPLAINT_KEYWORDS = [
    ("불법 주정차", r"주차|주정차|차를\s*대|세워"),
    ("도로·보도 파손", r"도로|보도|길이|패[여였]|움푹|파손|포장|보도블록"),
    ("가로등·보안등 고장", r"가로등|보안등|신호등|불이\s*안|깜빡"),
    ("불법 광고물", r"광고|현수막|전단|입간판"),
    ("쓰레기·동물 사체", r"쓰레기|투기|사체|죽은|냄새|악취"),
]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}( \(음력\))?$")
YEAR_RE = re.compile(r"^\d{4}$")


# ---------------------------------------------------------------------------
# 입력
# ---------------------------------------------------------------------------
def load_call_dates(urls_path):
    """urls.txt 메모에서 방송일(YYYY.MM.DD 또는 YYMMDD 뒤에 '방송')을 영상ID별로 뽑는다."""
    dates = {}
    if not urls_path.exists():
        return dates
    for line in urls_path.read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("#").strip()
        m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", line)
        if not m:
            continue
        vid = m.group(1)
        d = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", line)
        if d:
            dates[vid] = f"{d.group(1)}-{d.group(2)}-{d.group(3)}"
    return dates


def load_rows(csv_path):
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# 행 → gold action
# ---------------------------------------------------------------------------
def to_action(row, warnings):
    """(slot, action dict) 반환. 변환 불가면 None."""
    etype = (row.get("entity_type") or "").strip()
    gt = (row.get("gt_value") or "").strip()
    notes = row.get("notes") or ""
    slot = ENTITY_TO_SLOT.get(etype)
    if slot is None:
        # 비정보 답인데 entity_type이 비어 있으면 notes의 "Q:연세" 같은 표시로 슬롯 추정
        m = re.search(r"Q:\s*(연세|나이|생년|생일|성함|이름|언제|민원)", notes)
        if m:
            slot = {"연세": "birth_date", "나이": "birth_date", "생년": "birth_date", "생일": "birth_date",
                    "성함": "name", "이름": "name", "언제": "occurred_date", "민원": "complaint_type"}[m.group(1)]
        else:
            warnings.append(f"{row['cand_id']}: entity_type 비어 있고 notes에 Q: 표시도 없음 → 제외")
            return None, None

    def uncertain():
        return slot, {"act": "UNCERTAIN", "slot": slot, "values": [], "canonical_values": []}

    def inform(v):
        return slot, {"act": "INFORM", "slot": slot, "values": [v], "canonical_values": [v]}

    if not gt or etype == "age":
        return uncertain()  # 값 없음 / 나이만 → UNCERTAIN
    if slot == "birth_date":
        if DATE_RE.match(gt):
            return inform(gt)
        if YEAR_RE.match(gt):
            return uncertain()  # 연도만
        warnings.append(f"{row['cand_id']}: birth_date 형식 아님 '{gt}' → UNCERTAIN")
        return uncertain()
    if slot == "occurred_date":
        if DATE_RE.match(gt):
            return inform(gt)
        return uncertain()  # 상대 표현은 call_date 기준 계산을 사람이 안 했으면 UNCERTAIN
    if slot == "complaint_type":
        if gt in COMPLAINT_TYPES:
            return inform(gt)
        for ctype, pat in COMPLAINT_KEYWORDS:
            if re.search(pat, gt) or re.search(pat, row.get("corrected_text", "")):
                return inform(ctype)
        return inform("기타")
    if slot == "phone":
        digits = re.sub(r"\D", "", gt)
        if len(digits) == 11 and digits.startswith("010"):
            return inform(f"{digits[:3]}-{digits[3:7]}-{digits[7:]}")
        return uncertain()
    return inform(gt)  # name, reply_channel


# ---------------------------------------------------------------------------
# 대화 구성 (KoSGD 형식) + SFT 문자열
# ---------------------------------------------------------------------------
def sys_turn(utt):
    return {"speaker": "SYSTEM", "utterance": utt, "frames": [{"service": SERVICE, "actions": [], "state": None}]}


def user_turn(utt, actions):
    return {"speaker": "USER", "utterance": utt,
            "frames": [{"service": SERVICE, "actions": actions,
                        "state": {"active_intent": INTENT, "requested_slots": [], "slot_values": {}}}],
            "eval": False}


def build_dialogue(row, call_dates, default_call_date, warnings):
    slot, action = to_action(row, warnings)
    if action is None:
        return None
    vid, start = row["cand_id"].rsplit("_", 1)
    track = (row.get("speaker_group") or "").strip() or "미상"
    utt = (row.get("corrected_text") or "").strip() or row["raw_text"].strip()
    if not row.get("corrected_text"):
        warnings.append(f"{row['cand_id']}: corrected_text 비어 있어 raw_text 사용")
    call_date = call_dates.get(vid)
    if not call_date:
        call_date = default_call_date
        warnings.append(f"{row['cand_id']}: 방송일 미상 → call_date {default_call_date}")
    turns = [
        sys_turn(OPENING_Q),
        user_turn(OPENING_A, [{"act": "INFORM", "slot": "consent", "values": ["true"], "canonical_values": ["true"]}]),
        sys_turn(STD_QUESTION[slot]),
        user_turn(utt, [action]),
    ]
    pattern = (row.get("pattern_tag") or "").strip() or "RAW"
    return {
        "dialogue_id": f"RAW-{track}-{vid}-{start}",
        "services": [SERVICE],
        "pattern": pattern,
        "call_date": call_date,
        "turns": turns,
        # 합성 데이터에는 없는 추가 정보. 평가·분석용이며 모델 입력에는 들어가지 않음
        "source": {"video_id": vid, "url": row["url"], "start": float(row["start"]), "track": track,
                   "mc_question": row.get("context_prev", ""), "raw_text": row["raw_text"],
                   "entity_type": row.get("entity_type", ""), "gt_value": row.get("gt_value", ""),
                   "notes": row.get("notes", "")},
    }


def build_sft(dialogue, system_template):
    """sft_train.jsonl과 같은 문자열. 마지막 USER 턴이 타깃."""
    turns = dialogue["turns"]
    k = max(i for i, t in enumerate(turns) if t["speaker"] == "USER")
    hist = "\n".join(f"{t['speaker']}: {t['utterance']}" for t in turns[:k])
    user = f"[대화 이력]\n{hist}\n\n[마지막 USER 발화]\n{turns[k]['utterance']}"
    asst = json.dumps({"active_intent": INTENT, "actions": turns[k]["frames"][0]["actions"]}, ensure_ascii=False)
    return {"messages": [{"role": "system", "content": system_template.replace("{call_date}", dialogue["call_date"])},
                         {"role": "user", "content": user},
                         {"role": "assistant", "content": asst}],
            "pattern": dialogue["pattern"], "dialogue_id": dialogue["dialogue_id"]}


# ---------------------------------------------------------------------------
# 분할: 영상 단위, 트랙별 층화
# ---------------------------------------------------------------------------
def _cell(d):
    a = [t for t in d["turns"] if t["speaker"] == "USER"][-1]["frames"][0]["actions"][0]
    return (a["slot"], a["act"])


def split_by_video(dialogues, ratios, seed, force_train=frozenset()):
    """영상 단위 분할. 트랙별로 따로, (slot, act) 셀 비율까지 맞추도록 그리디 배정.
    force_train에 든 영상은 무조건 train (팀원이 패턴 설계에 참고한 영상 → test에서 제외)."""
    by_track = defaultdict(lambda: defaultdict(list))
    for d in dialogues:
        by_track[d["source"]["track"]][d["source"]["video_id"]].append(d)
    rng = random.Random(seed)
    names = ("train", "val", "test")
    for track, vids in by_track.items():
        order = list(vids)
        rng.shuffle(order)
        cells = Counter(_cell(d) for v in vids for d in vids[v])
        target = {n: {c: r * k for c, k in cells.items()} for n, r in zip(names, ratios)}
        filled = {n: Counter() for n in names}
        forced = [v for v in order if v in force_train]
        for v in forced:
            for d in vids[v]:
                d["split"] = "train"
                filled["train"][_cell(d)] += 1
        for v in sorted((v for v in order if v not in force_train), key=lambda v: -len(vids[v])):
            vc = Counter(_cell(d) for d in vids[v])

            def cost(n):
                # 이 영상을 n에 넣었을 때 셀별 초과분(목표 대비 비율) 합. 소수 셀은 분모가 작아 가중치가 커짐
                return sum((filled[n][c] + k - target[n][c]) / max(target[n][c], 0.5) for c, k in vc.items())
            split = min(names, key=cost)
            for d in vids[v]:
                d["split"] = split
            filled[split].update(vc)
    return dialogues


# ---------------------------------------------------------------------------
# 합성 부분집합: raw train과 같은 개수, 같은 (slot, act) 비율
# ---------------------------------------------------------------------------
def synthetic_subset(raw_train_sft, sft_train_path, seed, allowed_slots):
    lines = [json.loads(l) for l in sft_train_path.open(encoding="utf-8")]

    def key(entry):
        acts = json.loads(entry["messages"][2]["content"])["actions"]
        if len(acts) != 1:
            return None
        return (acts[0]["slot"], acts[0]["act"])

    pool = defaultdict(list)
    for e in lines:
        k = key(e)
        if k and k[0] in allowed_slots:
            pool[k].append(e)
    want = Counter(key(e) for e in raw_train_sft)
    rng = random.Random(seed)
    out, short = [], []
    for k, n in want.items():
        cands = pool.get(k, [])
        if len(cands) < n:
            short.append(f"{k}: 합성에 {len(cands)}개뿐, raw는 {n}개")
        out.extend(rng.sample(cands, min(n, len(cands))))
    rng.shuffle(out)
    return out, short


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="labeling.csv")
    ap.add_argument("--urls", default="urls.txt")
    ap.add_argument("--out", default="out")
    ap.add_argument("--default-call-date", default="2026-10-19")
    ap.add_argument("--ratios", default="0.6,0.2,0.2")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--force-train-videos", default=None, help="한 줄에 영상ID 하나. 이 영상들은 무조건 train (예: work/seen_by_team_videos.txt)")
    ap.add_argument("--synthetic-subset", action="store_true",
                    help="sft_train.jsonl에서 raw train과 같은 개수·(slot,act) 비율로 합성 부분집합 추출")
    args = ap.parse_args()

    ratios = [float(x) for x in args.ratios.split(",")]
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    system_template = SYSTEM_TEMPLATE.read_text(encoding="utf-8")
    call_dates = load_call_dates(Path(args.urls))

    rows = load_rows(Path(args.csv))
    usable = [r for r in rows if (r.get("usable") or "").strip() == "Y"]  # 대문자 Y만 (소문자 y는 미확인 선채움)
    print(f"[csv] 전체 {len(rows)}행, usable=Y {len(usable)}행")

    warnings, dialogues = [], []
    for r in usable:
        d = build_dialogue(r, call_dates, args.default_call_date, warnings)
        if d:
            dialogues.append(d)
    split_by_video(dialogues, ratios, args.seed, frozenset(l.strip() for l in Path(args.force_train_videos).read_text(encoding="utf-8").splitlines() if l.strip()) if args.force_train_videos else frozenset())

    (out / "raw_dialogues.json").write_text(json.dumps(dialogues, ensure_ascii=False, indent=1), encoding="utf-8")
    sft_by_split = defaultdict(list)
    for split in ("train", "val", "test"):
        part = [d for d in dialogues if d["split"] == split]
        (out / f"raw_{split}.json").write_text(json.dumps(part, ensure_ascii=False, indent=1), encoding="utf-8")
        with (out / f"raw_{split}.jsonl").open("w", encoding="utf-8") as f:
            for d in part:
                e = build_sft(d, system_template)
                sft_by_split[split].append(e)
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # 전달용: split 없이 전체 + 트랙별 (영상·시간순)
    ordered = sorted(dialogues, key=lambda d: (d["source"]["video_id"], d["source"]["start"]))
    all_sft = [build_sft(d, system_template) for d in ordered]
    with (out / "raw_all.jsonl").open("w", encoding="utf-8") as f:
        for e in all_sft:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    for track in sorted({d["source"]["track"] for d in dialogues}):
        with (out / f"raw_{track}.jsonl").open("w", encoding="utf-8") as f:
            for d, e in zip(ordered, all_sft):
                if d["source"]["track"] == track:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # 요약
    print(f"\n[변환] 대화 {len(dialogues)}개")
    tab = Counter((d["split"], d["source"]["track"]) for d in dialogues)
    print("  split × 트랙:", dict(sorted(tab.items())))
    sa = Counter((d["turns"][-1]["frames"][0]["actions"][0]["slot"], d["turns"][-1]["frames"][0]["actions"][0]["act"])
                 for d in dialogues)
    print("  (slot, act):", dict(sa.most_common()))
    print("  pattern:", dict(Counter(d["pattern"] for d in dialogues).most_common()))
    vids = Counter((d["split"], d["source"]["video_id"]) for d in dialogues)
    print("  영상 수 by split:", dict(Counter(s for s, _ in vids)))
    if warnings:
        print(f"\n[경고] {len(warnings)}건")
        for w in warnings[:20]:
            print("  -", w)
        (out / "warnings.txt").write_text("\n".join(warnings), encoding="utf-8")

    if args.synthetic_subset:
        allowed = {d["turns"][-1]["frames"][0]["actions"][0]["slot"] for d in dialogues}
        sub, short = synthetic_subset(sft_by_split["train"], TEAM_DATA / "sft_train.jsonl", args.seed, allowed)
        with (out / "synthetic_subset.jsonl").open("w", encoding="utf-8") as f:
            for e in sub:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"\n[합성 부분집합] {len(sub)}줄 (raw train {len(sft_by_split['train'])}줄과 (slot, act) 비율 일치, 슬롯 {sorted(allowed)})")
        for s_ in short:
            print("  부족:", s_)

    tracks = Counter(d["source"]["track"] for d in dialogues)
    print(f"\n[출력] {out}/raw_all.jsonl ({len(dialogues)}줄), "
          + ", ".join(f"raw_{t}.jsonl ({n}줄)" for t, n in tracks.items())
          + ", raw_dialogues.json, raw_{train,val,test}.json/.jsonl"
          + (", synthetic_subset.jsonl" if args.synthetic_subset else ""))


if __name__ == "__main__":
    main()
