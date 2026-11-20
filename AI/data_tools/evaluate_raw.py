"""
raw 테스트셋으로 합성 학습 모델을 평가할 때 생기는 문제를 처리하는 도구.

문제와 처리
  1. 슬롯만 보고 act를 찍어도 93%가 맞는 구조 → 다수결 베이스라인을 같이 계산해 비교선으로 제시
  2. 소수 셀(birth_date INFORM, name UNCERTAIN)이 작음 → (슬롯, act) 셀별 점수와 95% CI를 따로 보고, n<20은 "결론 보류" 표시
  3. 합성과 raw의 act 비율 차이(2% vs 63%) → 클래스별 P/R/F1과 macro-F1 보고
  4. 같은 화자(영상)의 발화가 여러 개 → CI는 영상 단위 부트스트랩
  5. raw에 없는 슬롯(phone 등) → 평가셋 자체가 name/birth_date/occurred_date로 제한됨을 명시
  6. 합성과 raw 사이 누수 → 발화·이름 문자열 겹침 검사

서브커맨드
  make  : labeling.csv(Y) → 팀 추론 스크립트 입력 형식(results_v2_baseline.jsonl의 입력 필드) out/raw_eval_turns.jsonl + 누수 검사
  score : 모델 출력(jsonl, 각 줄에 gold·pred 포함) → 지표 표
          python evaluate_raw.py score --pred out/preds.jsonl [--track 노인]
          pred 줄 형식: results_v2_baseline.jsonl과 동일 (gold, pred가 dict 또는 그 repr 문자열). dialogue_id 필수
"""

import argparse
import ast
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).parent
OUT = BASE / "out"
TEAM = BASE / "2026-2-CECD2-3-HEADFIRST-01" / "AI" / "data"


def _d(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x)
    except Exception:
        return ast.literal_eval(x)


def video_of(dialogue_id):
    # RAW-노인-<videoId>-<start>
    parts = dialogue_id.split("-")
    return "-".join(parts[2:-1]) if dialogue_id.startswith("RAW-") else dialogue_id.rsplit("_", 1)[0]


# ---------------------------------------------------------------------------
def cmd_make(args):
    dialogues = json.loads((OUT / "raw_dialogues.json").read_text(encoding="utf-8"))
    rows = []
    for d in dialogues:
        turns = d["turns"]
        k = max(i for i, t in enumerate(turns) if t["speaker"] == "USER")
        hist = [f"{t['speaker']}: {t['utterance']}" for t in turns[:k]]
        gold = {"active_intent": "FileComplaint", "actions": turns[k]["frames"][0]["actions"]}
        rows.append({
            "dialogue_id": d["dialogue_id"], "turn": str(k), "variant": "raw", "service": "민원접수",
            "history": hist, "utterance": turns[k]["utterance"],
            "noise": [d["pattern"]], "category": [d["source"]["track"]],
            "gold": gold, "prev_state": {"consent": ["true"]}, "today": d["call_date"],
            "source": {"track": d["source"]["track"], "video_id": d["source"]["video_id"], "url": d["source"]["url"]},
        })
    p = OUT / "raw_eval_turns.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tracks = Counter(r["source"]["track"] for r in rows)
    cells = Counter((r["gold"]["actions"][0]["slot"], r["gold"]["actions"][0]["act"]) for r in rows)
    print(f"[make] {p} {len(rows)}줄 | 트랙 {dict(tracks)}")
    print("  (slot, act):", dict(cells.most_common()))
    maj = majority_baseline(rows)
    print(f"  다수결 베이스라인(슬롯→다수 act): {maj['acc']:.3f}  규칙={maj['rule']}")

    # 누수 검사: raw 발화·이름이 합성 학습셋에 있는가
    syn_utts, syn_names = set(), set()
    for line in (TEAM / "sft_train.jsonl").open(encoding="utf-8"):
        e = json.loads(line)
        syn_utts.add(e["messages"][1]["content"].split("[마지막 USER 발화]")[-1].strip())
        for a in json.loads(e["messages"][2]["content"])["actions"]:
            if a["slot"] == "name":
                syn_names.update(a["canonical_values"])
    dup_u = [r["utterance"] for r in rows if r["utterance"] in syn_utts]
    raw_names = {a["canonical_values"][0] for r in rows for a in r["gold"]["actions"] if a["slot"] == "name" and a["canonical_values"]}
    dup_n = sorted(raw_names & syn_names)
    print(f"  누수 검사: 발화 문자열 겹침 {len(dup_u)}건, 이름 겹침 {len(dup_n)}건 {dup_n[:10]}")
    print("  (이름 겹침은 흔한 이름이면 우연일 수 있음. 발화 겹침 0이면 누수 없음)")


def majority_baseline(rows):
    by_slot = defaultdict(Counter)
    for r in rows:
        a = r["gold"]["actions"][0]
        by_slot[a["slot"]][a["act"]] += 1
    rule = {s: c.most_common(1)[0][0] for s, c in by_slot.items()}
    correct = sum(1 for r in rows if rule[r["gold"]["actions"][0]["slot"]] == r["gold"]["actions"][0]["act"])
    return {"acc": correct / max(1, len(rows)), "rule": rule}


# ---------------------------------------------------------------------------
def score_rows(rows):
    """rows: gold/pred dict 포함. 턴 단위 지표 + 슬롯 쌍 단위 지표."""
    jga_n = jga_hit = 0
    tp = fp = fn = 0           # (slot, value) 쌍
    atp = afp = afn = 0        # (act, slot) 쌍
    cls = {"INFORM": Counter(), "UNCERTAIN": Counter()}  # tp/fp/fn per class (gold act of the slot)
    cell = defaultdict(lambda: Counter())
    for r in rows:
        g = _d(r["gold"])["actions"]
        try:
            p = _d(r["pred"])["actions"]
        except Exception:
            p = []
        gset = {(a["slot"], v) for a in g for v in a.get("canonical_values", [])}
        pset = {(a["slot"], v) for a in p for v in a.get("canonical_values", [])}
        tp += len(gset & pset); fp += len(pset - gset); fn += len(gset - pset)
        if gset:
            jga_n += 1
            jga_hit += int(gset == pset)
        ga = {(a["act"], a["slot"]) for a in g}
        pa = {(a["act"], a["slot"]) for a in p}
        atp += len(ga & pa); afp += len(pa - ga); afn += len(ga - pa)
        # 클래스별: gold 슬롯 하나 기준으로 pred act 비교
        g0 = g[0]
        p_act = next((a["act"] for a in p if a["slot"] == g0["slot"]), None)
        key = (g0["slot"], g0["act"])
        cell[key]["n"] += 1
        if p_act == g0["act"]:
            cls[g0["act"]]["tp"] += 1
            cell[key]["act_hit"] += 1
        else:
            cls[g0["act"]]["fn"] += 1
            if p_act in cls:
                cls[p_act]["fp"] += 1
        if g0["act"] == "INFORM":
            pv = next((a.get("canonical_values", []) for a in p if a["slot"] == g0["slot"]), [])
            cell[key]["value_hit"] += int(pv == g0["canonical_values"])

    def prf(t, f_p, f_n):
        pr = t / (t + f_p) if t + f_p else 0.0
        rc = t / (t + f_n) if t + f_n else 0.0
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
        return pr, rc, f1

    sp, sr, sf = prf(tp, fp, fn)
    ap_, ar, af = prf(atp, afp, afn)
    per_class = {c: prf(v["tp"], v["fp"], v["fn"]) for c, v in cls.items()}
    macro = sum(x[2] for x in per_class.values()) / 2
    return {"n": len(rows), "JGA": jga_hit / jga_n if jga_n else None, "jga_n": jga_n,
            "slot_P": sp, "slot_R": sr, "slot_F1": sf, "act_P": ap_, "act_R": ar, "act_F1": af,
            "per_class": per_class, "macro_F1": macro, "cells": {k: dict(v) for k, v in cell.items()}}


def bootstrap_ci(rows, key, iters=2000, seed=0):
    """영상 단위 부트스트랩 95% CI."""
    by_vid = defaultdict(list)
    for r in rows:
        by_vid[video_of(r["dialogue_id"])].append(r)
    vids = list(by_vid)
    rng = random.Random(seed)
    vals = []
    for _ in range(iters):
        sample = [r for v in rng.choices(vids, k=len(vids)) for r in by_vid[v]]
        s = score_rows(sample)
        v = s[key] if key in s else s["per_class"][key][1]  # key가 클래스명이면 recall
        if v is not None:
            vals.append(v)
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]


def cmd_score(args):
    rows = [json.loads(l) for l in Path(args.pred).open(encoding="utf-8")]
    if args.track:
        rows = [r for r in rows if (r.get("source") or {}).get("track") == args.track or (args.track in (r.get("category") or []))]
    s = score_rows(rows)
    maj = majority_baseline([{"gold": _d(r["gold"])} for r in rows])
    print(f"n={s['n']}  (JGA 분모 {s['jga_n']})")
    print(f"JGA {s['JGA']:.3f}" if s["JGA"] is not None else "JGA -", end="  ")
    print(f"| Slot P/R/F1 {s['slot_P']:.3f}/{s['slot_R']:.3f}/{s['slot_F1']:.3f} | Act P/R/F1 {s['act_P']:.3f}/{s['act_R']:.3f}/{s['act_F1']:.3f}")
    print(f"다수결 베이스라인(act 정확도) {maj['acc']:.3f}  규칙 {maj['rule']}")
    for c, (p, r, f) in s["per_class"].items():
        lo, hi = bootstrap_ci(rows, c)
        print(f"  {c:9s} P {p:.3f} R {r:.3f} F1 {f:.3f}   recall 95% CI [{lo:.3f}, {hi:.3f}] (영상 단위 부트스트랩)")
    print(f"macro-F1 {s['macro_F1']:.3f}")
    print("\n셀별 (slot, act): n / act 정답률 / 값 정답률(INFORM만)")
    for (slot, act), v in sorted(s["cells"].items(), key=lambda x: -x[1]["n"]):
        n = v["n"]; flag = "  ← n<20 결론 보류" if n < 20 else ""
        val = f"{v.get('value_hit', 0)/n:.3f}" if act == "INFORM" else "-"
        print(f"  {slot:14s} {act:9s} n={n:4d}  act {v.get('act_hit', 0)/n:.3f}  value {val}{flag}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("make")
    sc = sub.add_parser("score")
    sc.add_argument("--pred", required=True)
    sc.add_argument("--track", default=None)
    a = ap.parse_args()
    cmd_make(a) if a.cmd == "make" else cmd_score(a)
